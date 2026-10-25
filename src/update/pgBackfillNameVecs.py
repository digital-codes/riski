"""Backfill `{item}_name_vecs` tables for hybrid search (task 4.1).

Resume-safe: items already present in a table's name-vecs are skipped, so
the run can be interrupted and restarted (e.g. overnight) without redoing
work. Embedding goes through ``src.remote.embed`` which honours
``Retry-After`` on HTTP 429; a small inter-request pause keeps us friendly
to the deepinfra rate limits.

Usage:
    python3 src/pgBackfillNameVecs.py                 # all tables, no limit
    python3 src/pgBackfillNameVecs.py -t Meeting -c 100
    python3 src/pgBackfillNameVecs.py --tables Paper File
"""

# Dual-mode import support.
try:
    import _bootstrap  # noqa: F401  (script mode: puts repo root on sys.path)
except ImportError:
    pass

import argparse
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from sqlalchemy import MetaData, Table, select

from src.db import get_engine
from src.update.pgNameVecs import NameVecs

# Smallest table first for an early complete win; File last (largest).
DEFAULT_TABLES = ["Meeting", "Paper", "AgendaItem", "File"]
PAUSE_SECONDS = 0.05


def run_table(engine, table: str, count: int | None, pause: float, workers: int = 1) -> None:
    metadata = MetaData()
    tbl = Table(table, metadata, autoload_with=engine)
    nv = NameVecs(table, engine=engine)

    with engine.connect() as conn:
        existing = {r[0] for r in conn.execute(select(nv._vec_table.c.oparl_key))}
        rows = conn.execute(select(tbl.c.oparlKey, tbl.c.name).where(tbl.c.name.isnot(None))).all()

    # Names are embedded RAW — the stop-term list must stay decoupled from
    # stored vectors (changing the list must not invalidate embeddings).
    # Non-discriminative terms are handled on the search side: the query
    # is stripped before its vector is computed (see pgTimeline /
    # pgHybridSearch design decision 6).
    todo = [(k, n) for k, n in rows if k not in existing]
    if count:
        todo = todo[:count]
    print(f"[{table}] {len(rows)} items, {len(existing)} already embedded, {len(todo)} to do "
          f"(workers={workers})", flush=True)

    done = failed = 0
    lock = threading.Lock()
    t0 = time.time()

    def embed_one(i: int, item) -> None:
        nonlocal done, failed
        oparl_key, name = item
        try:
            nv.upsert(oparl_key, name)
            status = "ok"
        except Exception as exc:  # noqa: BLE001 - keep the backfill running
            failed += 1
            print(f"[{table}] ERROR {oparl_key}: {exc}", flush=True)
            status = "failed"
        with lock:
            done += 1
            if done % 50 == 0 or done == len(todo):
                rate = done / max(time.time() - t0, 1e-9)
                eta = (len(todo) - done) / rate if rate > 0 else 0
                print(f"[{table}] {done}/{len(todo)} failed={failed} "
                      f"rate={rate:.1f}/s eta={eta/60:.1f}min", flush=True)

    if workers <= 1:
        for i, item in enumerate(todo, 1):
            embed_one(i, item)
            time.sleep(pause)
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(embed_one, i, item) for i, item in enumerate(todo, 1)]
            for f in as_completed(futures):
                f.result()
    print(f"[{table}] finished: {done} embedded, {failed} failed", flush=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Backfill name-vector tables")
    ap.add_argument("--tables", "-t", nargs="*", default=DEFAULT_TABLES,
                    help="Item tables to backfill (default: %(default)s)")
    ap.add_argument("--count", "-c", type=int, default=None,
                    help="Max items per table (testing)")
    ap.add_argument("--pause", type=float, default=PAUSE_SECONDS,
                    help="Pause between embedding calls with workers=1 (default: %(default)s)")
    ap.add_argument("--workers", "-w", type=int, default=1,
                    help="Parallel embedding workers; 1 = sequential (default: %(default)s)")
    args = ap.parse_args(argv)

    engine = get_engine()
    for table in args.tables:
        run_table(engine, table, args.count, args.pause, workers=args.workers)
    return 0


if __name__ == "__main__":
    sys.exit(main())
