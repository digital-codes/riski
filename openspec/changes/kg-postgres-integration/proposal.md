# Proposal

## Why

The kg prototype (`kg-statement-extraction`) produced its grounding data in a
local SQLite store — right for the prototype (fast iteration, no schema
commitments), but the retrieval layer (`riski_agentic` PostgreSQL) is the
living system: it grows continuously (`syncIncremental`), powers search, graph
and API, and must consume the statements/tags/pairs with the same freshness and
idempotent-update semantics as every other enrichment layer. Additionally, the
prototype era is ending its model-agnostic phase: local ollama is retired for
kg, cloud decision models replaced embedding classification — the specity
behaviour that must survive the integration becomes stable contract, not
prototype state.

## What Changes

- **New typed kg schema in `riski_agentic`** (additive, `kg_` prefix):
  `kg_pairs` `(paper_sid, meeting_sid)` unique with outcome/confidence/signal,
  `kg_pair_documents` (role matrix with `verify_note`),
  `kg_pair_links` (item history chains), `kg_statements` (JSONB field bags IF evolution-friendly),
  `kg_crosschecks`, `kg_tags`/`kg_qualifiers` vocabularies, `kg_doc_qualifiers`,
  `kg_file_meta`, `kg_ingestion_runs` (per-stage cursor: `last_synced_at`,
  `last_status`, `last_count` — mirrors the `oparlUpdateRuns` pattern).
- **Migrator `src/kg/kgMigrate.py`**: SQLite → Postgres, dry-run default,
  idempotent upserts throughout, sid resolution via oparlKey/oparlId joins,
  strict per-step row-count verification (mismatch aborts in apply mode).
- **Incremental ingestion contract**: kg stages become a re-runnable layer in
  the update workflow (after `syncIncremental` + enrichment); new documents
  flow through the same gates (kgProtocols / kgAbstimmung / statements) on the
  next run; deletions map to `status='retired'` (no destructive deletes);
  statement refreshes peg on OParl `modified` timestamps; outcomes upgrade by
  signal priority (better evidence beats worse, never the reverse).
- **Tag integration**: kg topics enter the **existing**
  `File_tags`/`File_tags_assoc` (scheme `kg-topic`, source e.g. `sysone`,
  confidence carried) so existing riski tag consumers work unchanged;
  vocabulary evolution stays data-only (add tag/qualifier = row inserts, plus
  optional re-classification pass).
- Documentation: `docs/kg-migration-postgres-proposal.md` is the design
  reference (schema DDL, identifier translation rules, per-table update
  semantics).

## Capabilities

### New Capabilities

- `kg-postgres-store`: the typed `kg_*` schema in `riski_agentic`, its
  identifier mapping rules (oparlKey/oparlId ↔ sid), idempotent migrator
  behaviour (dry-run/apply, verification gates), and the incremental
  ingestion contract (cursor table, upsert-merge priority, retirement
  semantics).
- `kg-tag-integration`: riski topics as provenance-stamped rows in the
  existing tag tables, vocabulary-sync rules and the re-classification
  trigger.

### Modified Capabilities

(none — modules add a layer; existing enrichment/search behaviour is
untouched)

## Impact

- Code: new `src/kg/kgMigrate.py`; no changes to existing pgGen/geo/search
  modules; `src/db` reused (RW credentials conventional).
- Database: additive DDL in `riski_agentic` (no existing table touched);
  `File_tags_assoc` gains rows under a new scheme value (`kg-topic`).
- Configuration: none new (vocabulary yaml remains the single source of
  truth; RW credentials via existing `src.db` resolution).
- Dependency: supersedes the SQLite store as the serving target once the
  first migration applies; `kg-statement-extraction` (in-flight) remains
  the producer of the store being migrated.
