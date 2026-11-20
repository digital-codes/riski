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


## Update-workflow verification (task 4.1, 2026-11-20)

`scripts/kgUpdateVerify.py` proves the kg phase chain inside the
riskiUpdate phase pattern (snapshot → phases → baseline delta → JSON
report) without merging the pending `unified-update-pipeline`
orchestrator. Run:

```bash
/home/agent/bin/python3.14 scripts/kgUpdateVerify.py --snapshot-only
/home/agent/bin/python3.14 scripts/kgUpdateVerify.py            # full
/home/agent/bin/python3.14 scripts/kgUpdateVerify.py --dry-run
/home/agent/bin/python3.14 scripts/kgUpdateVerify.py --skip-statements
```

Verified live 2026-11-20: snapshot 963 MB (TOC-verified), 9/9 phases ok
(ident/chains/protocols/abstimmung/statements/tags/authors/tune/
migrate), delta 0 on the converged store (correct — nothing new to
ingest), report at `results/kg_update_verify_<date>.json`. When
`unified-update-pipeline` lands, each phase function ports 1:1 into its
registry (best-effort class; `migrate` cursor-gated).
