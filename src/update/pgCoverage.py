"""Coverage report over the enrichment layers (change: categorization-indexing).

Reports, per item table and per layer, what fraction of rows is populated:
content / teaser / contentKind (File), content embeddings, name vectors and
tags (with scheme breakdown). Read-only; safe to run against production.
"""

# Dual-mode import support: allow running directly as a script.
try:
    import _bootstrap  # noqa: F401  (script mode: puts repo root on sys.path)
except ImportError:
    pass

import argparse
import json
import sys

import sqlalchemy as sa

from src.db import get_engine

# Item tables considered by the enrichment pipelines (order = report order).
ITEM_TABLES = ["File", "Paper", "AgendaItem", "Meeting", "Organization"]


def _scalar(conn, sql: str):
    return conn.execute(sa.text(sql)).scalar()


def _table_names(conn) -> set:
    return {
        r[0]
        for r in conn.execute(
            sa.text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
        )
    }


def coverage(engine, item_tables=ITEM_TABLES) -> dict:
    """Compute the coverage report as a nested dict."""
    report: dict = {}
    with engine.connect() as conn:
        tables = _table_names(conn)

        for t in item_tables:
            if t not in tables:
                continue
            total = _scalar(conn, f'SELECT count(*) FROM "{t}"') or 0
            entry: dict = {"total": total, "layers": {}}

            if t == "File":
                for col in ("content", "teaser"):
                    n = _scalar(conn, f'SELECT count(*) FROM "{t}" WHERE "{col}" IS NOT NULL') or 0
                    entry["layers"][col] = {"count": n, "pct": round(n / total * 100, 1) if total else 0.0}
                kinds = conn.execute(
                    sa.text('SELECT "contentKind", count(*) FROM "File" WHERE "contentKind" IS NOT NULL GROUP BY 1')
                ).all()
                entry["layers"]["contentKind"] = {k: v for k, v in kinds}

            if "contentEmbeddings" in tables and t == "File":
                n = _scalar(conn, 'SELECT count(*) FROM "contentEmbeddings"') or 0
                entry["layers"]["contentEmbeddings"] = {
                    "count": n, "pct": round(n / total * 100, 1) if total else 0.0
                }

            nvt = f"{t}_name_vecs"
            if nvt in tables:
                n = _scalar(conn, f'SELECT count(*) FROM "{nvt}"') or 0
                entry["layers"]["name_vecs"] = {
                    "count": n, "pct": round(n / total * 100, 1) if total else 0.0
                }

            tagt, assoct = f"{t}_tags", f"{t}_tags_assoc"
            if assoct in tables:
                tagged = _scalar(
                    conn,
                    f'SELECT count(DISTINCT oparl_key) FROM "{assoct}"',
                ) or 0
                entry["layers"]["tags"] = {
                    "tagged_items": tagged,
                    "pct": round(tagged / total * 100, 1) if total else 0.0,
                }
                if tagt in tables:
                    schemes = conn.execute(
                        sa.text(
                            f'SELECT COALESCE(scheme, \'(none)\'), count(DISTINCT oparl_key) '
                            f'FROM "{assoct}" GROUP BY 1 ORDER BY 2 DESC'
                        )
                    ).all()
                    entry["layers"]["tags"]["by_scheme"] = {k: v for k, v in schemes}

            report[t] = entry
    return report


def _print(report: dict) -> None:
    for table, entry in report.items():
        total = entry["total"]
        print(f"\n{table}  ({total} rows)")
        print("-" * 48)
        for layer, data in entry["layers"].items():
            if isinstance(data, dict) and "count" in data:
                print(f"  {layer:20s} {data['count']:>8}  ({data['pct']}%)")
            elif layer == "contentKind":
                print(f"  {'contentKind':20s} " + ", ".join(f"{k}={v}" for k, v in data.items()))
            elif layer == "tags":
                print(f"  {'tags':20s} {data['tagged_items']:>8}  ({data['pct']}%)")
                for scheme, n in data.get("by_scheme", {}).items():
                    print(f"    scheme {scheme:22s} {n:>8}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Enrichment-layer coverage report")
    ap.add_argument("--json", action="store_true", help="Emit JSON instead of a table")
    args = ap.parse_args(argv)

    engine = get_engine(readonly=True)
    report = coverage(engine)
    if args.json:
        json.dump(report, sys.stdout, indent=2, ensure_ascii=False)
        print()
    else:
        _print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
