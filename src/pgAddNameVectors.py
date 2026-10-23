
# Dual-mode import support: allow running this file directly as a script
# (``python src/<name>.py``) as well as importing it as ``src.<name>``.
try:
    import _bootstrap  # noqa: F401  (script mode: puts repo root on sys.path)
except ImportError:
    pass
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Utility to update the `content` (plaintext) column of the `File` table
by reading corresponding markdown files, optionally adding embedding vectors.

Migrated to src.  Fixes relative to the original ``src/pgAddNameVectors.py``:
the helper functions it referenced live in ``pgAddSummaries`` and are now
imported from there, the undefined ``Embedding`` model reference (the module
defined ``AgendaEmbedding``/``FileEmbedding`` but used a non-existent
``Embedding``) now targets ``FileEmbedding`` (``contentEmbeddings``), and the
engine/embedding configuration comes from the shared ``src.db``/``src.remote``
layers.
"""

import argparse
import signal
from pathlib import Path

from sqlalchemy import MetaData, Table, select, update, Column, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import declarative_base
from pgvector.sqlalchemy import Vector

# ----------------------------------------------------------------------
# Shared layers
# ----------------------------------------------------------------------
from src.db import get_engine
from src import remote
from src.pgAddSummaries import iter_md_files, normalize_file_basename

# Embedding target tables (own metadata, as in the original script)
Base = declarative_base()


class AgendaEmbedding(Base):
    __tablename__ = "agendaEmbeddings"
    id = Column(Integer, primary_key=True)
    oparlKey = Column(String)
    value = Column(Vector(1024))  # 1024-dimensional vector
    __table_args__ = (UniqueConstraint('oparlKey', name='uq_agenda_embedding_oparlKey'),)


class FileEmbedding(Base):
    __tablename__ = "contentEmbeddings"
    id = Column(Integer, primary_key=True)
    oparlKey = Column(String)
    value = Column(Vector(1024))  # 1024-dimensional vector
    __table_args__ = (UniqueConstraint('oparlKey', name='uq_embedding_oparlKey'),)


def embed(text: str):
    """Generate a normalised embedding for *text* via the shared remote client."""
    return remote.embed(text)


def run(conn, file_tbl, md_map, embeddings: bool = False, dry_run: bool = False,
        embedding_model=FileEmbedding) -> None:
    stmt_files = select(file_tbl.c.sid, file_tbl.c.oparlKey, file_tbl.c.filename)

    matched = updated = 0
    skipped_no_md = skipped_no_filename = 0

    def signal_handler(signum, frame):
        print(f"\n\nInterrupt received. Committing progress to database...")
        print(f"Current progress: {matched} matched, {updated} updated")
        if not dry_run:
            conn.commit()
            print("Progress saved to database.")
        raise KeyboardInterrupt("Graceful shutdown")

    signal.signal(signal.SIGINT, signal_handler)

    for file_sid, oparlKey, file_name in conn.execute(stmt_files):
        if matched % 1000 == 0 and matched > 0:
            print(f"Progress: {matched} items processed...", flush=True)

        base = normalize_file_basename(file_name)
        if not base:
            skipped_no_filename += 1
            continue

        md_path = md_map.get(base)
        if not md_path:
            skipped_no_md += 1
            continue

        matched += 1
        print(f"Reading from file: {md_path} for File.sid={file_sid}, fileName={file_name}")
        text = md_path.read_text(encoding="utf-8", errors="replace")

        if not dry_run:
            conn.execute(
                update(file_tbl)
                .where(file_tbl.c.sid == file_sid)
                .values(content=text)
            )
            updated += 1

            if embeddings:
                try:
                    vec = embed(text)
                    print(f"Generated embedding for {oparlKey}, vector length: {len(vec)}")
                    conn.execute(
                        pg_insert(embedding_model)
                        .values(oparlKey=oparlKey, value=vec)
                        .on_conflict_do_update(
                            index_elements=['oparlKey'], set_={'value': vec}
                        )
                    )
                except Exception as e:
                    print(f"Error embedding content for {oparlKey}: {e}")
                    continue

    print("\nSummary")
    print(f"  matched md/files   : {matched}")
    print(f"  updated            : {updated}")
    print(f"  skipped no fileName: {skipped_no_filename}")
    print(f"  skipped no md      : {skipped_no_md}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Fill File.content from markdown files.")
    ap.add_argument("-s", "--sums_dir", required=True, help='Directory containing markdown files like "00123456.md"')
    ap.add_argument("-f", "--full_dir", required=True, help='Directory containing original files like "00123456.md"')
    ap.add_argument("-e", "--embeddings", action="store_true", help='Add embedding vectors')
    ap.add_argument("-t", "--embeddings-table", choices=["contentEmbeddings", "agendaEmbeddings"],
                    default="contentEmbeddings", help="Target table for embedding vectors")
    ap.add_argument("--dry-run", action="store_true", help="Do not write to DB; just report actions.")
    args = ap.parse_args()

    sums_dir = Path(args.sums_dir).expanduser().resolve()
    if not sums_dir.is_dir():
        raise SystemExit(f"sums_dir is not a directory: {sums_dir}")

    full_dir = Path(args.full_dir).expanduser().resolve()
    if not full_dir.is_dir():
        raise SystemExit(f"full_dir is not a directory: {full_dir}")

    # Shared engine from the centralised DB layer (private.py / env)
    engine = get_engine()

    embedding_model = FileEmbedding if args.embeddings_table == "contentEmbeddings" else AgendaEmbedding
    if args.embeddings:
        # Ensure the embedding table exists if we're adding embeddings
        Base.metadata.create_all(engine)

    md_map = iter_md_files(sums_dir, full_dir)
    print(f"Found {len(md_map)} markdown files under: {sums_dir}")

    metadata = MetaData()
    file_tbl = Table("File", metadata, autoload_with=engine)

    if args.dry_run:
        with engine.connect() as conn:
            run(conn, file_tbl, md_map, embeddings=False, dry_run=True)
    else:
        with engine.begin() as conn:
            run(conn, file_tbl, md_map, embeddings=args.embeddings, dry_run=False,
                embedding_model=embedding_model)


if __name__ == "__main__":
    main()
