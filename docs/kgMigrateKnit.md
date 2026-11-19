# kgMigrateKnit — SQLite → PostgreSQL kg migration

`src/kg/kgMigrate.py` moves the kg prototype store
(`results/kg_statements.sqlite`) into `riski_agentic` as the typed
`kg_*` layer. Change: `kg-postgres-integration`.

## Commands

```bash
# dry run (default): planned counts + sid-resolution miss classes, no writes
python -m src.kg.kgMigrate

# apply: DDL (idempotent) + imports + verification + cursor bookkeeping
python -m src.kg.kgMigrate --apply

# partial phases
python -m src.kg.kgMigrate --apply --skip-tags    # statements pass only
python -m src.kg.kgMigrate --apply --skip-statements
```

## Semantics

* **Idempotent by construction** — every import is an upsert on a
  stable key; repeat runs merge deltas (critical while the SQLite bulk
  keeps appending — the migrator skips the live-writer race by
  verifying against a BASELINE snapshot and reporting the post-baseline
  residue as "picked up next apply").
* **Sid resolution** — declarative `LEFT JOIN "Paper"/"Meeting"/"File"`
  on oparlId/oparlKey inside the migrator; misses are listed by class
  (paper_unresolved / *_deleted / doc_key misses) before any write.
* **Outcome merge priority** — `kg_signal_priority()` (priority: db-
  partial < vector < regex < protocol < db-column): stronger evidence
  upgrades a pair's outcome, weaker evidence never downgrades it.
* **Statements as JSONB** — strict parse, malformed rows reported (not
  silently coerced); freshness via `kg_statements.updated_at` /
  `kg_pairs.updated_at` + `pipeline_version`.
* **Tag path via TagManager** — `pgTagMgr._VALID_SOURCES` now includes
  `sysone` / `llm-kg`; associations carry scheme `kg-topic` with
  per-row confidence and `*_tags_assoc.updated` freshness timestamps;
  the partial unique index on `(oparl_key, tag_id, scheme)` makes the
  upserts possible (review finding 2).
* **Retirement** — `deleted=true` sources and sid-resolution misses
  mark pairs `status='retired'`; evidence rows are never deleted.

## Cursor

`kg_ingestion_runs` (stage, last_synced_at, last_status, last_count):
the single source of truth for what has been ingested; mirrors
`oparlUpdateRuns`. Current state after first apply:
`('migrate', 'ok', 8301)`.
