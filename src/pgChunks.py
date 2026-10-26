"""pgChunks — chunk-based content processing (change: content-chunking).

Replaces the 8k clip / LLM-summary content layer for oversized documents
(OCR markdown > 8.000 bytes): heading-aware plaintext chunks are stored in
``File_chunks`` and embedded per chunk in ``contentEmbeddings`` (column
``chunk_index``; 0 = single/head vector for small documents, 1..n = chunk
vectors of oversized documents — their old summary vector is replaced).

Design (change: content-chunking): source is ``ko_extracted`` OCR markdown
(NOT ko_sums); chunk boundaries preferred at markdown headings, no overlap;
reranker input becomes the best-matching chunk.
"""

# Dual-mode import support: allow running this file directly as a script
# (``python src/<name>.py``) as well as importing it as ``src.<name>``.
try:
    import _bootstrap  # noqa: F401  (script mode: puts repo root on sys.path)
except ImportError:
    pass

import argparse
import os
from typing import Any, Dict, List, Optional

from sqlalchemy import MetaData, Table, text

from src.db import get_engine, get_logger

logger = get_logger("riski.chunks")

# size cutoff in bytes: markdown files above this are chunked (files at or
# below keep their single embedding, carried as chunk_index = 0)
SIZE_CUTOFF = 8000
# chunk sizing: boundaries preferred at markdown headings when a chunk
# reaches the target; oversized single sections are hard-split at lines
CHUNK_TARGET = 7000
CHUNK_HARD = 8000

FILE_CHUNKS_DDL = """
CREATE TABLE IF NOT EXISTS "File_chunks" (
    file_sid    INTEGER NOT NULL,
    chunk_index INTEGER NOT NULL,
    char_start  INTEGER NOT NULL,
    char_end    INTEGER NOT NULL,
    text        TEXT NOT NULL,
    PRIMARY KEY (file_sid, chunk_index)
)
"""


# ----------------------------------------------------------------------
# chunker
# ----------------------------------------------------------------------
def chunk_markdown(text: str, target: int = CHUNK_TARGET,
                   hard: int = CHUNK_HARD) -> List[Dict[str, Any]]:
    """Split *text* into ordered plaintext chunks of ~``target`` characters.

    Boundaries are preferred at markdown headings (a line starting with
    ``#``); single headings/sections larger than ``hard`` characters are
    hard-split at line boundaries. Each chunk carries its index and the
    character offset range within the original text, so consecutive chunks
    cover the document without gaps or overlaps.

    Returns a list of ``{"chunk_index", "char_start", "char_end", "text"}``.
    """
    if not text:
        return []

    # pass 1: split into blocks — a markdown heading line starts a new block
    lines = text.splitlines(keepends=True)
    blocks: List[List[Any]] = []  # [start_offset, block_text]
    block_start = 0
    cur: List[str] = []
    offset = 0
    for line in lines:
        if line.startswith("#") and cur:
            blocks.append([block_start, "".join(cur)])
            block_start = offset
            cur = []
        cur.append(line)
        offset += len(line)
    if cur:
        blocks.append([block_start, "".join(cur)])

    # pass 2: merge blocks into chunks up to the target; hard-split oversized
    # blocks at line boundaries (keeping the block's absolute offsets)
    chunks: List[Dict[str, Any]] = []
    cur_texts: List[str] = []
    cur_len = 0
    cur_start = 0
    cur_end = 0

    def flush() -> None:
        nonlocal cur_texts, cur_len, cur_start, cur_end
        if not cur_texts:
            return
        chunks.append({
            "chunk_index": len(chunks) + 1,  # chunks are 1..n (0 = single/head vector)
            "char_start": cur_start,
            "char_end": cur_end,
            "text": "".join(cur_texts),
        })
        cur_texts = []
        cur_len = 0

    def emit_piece(piece_start: int, piece_text: str) -> None:
        nonlocal cur_texts, cur_len, cur_start, cur_end
        if cur_texts:
            cur_end = piece_start + len(piece_text)
            cur_texts.append(piece_text)
            cur_len += len(piece_text)
        else:
            cur_start = piece_start
            cur_end = piece_start + len(piece_text)
            cur_texts = [piece_text]
            cur_len = len(piece_text)

    for start, block in blocks:
        if len(block) > hard:
            # oversized block: flush what we have, then split at line bounds;
            # each emitted piece closes its chunk at the hard limit — pieces
            # must never accumulate into one giant chunk
            flush()
            piece_start = start
            piece: List[str] = []
            piece_len = 0
            for line in block.splitlines(keepends=True):
                if piece and piece_len + len(line) > hard:
                    emit_piece(piece_start, "".join(piece))
                    flush()
                    piece_start += len("".join(piece))
                    piece = []
                    piece_len = 0
                piece.append(line)
                piece_len += len(line)
            if piece:
                emit_piece(piece_start, "".join(piece))
                if cur_len >= hard:
                    flush()
            continue

        if cur_texts and cur_len + len(block) > target:
            flush()

        # first block of a fresh chunk may itself push beyond target — accept
        # it (a single block is never split unless oversized) to guarantee
        # progress; the next boundary closes the chunk
        if not cur_texts:
            cur_start = start
        cur_texts.append(block)
        cur_end = start + len(block)
        cur_len += len(block)
        if cur_len >= target:
            flush()

    flush()
    return chunks


# ----------------------------------------------------------------------
# schema
# ----------------------------------------------------------------------
def ensure_tables(engine) -> None:
    """Create ``File_chunks`` and add ``chunk_index`` to contentEmbeddings
    (idempotent). Also migrates the embedding uniqueness from
    ``oparlKey``-only to ``(oparlKey, chunk_index)``."""
    from sqlalchemy import inspect as sa_inspect

    insp = sa_inspect(engine)
    if "contentEmbeddings" not in insp.get_table_names():
        # fresh scratch databases (unit tests) — minimal skeleton; on the
        # real database the table always exists
        with engine.begin() as conn:
            conn.execute(text(
                'CREATE TABLE IF NOT EXISTS "contentEmbeddings" '
                '(id INTEGER PRIMARY KEY, "oparlKey" VARCHAR, value TEXT, '
                'chunk_index INTEGER NOT NULL DEFAULT 0)'))
    emb_cols = {c["name"] for c in insp.get_columns("contentEmbeddings")}
    with engine.begin() as conn:
        conn.execute(text(FILE_CHUNKS_DDL))
        if "chunk_index" not in emb_cols:
            # SQLite (tests) lacks ADD COLUMN IF NOT EXISTS — check first
            conn.execute(text(
                'ALTER TABLE "contentEmbeddings" '
                'ADD COLUMN "chunk_index" INTEGER NOT NULL DEFAULT 0'))
        if engine.dialect.name == "postgresql":
            # legacy uniqueness (oparlKey only) must go — all chunk vectors
            # of one file share the oparlKey; SQLite (unit tests) has no
            # DROP CONSTRAINT syntax and no such constraint anyway
            conn.execute(text(
                'ALTER TABLE "contentEmbeddings" '
                'DROP CONSTRAINT IF EXISTS uq_embedding_oparlKey'))
        conn.execute(text(
            'DROP INDEX IF EXISTS uq_embedding_oparlKey'))
        conn.execute(text(
            'CREATE UNIQUE INDEX IF NOT EXISTS uq_embedding_key_chunk '
            'ON "contentEmbeddings" ("oparlKey", "chunk_index")'))
    logger.info("File_chunks / contentEmbeddings.chunk_index ensured")


def store_chunks(conn, file_sid: int, chunks: List[Dict[str, Any]]) -> int:
    """Replace a file's chunk rows with the given list (idempotent)."""
    conn.execute(text('DELETE FROM "File_chunks" WHERE file_sid = :s'),
                 {"s": file_sid})
    for c in chunks:
        conn.execute(text(
            'INSERT INTO "File_chunks" '
            '(file_sid, chunk_index, char_start, char_end, text) '
            'VALUES (:s, :i, :cs, :ce, :t)'),
            {"s": file_sid, "i": c["chunk_index"], "cs": c["char_start"],
             "ce": c["char_end"], "t": c["text"]})
    return len(chunks)


def chunk_text(conn, oparl_key: str, chunk_index: Optional[int]) -> Optional[str]:
    """Text of a file's best-matching chunk (reranker input). Legacy files
    (no chunk index) yield ``None`` — callers fall back to ``File.content``."""
    if chunk_index is None or chunk_index <= 0:
        return None
    row = conn.execute(text(
        'SELECT fc.text FROM "File_chunks" fc '
        'JOIN "File" f ON f.sid = fc.file_sid '
        'WHERE f."oparlKey" = :k AND fc.chunk_index = :i'),
        {"k": oparl_key, "i": chunk_index}).first()
    return row[0] if row else None


# ----------------------------------------------------------------------
# backfill (task 2)
# ----------------------------------------------------------------------
def iter_oversized_md(directory: str):
    """Markdown files in *directory* above the size cutoff, largest first."""
    entries = []
    for fn in os.listdir(directory):
        if not fn.endswith(".md"):
            continue
        path = os.path.join(directory, fn)
        size = os.path.getsize(path)
        if size > SIZE_CUTOFF:
            entries.append((fn, path, size))
    entries.sort(key=lambda e: e[2], reverse=True)
    return entries


def file_id_by_stem(conn, stem: str) -> Optional[Dict[str, Any]]:
    """File row (sid, oparlKey, filename) for a markdown filename stem.
    File.filename carries an extension (e.g. '00123456.pdf') — match on the
    stem."""
    row = conn.execute(text(
        'SELECT sid, "oparlKey", filename FROM "File" '
        'WHERE filename LIKE :f LIMIT 1'),
        {"f": stem + ".%"}).first()
    if row is None:
        return None
    return {"sid": row[0], "oparlKey": row[1], "filename": row[2]}


def missing_chunk_indexes(conn, oparl_key: str, chunk_indexes: List[int]) -> set:
    """Chunk indexes of *oparl_key* that have no embedding yet."""
    if not chunk_indexes:
        return set()
    rows = conn.execute(text(
        'SELECT chunk_index FROM "contentEmbeddings" '
        'WHERE "oparlKey" = :k AND chunk_index = ANY(:i)'),
        {"k": oparl_key, "i": chunk_indexes}).fetchall()
    return set(chunk_indexes) - {r[0] for r in rows}


def run_backfill(directory: str, limit: Optional[int] = None,
                 dry_run: bool = False, report_path: Optional[str] = None) -> Dict[str, Any]:
    """Chunk + embed all oversized markdown documents (resumable).

    Resume semantics: a document is skipped when all its chunks already have
    embeddings; embedding errors (e.g. remote billing errors with dummy
    responses) leave the chunk missing, so a re-run picks it up. For each
    completed document the superseded legacy single vector (chunk_index = 0,
    embedded from the lossy summary/clipped text) is deleted — chunk vectors
    replace it for retrieval.
    """
    from src import remote

    def embed_batch(texts: List[str]) -> List[Any]:
        """Embed a batch via IONOS (same model, ~5x faster, verified
        cosine-identical to DeepInfra) when configured; DeepInfra fallback
        on any failure. change: content-chunking."""
        try:
            from src import private
            url = getattr(private, "IO_EMB_URL", None)
            key = getattr(private, "IO_EMB_KEY", None)
            model = getattr(private, "IO_EMB_MDL", None)
            if url and key and model:
                import numpy as np
                import requests
                r = requests.post(
                    url,
                    json={"model": model, "input": [t[:8100] for t in texts],
                          "dimensions": 1024},
                    headers={"Authorization": f"Bearer {key}"}, timeout=60)
                r.raise_for_status()
                out: List[Any] = [None] * len(texts)
                for item in r.json()["data"]:
                    arr = np.array(item["embedding"], dtype=np.float64)
                    out[item.get("index", 0)] = arr / (np.linalg.norm(arr) + 1e-9)
                if all(v is not None for v in out):
                    return out
        except Exception as exc:  # noqa: BLE001 - fallback keeps the run going
            logger.warning("IONOS embedding failed (%s) — DeepInfra fallback", exc)
        return remote.embed_batch(texts)

    engine = get_engine()
    ensure_tables(engine)
    entries = iter_oversized_md(directory)
    if limit:
        entries = entries[:limit]

    stats = {"files_total": len(entries), "files_done": 0, "files_skipped_missing": 0,
             "files_skipped_complete": 0, "chunks_total": 0, "chunks_embedded": 0,
             "chunks_missing": 0, "errors": 0}
    lines: List[str] = ["# pgChunks backfill report", ""]
    BATCH = 16  # chunks per embeddings API call (change: content-chunking)

    for fn, path, size in entries:
        stem = fn[:-3]
        try:
            with engine.begin() as conn:
                fid = file_id_by_stem(conn, stem)
                if fid is None:
                    stats["files_skipped_missing"] += 1
                    continue
                stored_idx = [r[0] for r in conn.execute(text(
                    'SELECT chunk_index FROM "File_chunks" WHERE file_sid = :s'),
                    {"s": fid["sid"]}).fetchall()]
                have_missing = missing_chunk_indexes(conn, fid["oparlKey"], stored_idx)
                if stored_idx and not have_missing:
                    # complete already (chunks + all embeddings present)
                    stats["files_skipped_complete"] += 1
                    continue
                if dry_run:
                    stats["files_done"] += 1
                    continue

            text_ = open(path, encoding="utf-8", errors="replace").read()
            chunks = chunk_markdown(text_)
            stats["chunks_total"] += len(chunks)

            with engine.begin() as conn:
                store_chunks(conn, fid["sid"], chunks)
                # content = document head (first chunk), backward compat
                head = chunks[0]["text"] if chunks else text_[:SIZE_CUTOFF]
                conn.execute(text(
                    'UPDATE "File" SET content = :c, "contentKind" = \'chunked\' '
                    'WHERE sid = :s'), {"c": head, "s": fid["sid"]})

            # batched embedding of the chunks that lack a vector
            with engine.connect() as conn:
                todo_idx = sorted(missing_chunk_indexes(
                    conn, fid["oparlKey"], [c["chunk_index"] for c in chunks]))
            by_idx = {c["chunk_index"]: c for c in chunks}

            for batch_start in range(0, len(todo_idx), BATCH):
                batch_idx = todo_idx[batch_start:batch_start + BATCH]
                batch_texts = [by_idx[i]["text"] for i in batch_idx]
                vecs = embed_batch(batch_texts)
                with engine.begin() as conn:
                    for i, vec in zip(batch_idx, vecs):
                        conn.execute(text(
                            'INSERT INTO "contentEmbeddings" ("oparlKey", value, chunk_index) '
                            'VALUES (:k, :v, :i) '
                            'ON CONFLICT ("oparlKey", chunk_index) DO UPDATE SET value = :v'),
                            {"k": fid["oparlKey"],
                             "v": [float(x) for x in vec],  # np.float64 breaks psycopg2
                             "i": i})
                        stats["chunks_embedded"] += 1

            # chunk vectors replace the superseded legacy single vector
            with engine.begin() as conn:
                left = missing_chunk_indexes(
                    conn, fid["oparlKey"], [c["chunk_index"] for c in chunks])
                if not left:
                    conn.execute(text(
                        'DELETE FROM "contentEmbeddings" '
                        'WHERE "oparlKey" = :k AND chunk_index = 0'),
                        {"k": fid["oparlKey"]})
                else:
                    stats["chunks_missing"] += len(left)
            stats["files_done"] += 1
        except Exception as exc:  # noqa: BLE001 - backfill must continue
            stats["errors"] += 1
            logger.warning("backfill error for %s: %s", fn, exc)
            lines.append(f"- ERROR {fn}: {exc}")

    # completeness report (task 2.2)
    with engine.connect() as conn:
        chunked_files = conn.execute(text(
            'SELECT count(DISTINCT file_sid) FROM "File_chunks"')).scalar()
        total_chunks = conn.execute(text('SELECT count(*) FROM "File_chunks"')).scalar()
        missing_vecs = conn.execute(text('''
            SELECT count(*) FROM "File_chunks" fc
            JOIN "File" f ON f.sid = fc.file_sid
            LEFT JOIN "contentEmbeddings" ce
              ON ce."oparlKey" = f."oparlKey" AND ce.chunk_index = fc.chunk_index
            WHERE ce.id IS NULL''')).scalar()
    stats.update({"db_chunked_files": chunked_files, "db_chunks": total_chunks,
                  "db_chunks_missing_vector": missing_vecs})
    lines += [
        f"files in scope : {stats['files_total']}",
        f"files processed: {stats['files_done']} (skipped complete: "
        f"{stats['files_skipped_complete']}, missing file row: "
        f"{stats['files_skipped_missing']})",
        f"chunks in scope: {stats['chunks_total']}, embedded this run: "
        f"{stats['chunks_embedded']}, missing after run: {stats['chunks_missing']}",
        f"db state       : {stats['db_chunked_files']} chunked files, "
        f"{stats['db_chunks']} chunks, {stats['db_chunks_missing_vector']} "
        "missing vectors",
        f"errors         : {stats['errors']}",
    ]
    report = "\n".join(lines)
    print(report)
    if report_path:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report + "\n")
    stats["report"] = report
    return stats


def fix_small_contents(directory: str, dry_run: bool = False,
                       report_path: Optional[str] = None) -> Dict[str, Any]:
    """Reconcile non-chunked documents (< cutoff) with their full markdown
    (change: content-chunking verification finding): files whose
    ``File.content`` differs from the markdown (old LLM summaries,
    truncations) or is NULL get the full plaintext copied and a fresh
    single embedding (chunk_index = 0). Idempotent — identical files are
    skipped.
    """
    from src import private
    from src.remote import embed_batch as remote_embed_batch

    engine = get_engine()
    ensure_tables(engine)
    small: Dict[str, str] = {}
    for fn in os.listdir(directory):
        if fn.endswith(".md"):
            path = os.path.join(directory, fn)
            if os.path.getsize(path) < SIZE_CUTOFF:
                small[fn[:-3]] = path

    def embed_batch(texts: List[str]) -> List[Any]:
        """IONOS first (faster), DeepInfra fallback — same model."""
        try:
            from src import private as p
            url, key, model = (getattr(p, "IO_EMB_URL", None),
                               getattr(p, "IO_EMB_KEY", None),
                               getattr(p, "IO_EMB_MDL", None))
            if url and key and model:
                import numpy as np
                import requests
                r = requests.post(url, json={"model": model,
                                             "input": [t[:8100] for t in texts],
                                             "dimensions": 1024},
                                  headers={"Authorization": f"Bearer {key}"}, timeout=60)
                r.raise_for_status()
                out: List[Any] = [None] * len(texts)
                for item in r.json()["data"]:
                    arr = np.array(item["embedding"], dtype=np.float64)
                    out[item.get("index", 0)] = arr / (np.linalg.norm(arr) + 1e-9)
                if all(v is not None for v in out):
                    return out
        except Exception as exc:  # noqa: BLE001
            logger.warning("IONOS embedding failed (%s) — DeepInfra fallback", exc)
        return remote_embed_batch(texts)

    conn = engine.connect()
    stats = {"files_total": len(small), "identical": 0, "fixed_content": 0,
             "embedded": 0, "no_file_row": 0, "errors": 0}
    rows = conn.execute(text(
        'SELECT sid, "oparlKey", filename FROM "File"')).fetchall()
    by_stem = {r.filename.rsplit(".", 1)[0]: r.oparlKey
               for r in rows if r.filename}
    conn.close()

    keys = [(stem, by_stem[stem]) for stem in small if stem in by_stem]
    stats["no_file_row"] = len(small) - len(keys)

    conn = engine.connect()
    try:
        for i in range(0, len(keys), 500):
            batch = keys[i:i + 500]
            oparl_keys = [k[1] for k in batch]
            contents = dict(conn.execute(text(
                'SELECT "oparlKey", content FROM "File" WHERE "oparlKey" = ANY(:k)'),
                {"k": oparl_keys}).fetchall())
            fixes: List[Dict[str, Any]] = []
            for stem, oparlKey in batch:
                content = contents.get(oparlKey)
                md_text = open(small[stem], encoding="utf-8",
                               errors="replace").read()
                if content == md_text:
                    stats["identical"] += 1
                    continue
                fixes.append({"oparlKey": oparlKey, "text": md_text})
            if dry_run:
                stats["fixed_content"] += len(fixes)
                continue
            for fx in fixes:
                try:
                    with engine.begin() as conn2:
                        conn2.execute(text(
                            'UPDATE "File" SET content = :c, '
                            '"contentKind" = \'fulltext\' WHERE "oparlKey" = :k'),
                            {"c": fx["text"], "k": fx["oparlKey"]})
                    vec = embed_batch([fx["text"]])[0]
                    with engine.begin() as conn2:
                        conn2.execute(text(
                            'INSERT INTO "contentEmbeddings" '
                            '("oparlKey", value, chunk_index) VALUES (:k, :v, 0) '
                            'ON CONFLICT ("oparlKey", chunk_index) DO UPDATE '
                            'SET value = :v'),
                            {"k": fx["oparlKey"], "v": [float(x) for x in vec]})
                    stats["fixed_content"] += 1
                    stats["embedded"] += 1
                except Exception as exc:  # noqa: BLE001 - continue on error
                    stats["errors"] += 1
                    logger.warning("fix-small error for %s: %s",
                                   fx["oparlKey"], exc)
    finally:
        conn.close()

    lines = [
        f"small md files          : {stats['files_total']}",
        f"identical (untouched)   : {stats['identical']}",
        f"fixed (content + vector): {stats['fixed_content']}",
        f"embedded                : {stats['embedded']}",
        f"no File row (orphans)   : {stats['no_file_row']}",
        f"errors                  : {stats['errors']}",
    ]
    report = "\n".join(lines)
    print(report)
    if report_path:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report + "\n")
    stats["report"] = report
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Chunk + embed oversized OCR markdown documents (resumable).")
    ap.add_argument("-d", "--directory", default="/mnt_ai/data/odd26/ris/ko_extracted")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--report", default=None, help="write the completeness report here")
    ap.add_argument("--fix-small", action="store_true",
                    help="reconcile NON-chunked (<cutoff) documents: copy full "
                         "markdown into File.content where it differs/NULL and "
                         "(re)embed the single vector")
    args = ap.parse_args()
    if args.fix_small:
        fix_small_contents(args.directory, dry_run=args.dry_run,
                           report_path=args.report)
    else:
        run_backfill(args.directory, limit=args.limit, dry_run=args.dry_run,
                     report_path=args.report)

if __name__ == "__main__":
    main()

