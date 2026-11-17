"""Statistics report over the kg identification stage.

Verifies the plan assumptions from docs/kg_building.md against the
identified pair set (spec: pair statistics):

* documents per pair (request / modification / response counts),
* chunk-count distribution (expected: up to 5 chunks per document),
* number of modification chains (papers of class modification linked to
  originals) — reported as separate request-pair keys.

Usage::

    python -m src.kg.kgStats                      # default store
    python -m src.kg.kgStats --store path.sqlite  # custom store
"""

from __future__ import annotations

import argparse
import json

from src.kg.kgStore import KgStore

DEFAULT_STORE = "results/kg_statements.sqlite"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", default=DEFAULT_STORE)
    args = parser.parse_args()

    store = KgStore(args.store)
    cur = store.conn

    pairs = cur.execute("SELECT COUNT(*) FROM pairs").fetchone()[0]
    docs = cur.execute(
        """
        SELECT role, COUNT(*) AS n FROM pair_documents GROUP BY role
        """
    ).fetchall()
    per_pair = cur.execute(
        """
        SELECT bucket, COUNT(*) AS n FROM (
            SELECT pair_key, COUNT(*) AS c,
                   CASE WHEN COUNT(*) <= 5 THEN '<=5' ELSE '>5' END AS bucket
            FROM file_meta GROUP BY pair_key
        ) GROUP BY bucket
        """
    ).fetchall()
    outcome = cur.execute(
        "SELECT outcome, COUNT(*) AS n FROM pairs GROUP BY outcome ORDER BY n DESC"
    ).fetchall()
    request_type = cur.execute(
        "SELECT request_type, COUNT(*) AS n FROM pairs GROUP BY request_type ORDER BY n DESC"
    ).fetchall()
    chain_keys = cur.execute(
        """
        SELECT COUNT(DISTINCT pd.pair_key) AS n
        FROM pair_documents pd
        WHERE pd.role = 'modification'
        """
    ).fetchone()[0]

    report = {
        "pairs": pairs,
        "documents_by_role": {r["role"]: r["n"] for r in docs},
        "pairs_by_document_bucket": {r["bucket"]: r["n"] for r in per_pair},
        "pairs_by_outcome": {r["outcome"]: r["n"] for r in outcome},
        "pairs_by_request_type": {r["request_type"]: r["n"] for r in request_type},
        "pairs_with_modifications": chain_keys,
        "chunk_distribution": store.chunk_distribution(),
    }
    print(json.dumps(report, indent=2, sort_keys=False))
    with open("results/kg_identification_stats.json", "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, sort_keys=False)
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
