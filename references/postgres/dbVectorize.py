#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import os
from pathlib import Path

from sqlalchemy import MetaData, Table, select, insert, update
from sqlalchemy.engine import Engine

# engine connection (as given)
from sqlalchemy import create_engine

import requests
import json
from typing import List, Dict, Any, Optional

import numpy as np 


# ###############
def embed(text: str) -> List[List[float]]:
    url = "http://localhost:8080/v1/embeddings"
    embed_model = "bge-m3:latest"
    payload = {"model": embed_model, "input": [text]}
    headers = {"Content-Type": "application/json"}
    timeout = 30
    r = requests.post(url, headers=headers, data=json.dumps(payload), timeout=timeout)
    r.raise_for_status()
    data = r.json()
    # if self.DEBUG: print("Embedding: ",data)
    return [item["embedding"] for item in data["data"]]

# ###################
def make_engine(db_url: str) -> Engine:
    return create_engine(db_url, pool_pre_ping=True, future=True)


def run(conn, file_tbl):
    # for all entries in table File: get columns fileName and content. if content is not null get embedding via function embed. add result to vectors[] as with key fileName.split(".")[0] = embedding value
    matched = 0
    updated = 0
    skipped_no_filename = 0
    skipped_no_md = 0
    vectors = []
    files = []
    items = conn.execute(select(file_tbl.c.fileName, file_tbl.c.content)).all()
    items = sorted(items, key=lambda x: (x[0] is None, x[0]))  # sort by fileName, None last
    print(f"Total items in File table: {len(items)}")
    for i,row in enumerate(items):
        if i % 100 == 0:
            print(f"Processing {i}/{len(items)}...")
        fileName, content = row
        if not fileName:
            skipped_no_filename += 1
            continue
        if not content:
            skipped_no_md += 1
            continue
        matched += 1
        name = Path(fileName).stem
        # print("Content",content[:100])
        embedding = embed(content)[0]
        norm = np.linalg.norm(embedding, keepdims=True) + 1e-9
        embedding_normalized = embedding / norm

        #vectors.append({"file": name, "vector": embedding_normalized.tolist()})
        vectors.append(embedding_normalized.astype(float).tolist())
        files.append(name)
        updated += 1

    print("\nSummary")
    print(f"  matched md/files   : {matched}")
    print(f"  updated            : {updated}")
    print(f"  skipped no fileName: {skipped_no_filename}")
    print(f"  skipped no md      : {skipped_no_md}")

    return vectors, files
    


def main() -> None:
    ap = argparse.ArgumentParser(description="Fill Content.plaintext from sums/*.md for File rows.")
    ap.add_argument("-o", "--output", help='Output file')
    args = ap.parse_args()

    import private as pr
    db_url = f"mariadb+pymysql://{pr.DB_USER}:{pr.DB_PWD}@localhost/{pr.DB_NAME}"
    engine = make_engine(db_url)

    metadata = MetaData()
    file_tbl = Table("File", metadata, autoload_with=engine)

    with engine.begin() as conn:
        vectors, files = run(conn, file_tbl)
    if args.output:
        with open(args.output, "wb") as f:
            #json.dump(vectors, f, indent=2)
            # save as npz compressed array
            np.savez_compressed(f, vectors=np.array(vectors, dtype=np.float32), files=np.array(files))
            # np.savez_compressed(f, vectors=np.array(vectors, dtype=np.float32))
        # check output file
        if os.path.exists(args.output):
            print(f"Output saved to {args.output}")
            # load putput file and check length of vectros and files
            with np.load(args.output) as data:
                loaded_vectors = data["vectors"]
                loaded_files = data["files"]
                print(f"Loaded {len(loaded_vectors)} vectors and {len(loaded_files)} files from output.")
        else:
            print(f"Error: Output file {args.output} not found after writing.")


if __name__ == "__main__":
    main()
    