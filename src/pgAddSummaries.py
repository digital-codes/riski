#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Utility to update the `content` (plaintext) column of the `File` table
by reading corresponding markdown files.

This is a PostgreSQL adaptation of the MySQL/MariaDB version found at
`references/postgres/dbUpdate.py`. The logic is identical – it maps markdown
files to `File` rows and updates the `content` field – but the database
connection uses a PostgreSQL URL and the SQLAlchemy engine is created with the
PostgreSQL dialect.
"""

import argparse
import os
from pathlib import Path
from unittest.mock import Base

from requests.sessions import session
from sqlalchemy import MetaData, Table, select, update
from sqlalchemy.engine import Engine
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, sessionmaker

from sqlalchemy import Column, Integer, String, func, text, desc, inspect, UniqueConstraint
from sqlalchemy.orm import declarative_base

import numpy as np
from pgvector.sqlalchemy import Vector


import requests
import json
import time
from typing import List, Dict, Any, Optional


EMBED_URL: Optional[str] = None
EMBED_MDL: Optional[str] = None
EMBED_API_KEY: Optional[str] = None

# Define the embedding table
Base = declarative_base()

class Embedding(Base):
    __tablename__ = "contentEmbeddings"
    id = Column(Integer, primary_key=True)
    oparlKey = Column(String)
    value = Column(Vector(1024))  # 1024-dimensional vector
    __table_args__ = (UniqueConstraint('oparlKey', name='uq_embedding_oparlKey'),)



def make_engine(db_url: str) -> Engine:
    """Create a SQLAlchemy Engine for the given database URL.

    The URL should be a PostgreSQL connection string, e.g.:
    ``postgresql+psycopg2://user:pwd@localhost/dbname``.
    """
    return create_engine(db_url, pool_pre_ping=True, future=True)


def iter_md_files(sums_dir: Path, full_dir: Path) -> dict[str, Path]:
    """Recursively find markdown files and map their stems to the best match.
    Args:
        sums_dir: Directory containing summary markdown files.
        full_dir: Directory containing original/full files to compare against.

    Returns:
        A dictionary mapping file stems to their optimal Path objects.
    If a matching file exists in ``full_dir`` and is smaller than the one in
    ``sums_dir`` (but still under 3000 bytes and less than twice the size), it
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
def embed(text: str) -> List[List[float]]:
    """Generate embeddings for the given text using the configured embedding model.
        With local llamacp call like so to get context and batch size large enough for long documents: 
            llama-server -m /opt/llama/models/bge-m3-Q4_K_M.gguf --embeddings --port 8085 -c 8192 -ub 8192
    Args:
        text (str): The input text to be embedded.

    Returns:
        List[List[float]]: A list of embeddings, each represented as a list of floats.
    """
    url = EMBED_URL
    embed_model = EMBED_MDL
    payload = {"model": embed_model, "input": [text]}
    headers = {"Content-Type": "application/json"}
    if EMBED_API_KEY != None:
        headers["Authorization"] = f"Bearer {EMBED_API_KEY}"
    timeout = 30
    max_retries = 3
    retry_count = 0
    while retry_count < max_retries:
        #print(f"Requesting embedding at {url},{headers},{payload}")
        r = requests.post(url, headers=headers, json=payload, timeout=timeout)

        #print(f"Received response with status code {r.status_code}")

        if r.status_code == 429:
            retry_count += 1
            if retry_count < max_retries:
                delay = int(r.headers.get("Retry-After", 2 ** retry_count))
                print(f"Rate limited (429). Retrying in {delay} seconds... (attempt {retry_count}/{max_retries})")
                time.sleep(delay)
                continue
            else:
                r.raise_for_status()
        
        r.raise_for_status()
        result = r.json()
        embedding =  result["data"][0]["embedding"] if "data" in result and len(result["data"]) > 0 and "embedding" in result["data"][0] else None
        if embedding is None:
            raise ValueError(f"Unexpected response format: {result}")
        norm = np.linalg.norm(embedding, keepdims=True) + 1e-9
        vector = embedding / norm

        # if self.DEBUG: print("Embedding: ",data)
        return vector



def run(conn, file_tbl, md_map, embeddings: bool = False, dry_run: bool = False) -> None:
    stmt_files = select(file_tbl.c.sid, file_tbl.c.oparlKey, file_tbl.c.filename)

    matched = updated = 0
    skipped_no_md = skipped_no_filename = 0

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
                    embedding = Embedding(oparlKey=oparlKey, value=vec)
                    print(f"Generated embedding for {oparlKey}, vector length: {len(vec)}")
                    conn.execute(
                        pg_insert(Embedding).values(oparlKey=embedding.oparlKey, value=embedding.value).on_conflict_do_update(index_elements=['oparlKey'], set_={'value': embedding.value})
                    )
                except Exception as e:
                    print(f"Error embedding content for {oparlKey}: {e}")
                    continue

        #if matched >= 10:
        #    break

    print("\nSummary")
    print(f"  matched md/files   : {matched}")
    print(f"  updated            : {updated}")
    print(f"  skipped no fileName: {skipped_no_filename}")
    print(f"  skipped no md      : {skipped_no_md}")


def main() -> None:
    global EMBED_URL, EMBED_MDL, EMBED_API_KEY
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

    import private as pr
    # PostgreSQL connection – mirrors the pattern used in dbPgGen.py
    db_url = f"postgresql+psycopg2://{pr.DB_USER}:{pr.DB_PWD}@localhost/{pr.DB_NAME}"
    engine = make_engine(db_url)
    
    if args.embeddings:
        # Ensure the embedding table exists if we're adding embeddings
        Base.metadata.create_all(engine)
        EMBED_URL = pr.EMB_URL
        EMBED_MDL = pr.EMB_MDL
        EMBED_API_KEY = pr.EMB_KEY

    md_map = iter_md_files(sums_dir, full_dir)  # Limit to first 10 for testing; remove slice for full run
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
