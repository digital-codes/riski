# Design

## Context

The kg prototype ended its era with a stable SQLite store
(`results/kg_statements.sqlite`, 8,301 pairs, 20k+ statements, tags +
grounded qualifiers + 1.6k cross-check verdicts) and a working model
situation (see docs/kgStatus.md) — but PostgreSQL is the serving layer
(`riski_agentic`), growing continuously via `syncIncremental`.
`docs/kg-migration-postgres-proposal.md` already analysed both schemas
down to the identifier correspondence and carries the proposed DDL; this
design references it and only decides the remaining implementation
posture (do NOT restate the DDL here).

## Goals / Non-Goals

**Goals:**
- `kgMigrate.py`: dry-run-default, idempotent upsert migrator implementing
  the proposal's DDL + verification steps.
- Incremental contract: cursor table + re-runnable stages; defeats
  drift — new docs/protocols/scores refresh the layer with better
  evidence only.
- Tag integration through existing tag tables (schema `kg-topic`).

**Non-Goals:**
- No changes to existing PgGen/geo/search modules; no search-layer
  consumption yet (does not depend on this change's trigram indexing —
  deferred to the consumer side).
- No new credentials/roles (src.db conventions rule).
- No SQLite deprecation in this change (the producer keeps running
  until the first successful apply).

## Decisions

### D1: Sid resolution strategy — SQL joins over SQLite data, not in-Python lookups
Read the SQLite rows into a temp table (or CSV `COPY`) and use a single
`INSERT … SELECT` with `LEFT JOIN "File"/"Paper"/"Meeting"` on the
oparlKey/oparlId per table; misses get listed by a companion check query.
This keeps the translation declarative (0 Python loops over 29k+ rows)
and sid resolution errors surface as a diffable SQL result, mirroring the
verification philosophy of the prototype.

### D2: Upsert merge with signal priority expressed as a CASE ordering
The outcome upgrade rule (`sqlite out_key = column|regex|vector|
protocol|db-partial`) is enforced by an ordering table in `ON CONFLICT DO
UPDATE` (`SET outcome = EXCLUDED.outcome WHERE
signal_priority(EXCLUDED.signal) >= signal_priority(kg_pairs.signal)`) —
a `kg_signal_priority` lookup (VALUES list or enum function) rather than
scattered string comparisons; a new pipeline generation can add signals
by extending that table alone.

### D3: Freshness cursor mirrors `oparlUpdateRuns` (not `File.modtime` checks)
`kg_ingestion_runs` records `(stage, last_synced_at, status, count)`, and
stages derive 'what is new' by joining on the riski baseline
(`oparlUpdateRuns`) plus their own cursor — one cursor semantics across
stages, no per-table timestamp snooping.

### D4: JSONB statements — validation over schema constraints
`kg_statements.fields_json` is JSONB (proven JSON; per-field CHECK
constraints would semi-forbid statement-field evolution); the migrator
parses strictly (reject on malformed JSON instead of corrupting).
Downstream correctness relies on the round-trip cross-check verdicts,
which stay version-visible (same reasoning that justified not
normalizing the statement lists in SQLite).

### D5: Retirement semantics: `status='retired'`, never DELETE
Mirrors the OParl `deleted=true` convention of riski's import chain
(decision recorded in the migration proposal §5): retiring is reversible
(source could un-delete), evidence rows remain for audit, and the ingest
cursor never regresses.

### D6: Review dispositions (mistral review 2026-11-19)
Seven findings from the external review of
`docs/kg-migration-postgres-proposal.md` are dispositioned there (§5b)
— the three DDL-correct ones are binding for the DDL task: (a)
`kg_statements` uses a surrogate id + expression unique index (an
expression PK is invalid DDL); (b) `kg_pair_documents` PK includes
`role` (two roles per file in one pair become an invariant, not an
accident); (c) the tag path requires a partial unique index on
`File_tags_assoc (oparl_key, tag_id, scheme) WHERE scheme IS NOT NULL`
(the table only has the surrogate id PK) plus extending
`pgTagMgr._VALID_SOURCES` with the kg sources — TagManager stays the
single write path. Freshness: `kg_pairs.updated_at`/`pipeline_version`
vs `kg_statements.updated_at` detect staleness (no separate flag).
Deletion convention verified live: `deleted=true` exists (Paper 4 /
Consultation 4 / File 53 rows) but only when OParl delivers it —
sid-resolution misses during incremental runs retire pairs as well.

## Risks / Trade-offs

- [SQLite and PostgreSQL can drift between a kg run and a migration]
  → the run cursor gates staleness: stale-marginal rows are re-run, not
  silently accepted; the migrator's diff report makes drift visible.
- [Double source of truth risk (SQLite prototype + PG migration)]
  → after first successful apply, the docs/kgStatus.md instruction
  flips the producer state: SQLite becomes a stale artifact, and the pg
  path becomes normative (`kgStatements` writes to SQLite but the
  migrator pulls deltas until the producer switch, task list item).
- [Tag scheme collision if `kg-topic` already appears someday]
  → the migration pre-checks `SELECT 1 FROM File_tags_assoc WHERE
  scheme='kg-topic'` and aborts when rows exist that kg didn't write.
- [JSONB query cost on statements] → accepted for v1; GIN index on
  `fields_json` planned at consumer-side, not by this change.

## Migration Plan

Additive only: additive DDL, no rewrite of existing tables; the SQLite
producer remains intact until the first apply. Rollback = `DROP TABLE
kg_*` + removing the cursor rows (the search/graph layers are not yet
consuming kg data).


### D7: Cross-change coordination (2026-11-19 interference check)

All four open changes validated; pairwise interference inspected:

* **kg-statement-extraction ↔ kg-postgres-integration**: intent
  dependency, no file conflicts (migrator adds `src/kg/kgMigrate.py`
  alongside the prototype scripts; `src/db` conventions reused
  read-only). The SQLite store stays producer until first `--apply`
  (workflow note in design §5).
* **council-exploration-views ↔ kg**: its rule-based submitter
  detection (data-enrichment spec) DERIVES the same facts as the
  prototype's `kgAuthors` (LLM vocabulary + era validity) but stores
  them as PG paper enrichment, while kgAuthors lives in the kg store —
  no schema conflict; reuse opportunity: both should anchor party name
  resolution in `config/kg_vocabulary.yaml::party_variants` so the two
  implementations do not drift. Decision-status normalization
  (AgendaItem.result → controlled vocabulary) likewise mirrors the kg
  outcome mapping — same YAML is the shared anchor.
* **unified-update-pipeline ↔ kg**: owns `src/riskiUpdate.py` +
  `fileStageStatus`/stageLedger (dev branch). The kg stages become a
  phase there — kg-postgres-integration task 4.1 wires that and is
  deliberately deferred. No file overlap: riskiUpdate phase registry
  and kgMigrate/k g-stages stay disjoint until 4.1.
* No change writes another change's schema: kg_* DDL is additive;
  council enrichment writes paper-scheme tags; tag assoc gets ONE
  shared additive column (`updated`) from kg-postgres-integration that
  also benefits council's document-type tagging (no behavior change —
  column DEFAULT now()).

## Open Questions

- What's the precise KB NOT NULL / FK-cascade set on `kg_pair_documents`
  (paper/meeting sid pairs versus role values)? Deferred to the task list
  DDL step with the corpus statistics (task 2? placeholder).
- Whether `kgMigrate` should also *schedule* a post-migration
  `kgTagSystemOne` re-run for the new documents (tagging new docs right
  at ingestion) or whether the update workflow runs tags as the last kg
  stage before the migrator (proposal: the latter; the tag stage already
  handles new docs naturally).
