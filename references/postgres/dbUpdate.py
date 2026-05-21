#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import os
from pathlib import Path

from sqlalchemy import MetaData, Table, select, insert, update
from sqlalchemy.engine import Engine

# engine connection (as given)
from sqlalchemy import create_engine


def make_engine(db_url: str) -> Engine:
    return create_engine(db_url, pool_pre_ping=True, future=True)


def iter_md_files(sums_dir: Path, full_dir: Path) -> dict[str, Path]:
    """
    Recursively find all markdown files in a directory and map their stems to their paths.
    
    Args:
        sums_dir (Path): The directory to search for markdown files.
        full_dir (Path): Not used in the current implementation.
    
    Returns:
        dict[str, Path]: A dictionary where keys are markdown file stems (filenames without extension)
                         and values are the full Path objects to those files.
    
    Note:
        The variable `p` in the loop represents the full Path object to each markdown file found.
        It includes the complete file path. The `p.stem` extracts just the filename without the 
        .md extension (e.g., if p is '/path/to/document.md', then p.stem is 'document').
    """
    md_map: dict[str, Path] = {}
    for p in sums_dir.rglob("*.md"):
        if p.is_file():
            full_path = full_dir / p.name
            #print("Full path to check:", full_path)
            if full_path.is_file():
                sums_size = p.stat().st_size
                full_size = full_path.stat().st_size
                if (full_size < 3000) and (full_size < 2 * sums_size):
                    #print(f"Using full_dir file: {full_path} (full: {full_size} bytes, sums: {sums_size} bytes)")
                    md_map[p.stem] = full_path
                else:
                    #print(f"Using sums_dir file: {p.name} (full: {full_size} bytes, sums: {sums_size} bytes)")    
                    md_map[p.stem] = p
            print(f"Using file: {md_map[p.stem]}, size: {md_map[p.stem].stat().st_size} bytes")
            #md_map[p.stem] = p
    return md_map


def normalize_file_basename(file_name: str | None) -> str | None:
    if not file_name:
        return None
    base = os.path.basename(file_name)
    stem, _ = os.path.splitext(base)
    return stem or None


def run(conn, file_tbl, md_map, dry_run: bool) -> None:
    stmt_files = select(file_tbl.c.sid, file_tbl.c.fileName)

    matched = updated = 0
    skipped_no_md = skipped_no_filename = 0

    for file_sid, file_name in conn.execute(stmt_files):
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

    print("\nSummary")
    print(f"  matched md/files   : {matched}")
    print(f"  updated            : {updated}")
    print(f"  skipped no fileName: {skipped_no_filename}")
    print(f"  skipped no md      : {skipped_no_md}")

def main() -> None:
    ap = argparse.ArgumentParser(description="Fill Content.plaintext from sums/*.md for File rows.")
    ap.add_argument("-s", "--sums_dir", help='Directory containing markdown files like "00123456.md"')
    ap.add_argument("-f", "--full_dir", help='Directory containing original files like "00123456.md"')
    ap.add_argument("--dry-run", action="store_true", help="Do not write to DB; just report actions.")
    args = ap.parse_args()

    sums_dir = Path(args.sums_dir).expanduser().resolve()
    if not sums_dir.exists() or not sums_dir.is_dir():
        raise SystemExit(f"sums_dir is not a directory: {sums_dir}")

    full_dir = Path(args.full_dir).expanduser().resolve()
    if not full_dir.exists() or not full_dir.is_dir():
        raise SystemExit(f"full_dir is not a directory: {full_dir}")

    import private as pr
    db_url = f"mariadb+pymysql://{pr.DB_USER}:{pr.DB_PWD}@localhost/{pr.DB_NAME}"
    engine = make_engine(db_url)

    md_map = iter_md_files(sums_dir, full_dir)
    print(f"Found {len(md_map)} markdown files under: {sums_dir}")

    metadata = MetaData()
    file_tbl = Table("File", metadata, autoload_with=engine)

    if args.dry_run:
        # read-only-ish pass; no explicit transaction management needed
        with engine.connect() as conn:
            run(conn, file_tbl, md_map, dry_run=True)
    else:
        # one transaction for all writes; commits automatically on success
        with engine.begin() as conn:
            run(conn, file_tbl, md_map, dry_run=False)


if __name__ == "__main__":
    main()
    