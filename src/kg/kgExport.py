"""Export the kg SQLite store to JSON (task 8.1).

One JSON per export unit:
* ``pairs``          — full pair records with documents, tags, authors,
                       request/response statements and cross-check verdicts
* ``tags``           — tag vocabulary + distribution

Usage::

    python -m src.kg.kgExport                         # results/kg_export.json
    python -m src.kg.kgExport --store path.sqlite --only pairs
"""

from __future__ import annotations

try:  # script-mode import bootstrap
    import _bootstrap  # noqa: F401
except ImportError:
    pass

import argparse
import json
from collections import defaultdict

from src.kg.kgStore import KgStore

DEFAULT_STORE = "results/kg_statements.sqlite"
DEFAULT_OUT = "results/kg_export.json"


def export(store: KgStore, out_path: str, only: str | None) -> dict:
    data: dict = {}

    if only in (None, "tags"):
        data["tag_vocabulary"] = [
            {"tag": r["tag"], "description": r["description"]} for r in store.tags()
        ]
        data["qualifier_vocabulary"] = [
            {"tag": r["tag"], "qualifier": r["qualifier"], "description": r["description"]}
            for r in store.qualifiers()
        ]
        dist = defaultdict(lambda: {"n": 0, "avg_conf": 0.0})
        rows = store.conn.execute(
            "SELECT tag, confidence FROM file_tags"
        ).fetchall()
        acc = defaultdict(list)
        for r in rows:
            acc[r["tag"]].append(r["confidence"])
        data["tag_distribution"] = {
            t: {"n": len(v), "avg_conf": round(sum(v) / len(v), 3)}
            for t, v in acc.items()
        }

    if only in (None, "pairs"):
        pairs = []
        for p in store.conn.execute("SELECT * FROM pairs ORDER BY pair_key"):
            key = p["pair_key"]
            doc = [
                {
                    "doc_id": d["doc_id"],
                    "filename": d["filename"],
                    "name": d["name"],
                    "role": d["role"],
                }
                for d in store.documents_for_pair(key)
            ]
            stmt = defaultdict(dict)
            for r in store.conn.execute(
                "SELECT stage, fields_json FROM statements WHERE pair_key = ?", (key,)
            ):
                stmt[r["stage"]] = json.loads(r["fields_json"])
            cc = store.conn.execute(
                "SELECT verdict, reason FROM crosschecks WHERE pair_key = ?", (key,)
            ).fetchone()
            pairs.append(
                {
                    "pair_key": key,
                    "paper": p["paper_key"],
                    "meeting": p["meeting_key"],
                    "meeting_date": p["meeting_date"],
                    "request_type": p["request_type"],
                    "outcome": p["outcome"],
                    "confidence": p["confidence"],
                    "signal": p["signal"],
                    "pre_stage": bool(p["pre_stage"]) if p["pre_stage"] is not None else False,
                    "status": p["status"],
                    "documents": doc,
                    "author": stmt.get("author"),
                    "request": stmt.get("request"),
                    "response": stmt.get("response"),
                    "modification_link": stmt.get("link"),
                    "crosscheck": {"verdict": cc["verdict"], "reason": cc["reason"]}
                    if cc
                    else None,
                }
            )
        data["pairs"] = pairs
        data["counts"] = {
            "pairs": len(pairs),
            "with_statements": sum(1 for p in pairs if p["request"] or p["response"]),
            "crosscheck_passed": sum(
                1 for p in pairs if p["crosscheck"] and p["crosscheck"]["verdict"] == "passed"
            ),
            "crosscheck_failed": sum(
                1 for p in pairs if p["crosscheck"] and p["crosscheck"]["verdict"] == "failed"
            ),
        }

    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1, default=str)
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", default=DEFAULT_STORE)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--only", choices=["pairs", "tags"])
    args = parser.parse_args()

    store = KgStore(args.store)
    data = export(store, args.out, args.only)
    if "counts" in data:
        print(json.dumps(data["counts"], ensure_ascii=False))
    print(f"export written: {args.out} ({len(str(data))} chars)")
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
