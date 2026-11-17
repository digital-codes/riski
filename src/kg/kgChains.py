"""Reconstruct item history chains (design D10 amendment).

Post-processing over the SQLite store (no further DB reads needed):

* papers discussed in several Gemeinderat meetings produce several
  pairs — every pair BUT the latest meeting one is marked
  ``pairs.pre_stage = 1`` ("discussion pair") and consecutive pairs are
  linked in ``pair_links`` (relation 'next') so a statement layer can
  distinguish "discussed here" from "decided here".
* outcome-from-role rule: pairs whose consultation role is
  'Kenntnisnahme' but which carry no AgendaItem.result-derived outcome
  get outcome ``kenntnisnahme`` (signal ``db-partial``, reduced
  confidence). A present result ALWAYS wins — role-Kenntnisnahme items
  also carry results like 'einstimmig beschlossen' in the corpus
  (verified sample, 2026-11-17).

Usage::

    python -m src.kg.kgChains                    # operate on the store
    python -m src.kg.kgChains --store path.sqlite
"""

from __future__ import annotations

try:  # script-mode import bootstrap
    import _bootstrap  # noqa: F401
except ImportError:
    pass

import argparse

from src.kg.kgStore import KgStore
from src.kg.kgStatus import StatusTicker

DEFAULT_STORE = "results/kg_statements.sqlite"


def build_chains(store: KgStore) -> dict:
    """Mark pre-stage pairs and write consecutive links. Returns stats."""
    stats = {"chains": 0, "pre_stage": 0, "links": 0}
    chains = store.paper_chains()
    for row in chains:
        pairs = store.paper_pairs(row["paper_key"])
        stats["chains"] += 1
        # the last pair (latest meeting date) holds the decision;
        # everything before it is a pre-stage discussion pair
        for prev, nxt in zip(pairs, pairs[1:]):
            stats["pre_stage"] += 1
            store.set_pre_stage(prev["pair_key"])
            if not prev["outcome"]:
                stats["links"] += 0  # outcome stays null; role rule below
            store.upsert_link(prev["pair_key"], nxt["pair_key"])
            stats["links"] += 1
    return stats


def apply_role_outcomes(store: KgStore) -> int:
    """Pairs with role 'Kenntnisnahme' consultations and result-NULL
    agenda items — read from the PostgreSQL DB and update the store."""
    from sqlalchemy import text

    from src.db import get_engine

    conn = get_engine(readonly=True).connect()
    n = 0
    for pair in store.pairs_by_status("identified"):
        if pair["outcome"]:
            continue
        row = conn.execute(
            text(
                """
                SELECT c.role FROM "Paper" po
                JOIN "Paper__consultation__Consultation" pc ON pc."srcSid" = po.sid
                JOIN "Consultation" c ON c.sid = pc."tgtSid"
                JOIN "Meeting" m ON m.sid = c."meetingSid"
                WHERE po."oparlId" = :pk AND m."oparlId" = :mk
                """
            ),
            {"pk": pair["paper_key"], "mk": pair["meeting_key"]},
        ).fetchone()
        if row and row[0] == "Kenntnisnahme":
            store.upsert_pair(
                pair_key=pair["pair_key"],
                paper_key=pair["paper_key"],
                meeting_key=pair["meeting_key"],
                outcome="kenntnisnahme",
                signal="db-partial",
                confidence=0.6,
            )
            n += 1
    conn.close()
    return n


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", default=DEFAULT_STORE)
    parser.add_argument("--db", action="store_true", help="also read PG for role outcomes")
    args = parser.parse_args()

    store = KgStore(args.store)
    store.ensure_pre_stage()

    ticker = StatusTicker()
    ticker.section("chains")
    stats = build_chains(store)
    if args.db:
        ticker.tick("applying role outcomes from PG ...")
        stats["role_outcomes"] = apply_role_outcomes(store)
    store.commit()
    ticker.tick(f"done: {stats}", force=True)
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
