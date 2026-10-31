#!/usr/bin/env python3
"""Migrate File.content into File_chunks (change: unify-file-content-in-chunks).

File_chunks becomes the single store of document text:

- files with contentKind fulltext/summary and no chunk rows get their
  File.content text written as a single chunk at chunk_index = 0 — the
  existing contentEmbeddings row at (oparlKey, chunk_index=0) keeps
  matching, so NO vector is recomputed or lost;
- chunked files need no modification (their File.content duplicates
  chunk 1);
- with --retire-content, File.content is set to NULL for ALL non-null
  rows (run only AFTER verification passed).

Idempotent: re-runs skip files that already have chunk rows.

Usage:
    python3 scripts/migrate_content_to_chunks.py            # backfill + checks
    python3 scripts/migrate_content_to_chunks.py --retire-content
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from sqlalchemy import text

from src.db import get_engine

REPORT_DIR = REPO / "results"


def preflight(conn) -> dict:
    """Row counts per contentKind (when the column still exists), chunk
    and embedding coverage."""
    kinds = {}
    try:
        kinds = {k: n for k, n in conn.execute(text(
            'SELECT COALESCE("contentKind", \'null\'), count(*) FROM "File" GROUP BY 1')).all()}
    except Exception:  # noqa: BLE001 - column is dropped by the retire step
        conn.rollback()
    return {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "kinds": kinds,
        "chunks_total": conn.execute(text('SELECT count(*) FROM "File_chunks"')).scalar(),
        "embeddings_total": conn.execute(text('SELECT count(*) FROM "contentEmbeddings"')).scalar(),
        "files_with_content": conn.execute(
            text('SELECT count(*) FROM "File" WHERE content IS NOT NULL')).scalar(),
        "files_without_chunks": conn.execute(text(
            'SELECT count(*) FROM "File" f WHERE f.content IS NOT NULL '
            'AND NOT EXISTS (SELECT 1 FROM "File_chunks" fc WHERE fc.file_sid = f.sid)')).scalar(),
    }
    return stats


def backfill(conn) -> dict:
    """Insert chunk-0 rows for content-bearing files without chunks.
    Embeddings are NOT touched — (oparlKey, chunk_index=0) keys keep
    matching the new rows. Empty-string content rows are included too
    (they carry a legacy vector with no retrievable text — the chunk row
    keeps the embedding↔chunk mapping intact; document_text yields None
    for them, as the empty content did before)."""
    result = conn.execute(text('''
        INSERT INTO "File_chunks" (file_sid, chunk_index, char_start, char_end, text)
        SELECT f.sid, 0, 0, length(f.content), f.content
        FROM "File" f
        WHERE f.content IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM "File_chunks" fc WHERE fc.file_sid = f.sid)
        ON CONFLICT (file_sid, chunk_index) DO NOTHING
    '''))
    return {"chunks_inserted": result.rowcount}


def integrity_checks(conn) -> dict:
    """Every content embedding must have a matching chunk row; sample
    text-equality between the (pre-retirement) content column and chunk 0
    for migrated files."""
    missing_chunk_for_vec = conn.execute(text('''
        SELECT count(*) FROM "contentEmbeddings" ce
        JOIN "File" f ON f."oparlKey" = ce."oparlKey"
        WHERE NOT EXISTS (SELECT 1 FROM "File_chunks" fc
                          WHERE fc.file_sid = f.sid AND fc.chunk_index = ce.chunk_index)
    ''')).scalar()
    files_without_any_chunk_but_vec = conn.execute(text('''
        SELECT count(DISTINCT ce."oparlKey") FROM "contentEmbeddings" ce
        WHERE NOT EXISTS (SELECT 1 FROM "File_chunks" fc
                          JOIN "File" f ON f.sid = fc.file_sid
                          WHERE f."oparlKey" = ce."oparlKey")
    ''')).scalar()
    text_mismatch_sample = 0
    sample = conn.execute(text('''
        SELECT f."oparlKey", f.content, fc.text FROM "File" f
        JOIN "File_chunks" fc ON fc.file_sid = f.sid AND fc.chunk_index = 0
        WHERE f.content IS NOT NULL AND fc.chunk_index = 0
        ORDER BY random() LIMIT 200
    ''')).all()
    for key, content, chunk0 in sample:
        if (content or "") != (chunk0 or ""):
            text_mismatch_sample += 1
    return {
        "embeddings_without_chunk_row": missing_chunk_for_vec,
        "files_with_vec_but_no_chunks": files_without_any_chunk_but_vec,
        "sampled_text_mismatches": text_mismatch_sample,
        "sample_size": len(sample),
    }


def retire_content(conn) -> int:
    """Null File.content for ALL rows (chunked files' content merely
    duplicates chunk 1). Only run AFTER verification passed. Also drops
    the legacy contentKind column + index (storage-mode provenance, no
    remaining consumer — change: unify-file-content-in-chunks)."""
    result = conn.execute(text('UPDATE "File" SET content = NULL WHERE content IS NOT NULL'))
    conn.execute(text('DROP INDEX IF EXISTS idx_file_contentkind'))
    conn.execute(text('ALTER TABLE "File" DROP COLUMN IF EXISTS "contentKind"'))
    return result.rowcount


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--retire-content", action="store_true",
                    help="NULL File.content for all rows (AFTER verification)")
    args = ap.parse_args()

    # the migration writes — use the read/write engine (pgTimeline's
    # get_db_session is the read-only role)
    engine = get_engine(readonly=False)
    out: dict = {"mode": "retire" if args.retire_content else "backfill"}
    with engine.connect() as conn:
        out["preflight"] = preflight(conn)
        if args.retire_content:
            out["retired_rows"] = retire_content(conn)
        else:
            out["backfill"] = backfill(conn)
        out["integrity"] = integrity_checks(conn)
        out["postflight"] = preflight(conn)
        conn.commit()

    ok = out["integrity"]["embeddings_without_chunk_row"] == 0 \
        and out["integrity"]["files_with_vec_but_no_chunks"] == 0
    REPORT_DIR.mkdir(exist_ok=True)
    report = REPORT_DIR / f"content-unification-{out['mode']}-{datetime.now():%Y%m%d-%H%M%S}.json"
    report.write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps(out, indent=1, default=str))
    print(f"\nreport: {report}")
    if not ok:
        print("INTEGRITY CHECK FAILED — do not retire File.content!")
        sys.exit(1)
    print("integrity checks OK")


if __name__ == "__main__":
    main()
