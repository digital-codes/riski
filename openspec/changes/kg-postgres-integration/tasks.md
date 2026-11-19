# Tasks

## 1. Schema + migrator skeleton

- [x] 1.1 Implement `kgMigrate.py` DDL phase: `kg_*` tables from `docs/kg-migration-postgres-proposal.md` §2 (review-corrected DDL: surrogate-id + expression unique index on `kg_statements` — finding 3; `role` in the `kg_pair_documents` PK — finding 5; `kg_pairs.updated_at`/`pipeline_version` — finding 4) plus `kg_ingestion_runs` cursor (create-if-not-exists, idempotent) — verify by running twice against a test database the second run is a no-op; verify `kg_signal_priority` lookup exists and covers the SQLite signal values
- [x] 1.2 SQLite source reader + temp-table/COPY load of the SQLite rows into the migration session (design D1), including `pair_key` split into paper/meeting oparl ids — verify with the real store that resolution misses are zero or listed per class (empty-string doc_key, deleted Papers/Files, id/version drift); verify dry-run prints planned inserts per table and gains no rows in the target

## 2. Import paths

- [x] 2.1 Implement `kg_pairs` + `kg_pair_documents` + `kg_pair_links` import (`INSERT … SELECT` JOINs, signal-priority CASE upsert per design D2, `pre_stage`/`verify_note` carried); verify counts against SQLite per table on the live store and with an injected test pair (create/duplicate/upgraded-outcome scenario) exercising the ON CONFLICT branches
- [x] 2.2 Implement `kg_statements` + `kg_crosschecks` import (strict JSON parse, malformed reported and rejected not silently coerced, doc_sid nullable); verify round-trip sample access via SQL on 10 pairs and that cross-check counts match the source
- [x] 2.3 Implement tag path (task 'tags' step): **add the `updated TIMESTAMPTZ` freshness column to the three `*_tags_assoc` tables and have TagManager set it on add** (interplay analysis, serves kg-topic and document-type schemes); extend `pgTagMgr._VALID_SOURCES` with kg sources (`sysone`, `llm-kg` — review finding 1), create the partial unique index on `File_tags_assoc (oparl_key, tag_id, scheme) WHERE scheme IS NOT NULL` (finding 2, required before any ON CONFLICT upsert), vocabulary sync into `kg_tags`/`kg_qualifiers`/`File_tags`, tag associations via TagManager.add_tags (scheme `kg-topic`), grounded qualifiers into `kg_doc_qualifiers` (reject undefined pairs); verify existing `document-type` rows untouched, kg rows visible through the existing tag-join queries

## 3. Verification + cursor

- [x] 3.2 Implement per-stage incremental dedup semantics (interplay analysis): refresh decisions keyed on source `modified` timestamps vs `kg_ingestion_runs` cursors (outcome change → statement re-extract; new Files → tag/verify; changed protocols re-verify), re-classification = scheme-scoped DELETE then TagManager add (no silent-ignore trap); verify the upgrade scenario (weak outcome → protocol evidence upgrades the pair) and that completed pairs are never processed twice
- [x] 3.1 Implement per-table row-count verification gate + miss report (abort in apply mode), plus the `kg_ingestion_runs` cursor bookkeeping per stage and the `status='retired'` propagation for source-deleted pairs — deleted=true flag (verified live: Paper 4 / Consultation 4 / File 53 rows) AND sid-resolution misses in incremental runs (no destructive deletes — verify both scenarios); verify a second full run against the already-populated test DB reports "0 inserts" per table (pure idempotency) and the cursor shows only refreshes

## 4. Optional Deferred Integration

- [ ] 4.1 Wire `riskiUpdate` / update-workflow hooks for the kg stages as a documented phase (per design D3: cursor-gated, runs after enrichment; NOT implemented here — depends on the separate `unified-update-pipeline` change; task exists as wiring spec only, may be deferred — note dependency in docs)
- [x] 4.2 Write `docs/kgMigrateKnit.md` usage documentation of the migrator (dry-run/apply examples, cursor reading, idempotency note for updates) and the docs/kgStatus.md update marking the pg store as normative target after first apply

## Workflow follow-up

- `kg-statement-extraction` must complete (SQLite producer reaches stable output) before the first real --apply; the SQLite producer stays the source until then (design trade-off note).
- Consider a GIN index on `kg_statements.fields_json` when a consumer layer lands (deferred, consumer-side).
