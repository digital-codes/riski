"""Round-trip fact cross-check for extracted statements (task 6.1).

For each pair with response statements the checker:

1. renders the statements to a short German sample text
   (``render_response_text``),
2. asks the decision model (d3:2b, SystemOne-style) whether the sample
   text is fact-compatible with the pair's source chunks (style
   irrelevant, facts count) — a language model tie-break is available
   via ``--tiebreak-model``,
3. stores the verdict (passed/failed + reason) in the ``crosschecks``
   table.

Tuning loop (design D12): run this stage right after an extraction
batch on the SAME sample pairs; recurring mismatch classes drive
extraction-prompt adjustments (max 3 iterations). ``--tuning-report``
appends the iteration summary (mismatch classes, tried change, pass
rate) to ``results/kg_crosscheck_tuning.md``.

Usage::

    python -m src.kg.kgCrossCheck --limit 20           # sample batch
    python -m src.kg.kgCrossCheck --tiebreak-model mistral:latest
    python -m src.kg.kgCrossCheck --tuning-report      # append summary
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
from typing import Any

from sqlalchemy import text

from src.db import get_engine, get_logger
from src.kg.kgRemote import KgRemote
from src.kg.kgStore import KgStore
from src.kg.kgStatus import StatusTicker
from src.remote import get_prompt

log = get_logger("riski.kg.crosscheck")

DEFAULT_STORE = "results/kg_statements.sqlite"
DEFAULT_REPORT = "results/kg_crosscheck_tuning.md"
# Verdict model: d3:2b via the ollama SystemOne endpoint
# (POST /v1/systemone — the only route the d3-renderer model serves,
# cf. https://ollama.com/library/d3;
# noul score 0..1 per question). Language-model fallback via
# --verdict-model when SystemOne is unreachable.
DEFAULT_VERDICT_MODEL = "d3:2b"
NOUL_CONTRADICTION_THRESHOLD = 0.5

# change: centralize-llm-instruction-prompts — the SystemOne question
# instructions and the chat fallback instruction text moved to
# config/instruction_prompts.json (ids: kg-contradiction-question /
# kg-verdict-tiebreak); question assembly and answer criteria stay here.


def contradiction_questions() -> dict:
    """Cross-check SystemOne questions with the `instructions` field
    resolved from the prompt registry."""
    return {
        "contradicts": {
            "type": "noul",
            "instructions": get_prompt("kg-contradiction-question"),
            "criteria": {
                "true": "Ja, sie widersprechen sich in Fakten.",
                "false": "Nein, sie widersprechen sich nicht.",
            },
        }
    }

_HEAD_CHUNKS_SQL = text(
    """
    SELECT fc.text FROM "File_chunks" fc
    JOIN "File" f ON f.sid = fc."file_sid"
    WHERE f."oparlKey" = :dk
    ORDER BY fc.chunk_index LIMIT 3
    """
)


def render_response_text(fields: dict) -> str:
    """Statements → short German sample text (facts only, style free).

    Metadata-owned fields (meeting_date, document_id, file_names,
    author-from-DB) are NOT rendered — the cross-check must judge only
    what the MODEL extracted, not DB-provenance metadata (iteration-2
    fix: wrong-date false positives came from the DB meeting date).
    """
    lines = []
    mapping = [
        ("response_type", "Art der Antwort"),
        ("result", "Ergebnis"),
        ("planned_action", "Geplante Maßnahme"),
        ("action_executor", "Ausführende"),
        ("expected_cost", "Erwartete Kosten"),
        ("start_date", "Beginn (laut Dokument)"),
        ("end_date", "Ende (laut Dokument)"),
        ("request_modifications", "Änderungen am Antrag"),
        ("dependencies_constraints", "Bedingungen/Einschränkungen"),
        # request-stage fields
        ("topic", "Thema"),
        ("intended_impact", "Beabsichtigte Wirkung"),
        ("audience", "Betroffene"),
        ("action_actor", "Akteur"),
        ("requested_action", "Geforderte Maßnahme"),
        ("expected_benefit", "Erwarteter Nutzen"),
        ("involved_cost", "Kosten (laut Dokument)"),
    ]
    for key, label in mapping:
        value = str(fields.get(key, "") or "").strip()
        if value and value.lower() != "none":
            lines.append(f"{label}: {value}")
    return "\n".join(lines) if lines else "(keine Angaben)"


def source_text(conn: Any, doc_keys: list[str], cap: int = 9000) -> str:
    """Head chunks of the pair's response documents."""
    parts = []
    for dk in doc_keys[:3]:
        rows = conn.execute(_HEAD_CHUNKS_SQL, {"dk": dk}).fetchall()
        body = "".join((r[0] or "") for r in rows)
        if body:
            parts.append(body[:cap])
    return "\n\n".join(parts)


VERDICT_PROMPT = "kg-verdict-tiebreak"  # id in config/instruction_prompts.json


def verdict_prompt(summary: str, source: str) -> str:
    """Fallback instruction text from the prompt registry (id:
    kg-verdict-tiebreak), formatted with the decision summary and the
    original text."""
    return get_prompt(VERDICT_PROMPT).format(summary=summary, source=source)


def classify_mismatch(reason: str) -> str:
    """Coarse mismatch classes for the tuning report (D12)."""
    r = reason.lower()
    if "englisch" in r or re.search(r"\b(the|and|of|for)\b", reason):
        return "english-leakage"
    if "kosten" in r or "€" in reason or "euro" in r:
        return "invented-cost"
    if "datum" in r or "date" in r:
        return "wrong-date"
    if "ausführend" in r or "zuständig" in r:
        return "wrong-executor"
    if "erfunden" in r or "nicht im originaltext" in r:
        return "hallucinated-fact"
    return "other"


def check_pair(
    remote: KgRemote,
    conn: Any,
    store: KgStore,
    pair_key: str,
    tiebreak_model: str | None = None,
    verdict_model: str = DEFAULT_VERDICT_MODEL,
) -> dict:
    """Cross-check one pair; stores and returns the verdict record.

    Prefers response statements (spec: "at least for the response");
    falls back to request statements when the pair has none — both
    stages must be fact-compatible with their source documents.
    """
    row = store.conn.execute(
        "SELECT fields_json FROM statements WHERE pair_key = ? AND stage = 'response'",
        (pair_key,),
    ).fetchone()
    stage = "response"
    if row is None:
        row = store.conn.execute(
            "SELECT fields_json FROM statements WHERE pair_key = ? AND stage = 'request'",
            (pair_key,),
        ).fetchone()
        stage = "request"
    if row is None:
        return {}
    fields = json.loads(row[0])
    summary = render_response_text(fields)
    docs = store.documents_for_pair(pair_key)
    role = "response" if stage == "response" else "request"
    resp_keys = [d["doc_key"] for d in docs if d["role"] in (role, "modification")]
    src = source_text(conn, resp_keys)
    record: dict = {"verdict": "skipped", "reason": "no source text"}
    if src:
        state = f"Entscheidungs-Angaben:\n{summary}\n\nOriginaltext (Auszug):\n{src[:9000]}"
        verdict, reason = None, ""
        # 1st choice: d3:2b SystemOne verdict (noul score, threshold)
        try:
            answers = remote.systemone(
                state, contradiction_questions(),
                prompt_id="kg-contradiction-question",
                call_id="kgCrossCheck.check_pair.1",
            )
            noul = float(answers.get("contradicts", {}).get("noul", 0.0))
            verdict = "failed" if noul >= NOUL_CONTRADICTION_THRESHOLD else "passed"
            reason = f"systemone noul={noul:.3f}"
        except Exception as exc:  # noqa: BLE001
            log.info("systemone verdict unavailable (%s); falling back to %s", exc, verdict_model)
        # fallback: language-model JSON verdict
        if verdict is None:
            try:
                prompt = verdict_prompt(summary, src[:9000])
                out = remote.chat_json(
                    [{"role": "user", "content": prompt}], model=verdict_model, num_ctx=8192,
                    prompt_id="kg-verdict-tiebreak", call_id="kgCrossCheck.check_pair.2",
                )
                verdict = str(out.get("verdict", "")).lower()
                reason = str(out.get("reason", ""))
                if verdict not in ("passed", "failed") and tiebreak_model:
                    out = remote.chat_json(
                        [{"role": "user", "content": prompt}], model=tiebreak_model, num_ctx=8192,
                        prompt_id="kg-verdict-tiebreak", call_id="kgCrossCheck.check_pair.3",
                    )
                    verdict = str(out.get("verdict", "")).lower()
                    reason = str(out.get("reason", ""))
            except Exception as exc:  # noqa: BLE001
                verdict, reason = "failed", f"check-error: {exc}"
        record = {"verdict": verdict if verdict in ("passed", "failed") else "failed",
                  "reason": reason}
    store.upsert_crosscheck(pair_key, record["verdict"], record["reason"])
    return record


def tuning_report_line(batch: Counter, total: int, passed: int, iteration: int) -> str:
    classes = ", ".join(f"{k}={v}" for k, v in batch.most_common()) or "none"
    return (
        f"\n## Iteration {iteration} ({__import__('datetime').date.today().isoformat()})\n\n"
        f"- pairs checked: {total}, passed: {passed} "
        f"({(100 * passed // total if total else 0)}%)\n"
        f"- mismatch classes: {classes}\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", default=DEFAULT_STORE)
    parser.add_argument("--endpoint", default="ollama")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--verdict-model", default=DEFAULT_VERDICT_MODEL,
                        help="model for the fact-compat verdict (d3:2b is NOT "
                        "serveable by local ollama — see module docstring)")
    parser.add_argument("--tiebreak-model", default=None)
    parser.add_argument("--tuning-report", action="store_true",
                        help="append iteration summary to the tuning report")
    parser.add_argument("--iteration", type=int, default=1)
    parser.add_argument("--force", action="store_true",
                        help="re-check pairs that already have a verdict")
    args = parser.parse_args()

    engine = get_engine(readonly=True)
    conn = engine.connect()
    store = KgStore(args.store)
    # the standffalone-tune diagnose path prefers the dedicated CCLLM_*
    # client; the inline cross-check keeps its Decision/LLM path
    remote = KgRemote.for_diagnose() or KgRemote(args.endpoint)

    pairs = store.conn.execute(
        """
        SELECT DISTINCT p.pair_key FROM pairs p
        JOIN statements s ON s.pair_key = p.pair_key AND s.stage IN ('response','request')
        """ + ("" if args.force else
               " WHERE p.pair_key NOT IN (SELECT pair_key FROM crosschecks)")
    ).fetchall()
    if args.limit:
        pairs = pairs[: args.limit]

    stats = {"checked": 0, "passed": 0, "failed": 0, "skipped": 0}
    classes: Counter = Counter()
    ticker = StatusTicker()
    ticker.section("crosscheck")
    for row in pairs:
        stats["checked"] += 1
        record = check_pair(
            remote, conn, store, row["pair_key"],
            tiebreak_model=args.tiebreak_model,
            verdict_model=args.verdict_model,
        )
        if record.get("verdict") == "passed":
            stats["passed"] += 1
        elif record.get("verdict") == "skipped":
            stats["skipped"] += 1
        else:
            stats["failed"] += 1
            classes[classify_mismatch(record.get("reason", ""))] += 1
        ticker.tick(
            f"checked={stats['checked']} passed={stats['passed']} "
            f"failed={stats['failed']}"
        )
        if stats["checked"] % 10 == 0:
            store.commit()  # checkpoint (design D12: cheap re-runs)

    store.commit()
    ticker.tick(f"done: {stats} classes={dict(classes)}", force=True)
    if args.tuning_report:
        with open(DEFAULT_REPORT, "a", encoding="utf-8") as fh:
            fh.write(
                tuning_report_line(classes, stats["checked"], stats["passed"], args.iteration)
            )
        print(f"tuning report appended: {DEFAULT_REPORT}")
    conn.close()
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
