#!/usr/bin/env python3
"""OParl URL upgrade: web1.karlsruhe.de → web2.karlsruhe.de (change:
oparl-endpoint-web2; scope-extended per ops review 2026-11-26).

Scope: ALL tables of the OParl reconstruction — every table whose name
starts with an uppercase letter and contains no underscore (i.e. every
entity table, not the association tables) — in ALL their textual columns
(TEXT / VARCHAR / JSONB), including `oparlId` and the JSONB `data`
payloads with the original JSON. Identifier keys (oparlKey, sids, *_id
FKs) stay untouched, so the migration is structural and idempotent.

Usage:
    python scripts/upgrade_oparl_urls.py              # dry run (counts)
    python scripts/upgrade_oparl_urls.py --apply      # perform the UPDATEs
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

OLD_HOST = "web1.karlsruhe.de"
NEW_HOST = "web2.karlsruhe.de"

# textual SQLAlchemy type classes eligible for rewriting
_TEXT_TYPES = "TEXT", "VARCHAR", "CHAR", "STRING", "JSONB", "JSON"


def _eligible_table(name: str) -> bool:
    """OParl entity tables: uppercase first letter, no underscore;
    test_* tables are never touched."""
    if name.startswith("test_"):
        return False
    return name[:1].isupper() and "_" not in name


def _scan_tables(engine):
    """[(table, [(col, is_json, count), …]), …] for eligible tables that
    still contain web1 URLs."""
    import sqlalchemy as sa
    inspector = sa.inspect(engine)
    out = []
    with engine.connect() as conn:
        for t in inspector.get_table_names():
            if not _eligible_table(t):
                continue
            hits = []
            for col in inspector.get_columns(t):
                tname = str(col["type"]).upper()
                if not any(tname.startswith(p) for p in _TEXT_TYPES):
                    continue
                is_json = tname.startswith("JSON")
                n = conn.execute(sa.text(
                    f'SELECT count(*) FROM "{t}" '
                    f'WHERE "{col["name"]}"::text LIKE :pat'),
                    {"pat": f"%{OLD_HOST}%"}).scalar()
                if n:
                    hits.append((col["name"], is_json, n))
            if hits:
                out.append((t, hits))
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
    touched = _scan_tables(engine)

    n_cols = sum(len(cols) for _t, cols in touched)
    n_rows = sum(c for _t, cols in touched for _n, _j, c in cols)
    print(f"OParl entity tables (uppercase, no underscore) with "
          f"{OLD_HOST} URLs:")
    for t, cols in touched:
        for col, _is_json, cnt in cols:
            print(f"  {t}.{col}: {cnt}")
    print(f"TOTAL tables: {len(touched)}, columns: {n_cols}, "
          f"affected rows: {n_rows}")

    if not touched:
        print("nothing to do — no web1 URLs in the store.")
        return
    if not args.apply:
        print("dry run only — pass --apply to perform the migration.")
        return

    print("Applying UPDATEs…")
    updated = 0
    with engine.begin() as conn:
        for t, cols in touched:
            for col, is_json, _cnt in cols:
                cast = "::jsonb" if is_json else ""
                res = conn.execute(sa.text(
                    f'UPDATE "{t}" SET "{col}" = '
                    f'replace("{col}"::text, :oldhost, :newhost){cast} '
                    f'WHERE "{col}"::text LIKE :pat'),
                    {"oldhost": OLD_HOST, "newhost": NEW_HOST,
                     "pat": f"%{OLD_HOST}%"})
                print(f"  {t}.{col}: updated {res.rowcount}")
                updated += res.rowcount
    print(f"done — {updated} row updates.")

    # verification: nothing left behind
    left = _scan_tables(engine)
    leftover = sum(c for _t, cols in left for _n, _j, c in cols)
    print(f"verification: {leftover} rows still readable with "
          f"{OLD_HOST}" if leftover else
          f"verification: clean — no {OLD_HOST} URLs remain.")


if __name__ == "__main__":
    main()
