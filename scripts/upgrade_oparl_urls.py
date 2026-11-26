#!/usr/bin/env python3
"""OParl URL upgrade: web1.karlsruhe.de → web2.karlsruhe.de (change:
oparl-endpoint-web2).

All relevant URL columns are named `oparlId` (plus the JSONB `data`
payloads, which also hold OParl URLs). This migration rewrites the URL
*strings* in `oparlId` and — optionally — `data`; identifier keys
(oparlKey, sids, links) stay untouched, so it is structural and
idempotent.

Usage:
    python scripts/upgrade_oparl_urls.py              # dry run (counts)
    python scripts/upgrade_oparl_urls.py --apply      # perform the UPDATEs
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

OLD_HOST = "web1.karlsruhe.de"
NEW_HOST = "web2.karlsruhe.de"
URL_COLS = ("oparlId", "data")   # all relevant accessor names are oparlId


def _affected_tables(inspector):
    """(table, [cols]) pairs for every oparl data table with web1 URLs."""
    out = []
    for t in inspector.get_table_names():
        if t.startswith("test_"):
            continue
        cols = {c["name"] for c in inspector.get_columns(t)}
        use = sorted(cols & set(URL_COLS))
        if use:
            out.append((t, use))
    return out


def main():
    import argparse
    import sqlalchemy as sa
    from src.db import get_engine

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="report counts only (default)")
    parser.add_argument("--apply", action="store_true",
                        help="perform the UPDATE statements")
    args = parser.parse_args()
    if args.apply and args.dry_run:
        parser.error("--apply and --dry-run are mutually exclusive")

    engine = get_engine()  # RW side: a write migration
    inspector = sa.inspect(engine)

    print("Tables with oparlId/data (affected rows):")
    touched = []
    for table, use in _affected_tables(inspector):
        where = " OR ".join(
            '"%s"::text LIKE %s' % (c, "CONCAT('%', :pat, '%')")
            for c in use)
        with engine.connect() as conn:
            n = conn.execute(
                sa.text(f'SELECT count(*) FROM "{table}" WHERE {where}'),
                {"pat": f"%{OLD_HOST}%"}).scalar()
        if n:
            touched.append((table, use, n))
            print(f"  {table}: {n}")

    total = sum(n for _t, _u, n in touched)
    print(f"TOTAL affected rows: {total}")

    if not touched:
        print("nothing to do — no web1 URLs in the store.")
        return
    if args.apply:
        print("Applying UPDATEs…")
        with engine.begin() as conn:
            for table, use, _n in touched:
                sets = ", ".join(
                    (f'"{c}" = replace("{c}"::text, :oldhost, '
                     f"'{NEW_HOST}')::jsonb" if c == "data" else
                     f'"{c}" = replace("{c}", :oldhost, \'{NEW_HOST}\')')
                    for c in use)
                where = " OR ".join(
                    '"%s"::text LIKE %s' % (c, "CONCAT('%', :pat, '%')")
                    for c in use)
                res = conn.execute(
                    sa.text(f'UPDATE "{table}" SET {sets} WHERE {where}'),
                    {"pat": f"%{OLD_HOST}%", "oldhost": OLD_HOST})
                print(f"  {table}: updated {res.rowcount}")
        print("done.")
    else:
        print("dry run only — pass --apply to perform the migration.")


if __name__ == "__main__":
    main()
