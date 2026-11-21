"""Field-level failure flags on statements — post-archive QA hardening.

Operator requirement (2026-11-20): failure modes SHALL be flagged at the
statement level; hallucination-suspect facts MUST NOT remain as plain
field values. Instead the suspect value moves into a note block and the
field is blanked — downstream consumers can never mistake it for
extracted fact.

Quality/certainty infrastructure that already exists (reused, not
duplicated):

* `crosschecks.verdict/reason` — pair-level round-trip verdict, with
  tune reasons naming the field + discrepancy (kgTune, D12/D14 loop)
* `statements.fields_json.source_refs` — per-statement source doc
  references
* `kg_pairs.outcome_confidence/outcome_signal` — pair-level outcome
  certainty
* `pair_documents.verify_note` — per-attachment verification detail
  (kgProtocols / kgAbstimmung OCR gates)

NEW here — **field-level flags inside `fields_json`** (JSONB absorbs
the schema growth, SQLite and PostgreSQL alike — no DDL):

    "_flags":   {field: "hallucination-suspect|date-suspect|..."},
    "_flagged": {field: {"value": <original>, "reason": <why>, "origin": "crosscheck"}}

Affected VALUE is blanked from the plain field. The rendering in
kgCrossCheck / kgExport consumers sees only verified-or-empty fields.

`--repair` mode processes all diagnosed failures and writes flags;
`--dry-run` lists what would be flagged.

Usage::

    python -m src.kg.kgFlagFailures --dry-run
    python -m src.kg.kgFlagFailures --apply
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

from src.db import get_engine, get_logger
from src.kg.kgRemote import KgRemote
from src.kg.kgStore import KgStore
from src.kg.kgStatus import StatusTicker
from src.kg.kgCrossCheck import render_response_text, source_text
from src.remote import get_prompt
from src.db import get_engine as _pg_engine  # noqa: F401 (pg parity later)

log = get_logger("riski.kg.flagfailures")

FIELD_ALIASES = {
    # diagnose reasons name fields in German — map to field keys
    "kosten": "involved_cost",
    "erwartete kosten": "involved_cost",
    "beginn": "start_date",
    "ende": "end_date",
    "startdatum": "start_date",
    "enddatum": "end_date",
    "ausführende": "action_executor",
    "ausführende stelle": "action_executor",
    "thema": "topic",
    "maßnahme": "requested_action",
    "geforderte maßnahme": "requested_action",
    "nutzen": "expected_benefit",
    "erwarteter nutzen": "expected_benefit",
    "betroffene": "audience",
    "akteur": "action_actor",
    "wirkung": "intended_impact",
    "beabsichtigte wirkung": "intended_impact",
}

# change: centralize-llm-instruction-prompts — the instruction text moved to
# config/instruction_prompts.json (id: kg-field-flags)
FIELD_FLAGS_PROMPT_ID = "kg-field-flags"

FIELD_KEYS = ["topic", "request_type", "meeting_date", "document_id",
              "file_names", "author", "intended_impact", "audience",
              "action_actor", "requested_action", "start_date", "end_date",
              "expected_benefit", "involved_cost", "response_type", "result",
              "planned_action", "action_executor", "expected_cost",
              "request_modifications", "dependencies_constraints"]


def field_flags(pair_key: str, stage: str, fields: dict, src: str,
                remote: KgRemote) -> list[dict]:
    """Diagnose each named field; return the affected-fields verdicts."""
    summary = render_response_text(fields)
    prompt = get_prompt(FIELD_FLAGS_PROMPT_ID).format(summary=summary, source=src)
    try:
        out = remote.chat_json(
            [{"role": "user", "content": prompt}],
            prompt_id=FIELD_FLAGS_PROMPT_ID, call_id="kgFlagFailures.field_flags.1",
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("flag diagnose failed for %s: %s", pair_key, exc)
        return []
    hits = []
    for item in out.get("fields_affected", []):
        key = str(item.get("field", ""))
        # allow German names in the response
        key_norm = key if key in FIELD_KEYS else FIELD_ALIASES.get(key.lower(), None)
        if key_norm is None:
            # try fuzzy: find the field key whose German alias prefix matches
            low = key.lower()
            for alias, fk in FIELD_ALIASES.items():
                if low in alias or alias in low:
                    key_norm = fk
                    break
        mode = str(item.get("mode", "other"))
        flag = bool(item.get("flag", False))
        reason = str(item.get("reason", ""))
        if key_norm and flag:
            hits.append({"field": key_norm, "mode": mode, "reason": reason})
    return hits


def flag_statement(store: KgStore, pair_key: str, stage: str, hits: list[dict],
                   apply: bool) -> int:
    """Write the _flags + _flagged blocks; blank the suspect values."""
    row = store.conn.execute(
        "SELECT fields_json FROM statements WHERE pair_key=? AND stage=? LIMIT 1",
        (pair_key, stage)).fetchone()
    if row is None:
        return 0
    fields = json.loads(row[0])
    flags = fields.setdefault("_flags", {})
    flagged = fields.setdefault("_flagged", {})
    n = 0
    for h in hits:
        key = h["field"]
        value = fields.get(key, "")
        if not value:
            continue  # nothing to blank
        flags[key] = h["mode"]
        flagged[key] = {"value": value, "reason": h["reason"],
                        "origin": "crosscheck"}
        if apply:
            fields[key] = ""  # hallucination-proof: value removed
        n += 1
    if n and apply:
        store.conn.execute(
            "UPDATE statements SET fields_json=? WHERE pair_key=? AND stage=?",
            (json.dumps(fields, ensure_ascii=False), pair_key, stage))
    return n


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", default="results/kg_statements.sqlite")
    parser.add_argument("--endpoint", default="olc")
    parser.add_argument("--apply", action="store_true",
                        help="write flags + blank the suspect values")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    engine = get_engine(readonly=True)
    conn = engine.connect()
    store = KgStore(args.store)
    remote = KgRemote.for_diagnose() or KgRemote(args.endpoint)

    rows = store.conn.execute(
        "SELECT pair_key, reason FROM crosschecks WHERE verdict='failed' ORDER BY rowid"
    ).fetchall()
    if args.limit:
        rows = rows[: args.limit]

    stats = {"pairs": 0, "flagged_fields": 0, "no_diagnosis": 0}
    classes: Counter = Counter()
    ticker = StatusTicker()
    ticker.section("flagfailures")
    for row in rows:
        stats["pairs"] += 1
        ticker.tick(f"pairs={stats['pairs']} flagged={stats['flagged_fields']}")
        pk = row["pair_key"]
        st_row = store.conn.execute(
            "SELECT fields_json, stage FROM statements WHERE pair_key=? "
            "AND stage IN ('request','response') LIMIT 1", (pk,)).fetchone()
        if st_row is None:
            continue
        stage = st_row[1]
        fields = json.loads(st_row[0])
        # skip already-flagged statements
        if "_flags" in fields:
            continue
        docs = store.documents_for_pair(pk)
        role = "response" if stage == "response" else "request"
        keys = [d["doc_key"] for d in docs
                if d["role"] in (role, "modification")]
        src = source_text(conn, keys, cap=6000)
        if not src:
            stats["no_diagnosis"] += 1
            continue
        hits = field_flags(pk, stage, fields, src, remote)
        for h in hits:
            classes[h["mode"]] += 1
        n = flag_statement(store, pk, stage, hits, args.apply)
        stats["flagged_fields"] += n
        if args.apply and stats["pairs"] % 20 == 0:
            store.commit()

    store.commit()
    ticker.tick(f"done: {stats} classes={dict(classes)}", force=True)
    print(json.dumps({"stats": stats, "classes": dict(classes)}, ensure_ascii=False))
    conn.close()
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
