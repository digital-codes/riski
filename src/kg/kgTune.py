"""D12 tuning pass — diagnose failed cross-checks with reasons.

The inline verdict (d3:2b SystemOne) gives only a noul score, no
reason. This stage re-examines the FAILED pairs with the language
model (OLC cloud chat): renders the statement summary, compares with
source spans, classifies the mismatch (invented cost | wrong date |
wrong executor | english-leakage | hallucinated fact | ok-after-review)
and:

1. writes the diagnosis into cyanckcheck.reason (prefixed 'tune:') so
   the tuning report has substance,
2. sets failed pairs whose failure looks like CHECKER artifact (model
   now judges them compatible) to passed,
3. resets truly-extracted pairs to 'identified' for re-extraction with
   adjusted prompts on the NEXT kgStatements run (the running process
   keeps its in-memory queue; its remaining pairs are untouched).

Usage (safe in parallel with the bulk run):
    python -m src.kg.kgTune --limit 40
"""

from __future__ import annotations

try:  # script-mode import bootstrap
    import _bootstrap  # noqa: F401
except ImportError:
    pass

import argparse
import json
import re
from collections import Counter

from sqlalchemy import text

from src.db import get_engine, get_logger
from src.kg.kgRemote import KgRemote
from src.kg.kgStore import KgStore
from src.kg.kgStatus import StatusTicker
from src.kg.kgCrossCheck import render_response_text, source_text

log = get_logger("riski.kg.tune")

DIAGNOSE_PROMPT = """Du bist Fehldiagnose-Spezialist. Vergleiche die extrahierten
Angaben mit dem Originaltext und entscheide:

Entscheidungs-Angaben:
{summary}

Originaltext (Auszug):
{source}

WIDERSPRUCH nur wenn ein extrahierter Wert dem Original EXPLIZIT anders lautet (falsche Stelle, erfundene Kosten, falsches Datum).
Fehlende Verdichtung ist KEIN Widerspruch.

Antworte NUR als JSON: {{"verdict": "passed"|"failed", "reason": "<kurz, deutsch — nenne das Feld und die Diskrepanz>", "system_issue": "prompt|checker|ocr|model"}}
"""

CLASSES = {
    "prompt": "prompt-unclear",       # extractor prompt should be sharpened
    "checker": "checker-artifact",    # wrong verdict — pass instead
    "ocr": "ocr-evidence",
    "model": "model-limitation",
}


def classify(reason: str) -> str:
    for token, label in CLASSES.items():
        if token in reason:
            return label
    return "other"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", default="results/kg_statements.sqlite")
    parser.add_argument("--endpoint", default="olc")
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--report", default="results/kg_crosscheck_tuning.md")
    parser.add_argument("--apply-reset", action="store_true",
                        help="reset prompt-issue failed pairs to 'identified'")
    args = parser.parse_args()

    engine = get_engine(readonly=True)
    conn = engine.connect()
    store = KgStore(args.store)
    # diagnose calls go through the dedicated CCLLM_* client when the
    # operator has configured one; generic cloud chat is the fallback
    remote = KgRemote.for_diagnose() or KgRemote(args.endpoint)

    rows = store.conn.execute(
        "SELECT pair_key, reason FROM crosschecks WHERE verdict = 'failed' LIMIT :n",
        {"n": args.limit},
    ).fetchall()
    ticker = StatusTicker()
    ticker.section("tune")
    ticker.tick(f"failed pairs to diagnose: {len(rows)}", force=True)

    classes = Counter()
    reset_pairs = 0
    for row in rows:
        pair_key = row["pair_key"]
        st = store.conn.execute(
            "SELECT fields_json, stage FROM statements WHERE pair_key = ? "
            "AND stage IN ('response','request') LIMIT 1",
            (pair_key,),
        ).fetchone()
        if st is None:
            continue
        summary = render_response_text(json.loads(st[0]))
        docs = store.documents_for_pair(pair_key)
        role = st[1]
        keys = [
            d["doc_key"] for d in docs
            if d["role"] in (role, "modification")
        ]
        src = source_text(conn, keys, cap=6000)
        if not src:
            continue
        try:
            out = remote.chat_json(
                [{"role": "user",
                  "content": DIAGNOSE_PROMPT.format(summary=summary, source=src)}],
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("diagnose failed for %s: %s", pair_key, exc)
            continue
        verdict = str(out.get("verdict", "")).lower()
        reason = str(out.get("reason", ""))
        issue = classify(str(out.get("system_issue", "")))
        classes[issue] += 1
        store.upsert_crosscheck(pair_key, verdict or "failed", f"tune: {issue}: {reason}")
        # checker-artifact → pass; prompt-issue → reset for smart re-extract
        if verdict == "passed":
            pass
        elif issue == "prompt" and args.apply_reset:
            store.set_pair_status(pair_key, "identified")
            reset_pairs += 1
        ticker.tick(f"diagnosed={classes.total()} resets={reset_pairs}")

    store.commit()
    ticker.tick(f"classes: {dict(classes)}", force=True)

    with open(args.report, "a", encoding="utf-8") as fh:
        fh.write(
            f"\n## Tuning diagnose {__import__('datetime').date.today().isoformat()}"
            f" ({len(rows)} pairs)\n\n- classes: {dict(classes)}\n"
            f"- pair status resets: {reset_pairs}\n"
        )
    conn.close()
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
