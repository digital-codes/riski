
# Dual-mode import support: allow running this file directly as a script
# (``python src/<name>.py``) as well as importing it as ``src.<name>``.
try:
    import _bootstrap  # noqa: F401  (script mode: puts repo root on sys.path)
except ImportError:
    pass
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Utility to update the `content` (plaintext) column of the `File` table
by reading corresponding markdown files.

Migrated to src: the database connection comes from the shared ``src.db``
layer and embeddings are generated via the shared ``src.remote`` client
instead of a hand-rolled requests call against ``private.py`` URLs.
"""

import argparse
import os
import signal
from pathlib import Path
from typing import List, Optional

from sqlalchemy import MetaData, Table, select, update, Column, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import declarative_base, sessionmaker
from pgvector.sqlalchemy import Vector

# ----------------------------------------------------------------------
# Shared layers
# ----------------------------------------------------------------------
from src.db import get_engine
from src import remote

# Define the embedding table (own metadata, as in the original script)
Base = declarative_base()


class Embedding(Base):
    __tablename__ = "contentEmbeddings"
    id = Column(Integer, primary_key=True)
    oparlKey = Column(String)
    value = Column(Vector(1024))  # 1024-dimensional vector
    __table_args__ = (UniqueConstraint('oparlKey', name='uq_embedding_oparlKey'),)


def iter_md_files(sums_dir: Path, full_dir: Path) -> dict[str, Path]:
    """Recursively find markdown files and map their stems to the best match.

    If a matching file exists in ``full_dir`` and is smaller than the one in
    ``sums_dir`` (but still under 3000 bytes and less than twice the size), it
    is preferred. Otherwise the file from ``sums_dir`` is used.
    """
    md_map: dict[str, Path] = {}
    for p in sums_dir.rglob("*.md"):
        if p.is_file():
            full_path = full_dir / p.name
            if full_path.is_file():
                sums_size = p.stat().st_size
                full_size = full_path.stat().st_size
                if (full_size < 3000) and (full_size < 2 * sums_size):
                    md_map[p.stem] = full_path
                else:
                    md_map[p.stem] = p
            else:
                md_map[p.stem] = p
            print(f"Using file: {md_map[p.stem]}, size: {md_map[p.stem].stat().st_size} bytes")
    return md_map


def normalize_file_basename(file_name: str | None) -> str | None:
    if not file_name:
        return None
    base = os.path.basename(file_name)
    stem, _ = os.path.splitext(base)
    return stem or None


# ###############
def embed(text: str):
    """Generate a normalised embedding for *text* via the shared remote client."""
    return remote.embed(text)


def run(conn, file_tbl, md_map, embeddings: bool = False, dry_run: bool = False) -> None:
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
                        pg_insert(Embedding)
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
            run(conn, file_tbl, md_map, embeddings=args.embeddings, dry_run=False)


if __name__ == "__main__":
    main()
