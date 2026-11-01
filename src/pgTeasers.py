#!/usr/bin/env python3
"""
pgTeasers.py - Generate document teasers using the shared remote LLM client

Usage:
    python src/pgTeasers.py -c 10
    python src/pgTeasers.py -c 50 -l en --force
    python src/pgTeasers.py -c 10 --model <model-name>

The database connection resolves through the shared ``src.db`` layer
(private.py -> env -> defaults) and LLM calls go through ``src.remote`` —
teasers use the configured **summary** model (``SUMMARY_URL``/``SUMMARY_MDL``,
legacy ``LLM_URL``/``LLM_MDL`` names honoured) unless ``--model`` overrides it
for one run.

Teaser generation is chunk-aware (change: fix-result-summarizer): chunked
documents are summarized map-reduce style — per-chunk pre-summaries are
reduced into the single document teaser — so the teaser covers the whole
document, not just its head chunk. Every storage path caps the teaser at
120% of the maximum chunk size (~9.600 chars), because teasers are consumed
as summarizer context.

Change: teasers-cli-parity — connection/LLM parity with the other backfill
scripts (no more psycopg2/requests boilerplate, no `-u`/`-p` flags).
"""

import argparse
import sys

# Dual-mode import support: allow running this file directly as a script
# (``python src/<name>.py``) as well as importing it as ``src.pgTeasers``.
try:
    import _bootstrap  # noqa: F401  (script mode: puts repo root on sys.path)
except ImportError:
    pass

from sqlalchemy import inspect, text

from src.db import get_engine
from src import remote

DEFAULT_MAX_LEN = 200
TEXT_EXCERPT_MAXLEN = 16000
SUMMARY_TEMP = 0.2
# teaser length ceiling (change: fix-result-summarizer): teasers are punted
# into the summarizer, so they must not exceed the max chunk size by a
# large factor — 120% of the chunk hard limit.
MAX_CHUNK_CHARS = int(__import__("os").environ.get("RISKI_CHUNK_HARD", "8000"))
TEASER_CEILING = int(MAX_CHUNK_CHARS * 1.2)
# map-reduce pre-summary budget per chunk (change: fix-result-summarizer)
CHUNK_PRE_SUMMARY_WORDS = 40
# remote.chat returns this placeholder as a last resort (e.g. offline tests)
_DUMMY_CONTENT = "[dummy response]"


def parse_args():
    p = argparse.ArgumentParser(description="Generate document teasers using the shared remote LLM client")
    p.add_argument("-c", "--count", type=int, default=None, help="number of files to process")
    p.add_argument("-l", "--lang", default="de", help="language for teaser (de=German, en=English)")
    p.add_argument("--ids", type=str, nargs='*', default=[], help="file ids")
    p.add_argument("--oparlid", type=str, default=None, help="process only files where column oparlKey equals this value")
    p.add_argument("--force", action="store_true", help="overwrite existing teaser")
    p.add_argument("--chunked-only", action="store_true",
                   help="process only chunked documents (File_chunks rows exist) — "
                        "targeted backfill of head-only teasers (change: fix-result-summarizer)")
    p.add_argument("-m", "--model", default=None,
                   help="LLM model for this run (default: configured summary model via src.remote)")
    p.add_argument("--max-bar", type=int, default=50, help="progress bar width")
    return p.parse_args()


def _cap_teaser(teaser):
    """Enforce the teaser length ceiling on every storage path (change:
    fix-result-summarizer): teasers are summarizer context and must not
    exceed the max chunk size by a large factor."""
    return (teaser or "")[:TEASER_CEILING]


def make_request(text, lang="de", maxlen=DEFAULT_MAX_LEN, model=None):
    """One LLM call via the shared remote client (change: teasers-cli-parity).

    Retry/backoff/429 handling lives in ``src.remote``. Returns the response
    content trimmed to *maxlen* words, or ``None`` on failure (empty content
    or the shared client's dummy placeholder)."""
    lang_map = {"de": "German", "en": "English"}
    lang_setting = lang_map.get(lang.lower(), "German")

    prompt = f"""Summarize this document in 3-5 sentences.
    Maximum {maxlen} words. Focus on main topic.
    Language must be: {lang_setting} (do not mix languages)
    """
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"Document text: {text[:TEXT_EXCERPT_MAXLEN] if len(text) > TEXT_EXCERPT_MAXLEN else text}"},
    ]
    result = remote.chat(messages, model=model, temperature=SUMMARY_TEMP)
    response = (result.get("content") or "").strip()
    if not response or response == _DUMMY_CONTENT:
        return None
    response = response.strip('"""') if response.startswith('"') else response
    if response and len(response.split()) > maxlen:
        response = ' '.join(response.split()[:maxlen])
    return response.strip()


def get_chunk_texts(conn, oparl_key):
    """All chunk texts of a chunked document, in chunk order; ``None`` when
    the document has no chunk rows (non-chunked)."""
    rows = conn.execute(
        text('SELECT fc.text FROM "File_chunks" fc '
             'JOIN "File" f ON f.sid = fc.file_sid '
             'WHERE f."oparlKey" = :k ORDER BY fc.chunk_index'),
        {"k": oparl_key}).fetchall()
    texts = [r[0] for r in rows if r[0]]
    return texts or None


def summarize_to_teaser(text, lang="de", model=None):
    """Summarize document text into a teaser (single call, existing prompt
    and fallback truncation) — ceiling-capped."""
    text = text or ""
    words = text.split()
    if len(words) <= DEFAULT_MAX_LEN:
        return _cap_teaser(text.replace('\n', ' '))
    result = make_request(text, lang, DEFAULT_MAX_LEN, model=model)
    if result and len(result.split()) > 1:
        teaser = result
        if len(teaser.split()) > DEFAULT_MAX_LEN:
            teaser = ' '.join(teaser.split()[:DEFAULT_MAX_LEN])
    else:
        teaser = text[:TEXT_EXCERPT_MAXLEN].replace('\n', ' ')
    return _cap_teaser(teaser)


def generate_chunked_teaser(chunk_texts, lang="de", model=None):
    """Aggressive map-reduce teaser for chunked documents (change:
    fix-result-summarizer): per-chunk pre-summaries reduced into the ONE
    document teaser. A chunk whose pre-summary call fails contributes a
    truncated text head instead — the document still gets a teaser. The
    reduce call always runs (pre-summaries are bullets, never the teaser);
    when it fails the concatenated pre-summaries serve as the teaser."""
    pre = []
    for i, chunk in enumerate(chunk_texts, 1):
        s = make_request(chunk, lang, CHUNK_PRE_SUMMARY_WORDS, model=model)
        if s and len(s.split()) > 1:
            pre.append(s.strip())
        else:
            sys.stderr.write(f"  chunk {i}/{len(chunk_texts)}: pre-summary failed, using text head\n")
            pre.append(' '.join((chunk or "").split()[:CHUNK_PRE_SUMMARY_WORDS * 2]))
        print(f"    chunk {i}/{len(chunk_texts)}: {len(s or '')} chars")
    reduction_input = "\n".join(f"- {p}" for p in pre if p)
    result = make_request(reduction_input, lang, DEFAULT_MAX_LEN, model=model)
    if result and len(result.split()) > 1:
        teaser = result
        if len(teaser.split()) > DEFAULT_MAX_LEN:
            teaser = ' '.join(teaser.split()[:DEFAULT_MAX_LEN])
    else:
        teaser = " ".join(pre)
    return _cap_teaser(teaser)


def main():
    args = parse_args()
    files = []
    idset = set(int(i.strip()) for i in args.ids) if args.ids else set()
    count = args.count

    print(f"Connecting via shared src.db layer (language: {args.lang}, model: {args.model or 'configured summary model'})...")

    try:
        engine = get_engine()
        with engine.connect() as conn:
            # schema guard: ensure the teaser column exists
            if "teaser" not in {c["name"] for c in inspect(engine).get_columns("File")}:
                print("  Attempting to add teaser column...")
                conn.execute(text('ALTER TABLE "File" ADD COLUMN IF NOT EXISTS teaser TEXT'))
                conn.commit()

            # change: unify-file-content-in-chunks — File_chunks is the single
            # text store: select files that HAVE chunk text (chunk 0 = the
            # complete small document, 1..n = chunks of oversized ones)
            where_clauses = ['EXISTS (SELECT 1 FROM "File_chunks" fc '
                             'JOIN "File" f2 ON f2.sid = fc.file_sid '
                             'WHERE f2.id = "File".id)']
            query_params = {}

            # Filter out files with existing teasers before processing if not forcing.
            if not args.force:
                where_clauses.append("(teaser IS NULL OR LENGTH(teaser) = 0)")

            # Keep exact case in column name: "oparlKey".
            if args.oparlid is not None:
                where_clauses.append('"oparlKey" = :oparlid')
                query_params["oparlid"] = args.oparlid

            # targeted backfill: only chunked documents (change: fix-result-summarizer)
            if args.chunked_only:
                where_clauses.append(
                    'EXISTS (SELECT 1 FROM "File_chunks" fc WHERE fc.file_sid = "File".sid)')

            # change: unify-file-content-in-chunks — order by the document's
            # chunk text length (File.content is retired)
            query = (
                'SELECT id, "oparlKey", COALESCE((SELECT sum(length(fc.text)) '
                'FROM "File_chunks" fc WHERE fc.file_sid = "File".sid), 0) AS total_len '
                f'FROM "File" WHERE {" AND ".join(where_clauses)} ORDER BY total_len DESC'
            )
            rows = conn.execute(text(query), query_params).fetchall()
            files = [tuple(r) for r in rows]

            if idset:
                files = [f for f in files if f[0] in idset]

            limit = min(count, len(files)) if count else len(files)
            files = files[:limit]

            print(f"\nProcessing {len(files)} documents... (language: {args.lang})")
            if not args.force:
                print("(filtered: only files without existing teaser)")
            if args.oparlid is not None:
                print(f"(filtered: only files with oparlKey='{args.oparlid}')")
            print("=" * 60)

            processed = 0
            updated = 0
            skipped_api = 0
            total = len(files)

            for i, (file_id, oparl_key, total_len) in enumerate(files):

                # change: unify-file-content-in-chunks — ALL text comes from
                # File_chunks (chunk 0 = the complete small document, 1..n =
                # chunks of oversized ones); the map-reduce path covers every
                # document so the single teaser covers the whole text.
                chunk_texts = get_chunk_texts(conn, oparl_key)
                if not chunk_texts:
                    print(f"\n[{i+1:3d}] File #{file_id}: no chunk text, skipping")
                    skipped_api += 1
                    continue

                text_joined = "\n".join(chunk_texts)
                word_count = len(text_joined.split())
                if word_count <= DEFAULT_MAX_LEN:
                    # tiny documents keep their verbatim-text teaser
                    print(f"\n[{i+1:3d}] File #{file_id} ({oparl_key}): short ({word_count} words)")
                    teaser = _cap_teaser(text_joined.replace('\n', ' '))
                else:
                    print(f"\n[{i+1:3d}] File #{file_id} ({oparl_key}): "
                          f"{len(chunk_texts)} chunks ({total_len} bytes) [l={args.lang}]...")
                    teaser = generate_chunked_teaser(chunk_texts, args.lang, model=args.model)
                    if not teaser:
                        print("  API failed permanently after retries")
                        skipped_api += 1
                        continue

                print(f"  {len(teaser)} chars, {len(str(teaser).split())} words")
                preview = str(teaser)[:40] + "..." if len(str(teaser)) > 40 else (str(teaser) or "None")
                print(f"  Preview: {preview}")

                try:
                    conn.execute(text('UPDATE "File" SET teaser = :t WHERE id = :i'),
                                 {"t": _cap_teaser(teaser), "i": file_id})
                    updated += 1

                    conn.commit()
                    processed += 1
                except Exception as e:
                    print(f"  Failed to update file #{file_id}: {e}")
                    # aborted transaction must be rolled back — otherwise every
                    # following statement fails with InFailedSqlTransaction
                    conn.rollback()

                pct = int(100 * processed / total) if total > 0 else 0
                bar = '#' * int(50 * processed / total) if total > 0 else '#' * 50
                bar += '.' * (50 - len(bar))
                sys.stdout.write(f'\r[{bar}] {processed:3d}/{total:3d} ({pct:3d}%)')
                sys.stdout.flush()

            sys.stdout.write('\n')
            print(f"\nDone: {processed} processed, {updated} updated, {skipped_api} skipped (API failures)")
            print(f"==========================")

    except KeyboardInterrupt:
        print("\nInterrupted")
    except Exception as e:
        sys.stderr.write(f"Fatal error: {e}\n")
        import traceback
        sys.stderr.write(traceback.format_exc())


if __name__ == "__main__":
    main()
