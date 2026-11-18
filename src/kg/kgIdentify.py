"""Discover request/response document pairs from the OParl database.

Stage 1 of the kg pipeline (capability: ``kg-pair-identification``).
Read-only over PostgreSQL via the shared ``src.db`` layer; output goes
into the local SQLite store (``results/kg_statements.sqlite`` by
default).

Identification strategy (design D3, tier 1 = structural):

* Paper.papertype resolves through ``config/kg_vocabulary.yaml`` to a
  request / modification / response class.
* Consultations attached to the paper are joined with their meeting and
  agenda item; only meetings matching the Gemeinderat scope are kept.
* The outcome is normalised from AgendaItem.result / Consultation.role.
* Every pair carries the FULL input-document list (document id, file
  name, role: request / modification / response / attachment) per spec.
* Per candidate a provenance signal and a numeric confidence are stored.

Usage::

    python -m src.kg.kgIdentify --sample 20        # console sample
    python -m src.kg.kgIdentify                    # full run (resumable);
    python -m src.kg.kgIdentify --store path.sqlite --force  # redo pairs
"""

from __future__ import annotations

try:  # script-mode import bootstrap (mirrors src/pg*.py convention)
    import _bootstrap  # noqa: F401
except ImportError:
    pass

import argparse
import sys

from sqlalchemy import text

from src.db import get_engine, get_logger
from src.kg.kgStore import KgStore
from src.kg.kgStatus import StatusTicker
from src.kg.kgVocab import load_vocab, resolve_mapping

log = get_logger("riski.kg.identify")

DEFAULT_STORE = "results/kg_statements.sqlite"

REQUEST_CLASSES = {"request", "modification"}
RESPONSE_CLASSES = {"response"}

# SQL ----------------------------------------------------------------
# structural traversal: papers → consultations → meeting/agenda item
_PAIR_SQL = text(
    """
    SELECT po."oparlId"  AS paper_id,
           po."oparlKey" AS paper_key,
           po.name     AS paper_name,
           po.papertype,
           c."oparlId"   AS consultation_id,
           c.role      AS consultation_role,
           c.authoritative,
           m.sid       AS meeting_sid,
           m."oparlId"   AS meeting_id,
           m.name      AS meeting_name,
           m.start_date AS meeting_date,
           a.sid       AS agenda_sid,
           a."oparlId"   AS agenda_id,
           a.result    AS agenda_result
    FROM "Paper" po
    JOIN "Paper__consultation__Consultation" pc ON pc."srcSid" = po.sid
    JOIN "Consultation" c ON c.sid = pc."tgtSid"
    LEFT JOIN "Meeting" m ON m.sid = c."meetingSid"
    LEFT JOIN "AgendaItem" a ON a.sid = c."agendaItemSid"
    WHERE po.deleted IS NOT TRUE
      AND c.deleted IS NOT TRUE
      AND po.papertype IS NOT NULL
    ORDER BY po.sid, m.start_date NULLS LAST
    """
)

_FILES_SQL = text(
    """
    SELECT f."oparlId"  AS doc_id,
           f."oparlKey" AS doc_key,
           f.name     AS name,
           f.filename  AS filename
    FROM "Paper__auxiliaryFile__File" pf
    JOIN "File" f ON f.sid = pf."tgtSid"
    WHERE pf."srcSid" = :paperSid AND f.deleted IS NOT TRUE
    """
)

_AGENDA_FILES_SQL = text(
    """
    SELECT f."oparlId"  AS doc_id,
           f."oparlKey" AS doc_key,
           f.name     AS name,
           f.filename AS filename
    FROM "AgendaItem__auxiliaryFile__File" af
    JOIN "File" f ON f.sid = af."tgtSid"
    WHERE af."srcSid" = :agendaSid AND f.deleted IS NOT TRUE
    """
)

_CHUNK_COUNT_SQL = text(
    """
    SELECT COUNT(*) FROM "File_chunks" fc
    JOIN "File" f ON f.sid = fc."file_sid"
    WHERE f."oparlKey" = :fileKey
    """
)
def classify_pair(
    papertype: str | None,
    agenda_result: str | None,
    consultation_role: str | None,
    authoritative: bool | None,
    vocab: dict,
) -> tuple[str | None, str | None, float, str]:
    """Return (request_type, outcome, confidence, signal) for one row.

    Signal hierarchy: database columns first (tier 1); name patterns are
    applied only to fill remaining gaps (tier 2), vectors and LLM live
    in later stages (kgTagSystemOne/kgStatements), not here.
    """
    ptype_key, ptype_entry = resolve_mapping(papertype, vocab["papertypes"])
    if ptype_key is None or ptype_entry["class"] not in REQUEST_CLASSES | RESPONSE_CLASSES:
        return None, None, 0.0, "column"

    confidence = 0.5
    outcome = None
    out_key, _ = resolve_mapping(agenda_result, vocab["results"])
    if out_key:
        outcome = out_key
    if agenda_result:
        confidence += 0.2
    if consultation_role and authoritative:
        # a decisive consultation on the right meeting type is the
        # strongest structural signal
        confidence += 0.2
    if agenda_result and consultation_role and authoritative:
        confidence = min(1.0, confidence + 0.1)
        signal = "db-column"
    else:
        signal = "db-partial"

    return ptype_key, outcome, round(confidence, 2), signal


def meeting_in_scope(meeting_name: str | None, vocab: dict) -> bool:
    patterns = vocab["meeting_scope"]["meeting_name_patterns"]
    if not meeting_name:
        return False
    import re

    return any(re.search(p, meeting_name) for p in patterns)


def store_documents(
    conn, store: KgStore, pair_key: str, paper_sid: int, agenda_sid: int | None, paper_class: str
) -> None:
    """Write the FULL input-document list for one pair (spec requirement)."""
    files = conn.execute(_FILES_SQL, {"paperSid": paper_sid}).fetchall()
    for fid, fkey, name, filename in files:
        store.upsert_document(
            pair_key,
            {
                "doc_key": fkey,
                "doc_id": fid,
                "name": name,
                "filename": filename,
                "role": "request" if paper_class == "request" else "modification",
            },
        )
    if agenda_sid:
        for fid, fkey, name, filename in conn.execute(_AGENDA_FILES_SQL, {"agendaSid": agenda_sid}):
            store.upsert_document(
                pair_key,
                {
                    "doc_key": fkey,
                    "doc_id": fid,
                    "name": name,
                    "filename": filename,
                    "role": "response",
                },
            )


def file_chunk_counts(conn, store: KgStore, pair_key: str) -> None:
    """Record per-file chunk counts for the statistics report."""
    rows = store.documents_for_pair(pair_key)
    for row in rows:
        n = conn.execute(
            _CHUNK_COUNT_SQL, {"fileKey": row["doc_key"]}
        ).scalar() or 0
        store.upsert_file_meta(pair_key, row["doc_key"], int(n))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", default=DEFAULT_STORE, help="SQLite output path")
    parser.add_argument("--sample", type=int, default=0, help="only process N candidates")
    parser.add_argument("--force", action="store_true", help="reprocess existing pairs")
    args = parser.parse_args()

    engine = get_engine(readonly=True)
    conn = engine.connect()
    store = KgStore(args.store)
    vocab = load_vocab()
    ticker = StatusTicker()
    ticker.section("identify")

    # resumability: existing pairs are skipped unless --force
    done = set()
    if not args.force:
        done = {r["pair_key"] for r in store.pairs_by_status("identified")}
        done |= {
            r["pair_key"]
            for r in store.conn.execute("SELECT pair_key FROM pairs")
        }

    counts = {"candidates": 0, "pairs": 0, "skipped": 0, "excluded_meeting": 0, "excluded_class": 0}
    for row in conn.execute(_PAIR_SQL):
        counts["candidates"] += 1
        if args.sample and counts["candidates"] > args.sample:
            break
        ptype_key, _ = resolve_mapping(row.papertype, vocab["papertypes"])
        if ptype_key is None:
            counts["excluded_class"] += 1
            continue
        if not meeting_in_scope(row.meeting_name, vocab):
            counts["excluded_meeting"] += 1
            continue
        tik = ticker.tick(
            f"candidates={counts['candidates']} pairs={counts['pairs']}"
        )
        pair_key = f"{row.paper_id}|{row.meeting_id}"
        if pair_key in done:
            counts["skipped"] += 1
            continue

        paper_class = resolve_mapping(row.papertype, vocab["papertypes"])[1]["class"]
        conn2 = conn  # reuse same connection
        paper_sid = conn2.execute(
            text('SELECT sid FROM "Paper" WHERE "oparlId" = :pid'),
            {"pid": row.paper_id},
        ).scalar()
        request_type, outcome, confidence, signal = classify_pair(
            row.papertype,
            row.agenda_result,
            row.consultation_role,
            row.authoritative,
            vocab,
        )
        store.upsert_pair(
            pair_key=pair_key,
            paper_key=row.paper_id,
            meeting_key=row.meeting_id,
            meeting_date=(row.meeting_date.isoformat() if row.meeting_date is not None else None),
            request_type=request_type,
            outcome=outcome,
            confidence=confidence,
            signal=signal,
        )
        store_documents(conn2, store, pair_key, paper_sid, row.agenda_sid, paper_class)
        file_chunk_counts(conn2, store, pair_key)
        counts["pairs"] += 1

    store.commit()
    ticker.tick(
        f"done: {counts['pairs']} pairs, "
        f"{counts['skipped']} skipped (resume), "
        f"{counts['excluded_meeting']} excluded (meeting scope), "
        f"{counts['excluded_class']} excluded (unknown papertype)",
        force=True,
    )
    print(
        f"status distribution: {store.pair_counts_by_status()}",
        file=sys.stderr,
        flush=True,
    )
    conn.close()
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
