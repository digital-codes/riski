# Proposal

## Why

Updating the database currently means running seven+ scripts in the right order
with the right flags and environment (`syncIncremental`, `pgOcr`, `pgSummarize`,
`pgAddSummaries --embed-missing`, `pgTeasers` with LLM env vars, three geo-ref
scripts, `pgCategorise`, `pgCoverage`) — easy to get wrong, no automatic
backup, no rollback when a step fails mid-way, and no single report of what the
run actually changed. The 2026-10-24 data update had to be coordinated by hand
across several sessions.

Amended 2026-10-25 after ops review: the auto-rollback idea (`pg_restore` on
any phase failure) is replaced by a retry-on-next-run philosophy — the
pipeline is additive and idempotent by design, so a per-item failure (e.g. one
OCR step) must neither block the rest of the run nor be marked done; it is
simply retried next run. A per-File stage ledger makes this explicit and
observable.

Amended 2026-11-26 against the current codebase (main): the pipeline modules
have evolved since this change was written — the content phase is now
chunk-based (`File_chunks` is the single text store, embeddings are
chunk-indexed), the geo-ref scripts gained the write-time LLM GeoGate with a
new CLI surface, `pgTeasers` uses the shared `src.db` DB/LLM layers, and
several new modules (`pgChunks`, `geoGate`, `pgGeoGateCleanup`, `apiTrace`,
`pgLocationSearch`, the `src/kg/` layer) need a place in the module split.

Amended 2026-11-26 (PII/geo interplay review): the serving-side PII guard
(summary-pii-guard) can mask street names derived from person names
(e.g. "Marie-Alexandra-Straße" → "[xxx]straße"), because hyphenated street
compounds match the person-name detector's boundaries. Two rules are added:
geo inference always consumes raw text (PII masking is request-time only and
never touches stored pipeline data), and the PII guard exempts
street/district name compounds — only the compound stays visible
("karolinenstraße"), not bare person mentions ("Karoline" remains redacted).
The `src/kg/` layer is explicitly excluded and is a candidate for replacement
by another mechanism.

Amended 2026-11-26 (apply-session findings, ops incidents): third-party
payloads remain inconsistent — the web2 API still emits `web1.karlsruhe.de`
URLs for historical entities, and deleted-stub entities carry empty strings
for timestamp fields; pgGen therefore normalizes URL hosts at ingest
(web1→web2, preventing duplicate-entity forks through the `oparlId` unique
key) and coerces empty strings to NULL for non-textual columns, and
decorators `pgAddSummaries`/`pgAddNameVectors` guard their SIGINT handler
registration to the main thread so phase adapters can call them in-process.
The restore helper works in place on this deployment (pg_hba.conf admits
the app role only to the app database; see design D3).

## What Changes

- **One command, `python src/riskiUpdate.py` (or `python -m src.riskiUpdate`)**,
  that executes the complete update as a sequence of phases:
  1. **Snapshot** — `pg_dump -Fc` the database to `/mnt_ai/data/riski/snapshots/`
     (verified with `pg_restore --list`) before anything is written.
  2. **Sync** — incremental crawl + `pgGen` import (reuses
     `syncIncremental.sync()`, which already guarantees the baseline only
     advances after a successful import; instance config aware).
  3. **Enrich** — OCR missing PDFs (`pgOcr`), summarise new markdown
     (`pgSummarize`), update `File.content` and the `File_chunks` chunk store +
     chunk-indexed embeddings (`pgAddSummaries --embed-missing`), teasers
     (`pgTeasers`), geo references with the write-time LLM gate
     (`pgAddFileGeoRefs --prune`, `pgAddStreetRefs`, `pgAddDistrictRefs`),
     tags (`pgCategorise all`) — every step idempotent and resumable.
  4. **Report** — a markdown run report (per-phase stats, row deltas, tag/geo
     counts, coverage numbers, errors) written next to the snapshot.
  5. **On failure** — critical phases (snapshot, sync) stop the run and the
     report prints the restore command; failed enrichment items are retried
     on the next run.
- **Phase criticality** (amended 2026-10-25, after ops review): `sync`
  (crawl + import) is **critical** — on its failure the run stops and reports
  (the tracked baseline already stays put, so the next run re-fetches the
  window). All enrichment phases (OCR, summaries, content, teasers, geo,
  tags) are **best-effort** — a failure in one phase (e.g. OCR) is recorded
  and the run continues with the remaining phases. The pipeline heals by
  **retrying on the next run**, not by rolling back: every step is idempotent
  and only marks work done that actually succeeded, so failed items are
  picked up again automatically.
- **Per-File stage tracking** — every File advances through stages (OCR →
  summary → content+chunks+embeddings → teaser → geo → tags) tracked in a
  per-item ledger: a stage ends in `done`, `failed` (retried next run), or
  `empty` (terminal, with a recorded reason — e.g. no extractable text, no
  streets matched). A File's enrichment is complete when every stage is
  `done` or `empty`; the report lists failed stages and repeat offenders.
  See the new `enrichment-stage-tracking` capability.
- **Geo/PII interplay** (amended 2026-11-26): geo inference (file geo refs,
  street and district links) always consumes **raw** text — `File_chunks`
  (assembled per file) and `AgendaItem.name` — and no stage ever writes
  PII-masked text into stored pipeline fields (`File.content`,
  `File_chunks`, teasers, summaries); PII controls live exclusively in the
  request path. The serving-side PII guard gains a street/district
  exemption: occurrences of a person-vocabulary name that form part of an
  actual street or district name compound remain unmasked; all other
  occurrences (bare person mentions) are still redacted.
- **Phase granularity**: each phase is individually skippable/selectable
  (`--phases sync,enrich` / `--skip enrich`) and resumable — a re-run skips
  completed work by design (all sub-steps are idempotent).
- **Cron contract**: safe for unattended daily invocation — an exclusive-run
  lock (overlapping invocations exit early), per-phase timeouts (a hung LLM
  phase cannot block the next day's run), and exit codes that mail(1) can act
  on (0 = all stages done, 1 = critical failure, 2 = partial success with
  failed stages).
- **Snapshot recovery, not auto-rollback** (amended 2026-10-25): the snapshot
  is a manual recovery point for the operator, not an automatic rollback. The
  restore helpers (verified restore target, rename swap) remain available and
  documented; the pipeline itself never drops or replaces the live database
  unattended — additive/idempotent re-runs are the recovery mechanism.
- **Cleaner module structure** with an obvious separation of concerns
  (mirrors the restructure already implemented on `dev`, extended for modules
  added since the fork):
  - `src/update/` — acquisition & enrichment pipeline (`oparlUpdate`,
    `oparlRunLog`, `syncIncremental`, `pgOcr`, `pgSummarize`, `pgAddSummaries`,
    `pgChunks`, `pgTeasers`, `pgAddFileGeoRefs`, `pgAddStreetRefs`,
    `pgAddDistrictRefs`, `geoGate`, `pgGeoGateCleanup`, `pgCategorise`,
    `pgCoverage`, `pgTagMgr`, `pgAddDistricts`, `pgAddStreets`,
    `pgAddNameVectors`, `pgBackfillNameVecs`, `pgAddVecs`, `pgNameVecs` —
    the orchestrator `src/riskiUpdate.py` incl. its report helper sits one
    level up in `src/` so the documented command keeps working)
  - `src/db/` — database utilities (already exists; gains the snapshot/restore
    helpers `db_snapshot.py` and the stage ledger `stageLedger.py`)
  - `src/search/` — search & analysis surface (`pgVecSearch`, `pgHybridSearch`,
    `pgTimeline`, `pgFileQuery`, `pgLocationSearch`, `graphModel`,
    `pgResultSummarizer`, `apiServer`, `apiTrace`, `local_geo_matching`)
  - **Unmoved**: `src/kg/` (the knowledge-graph layer is explicitly out of
    scope here — it is a candidate for replacement by another mechanism, so
    this pipeline does not compose it), and shared/analyst utilities that
    both halves or standalone workflows use: `pgGen`, `pgAddTags`,
    `pgAddOrgClassification`, `pgGeo`, `pgIntentRouter`, `instanceConfig`,
    `remote/`, `timing.py`, `pass1_entities_tfidf`, `pass2_cluster_words`.
  - **No breakage**: top-level `src/pg*.py` modules become thin re-export
    shims so existing command lines, tests and cross-imports keep working.
- **Docs**: the README "Data update workflow" section is updated to the
  one-command flow (the manual step list remains documented as the underlying
  phases).

## Capabilities

### New Capabilities

- `update-orchestration`: the one-command update pipeline — phase execution
  and selection with criticality classes, pre-run snapshot with verification,
  manual snapshot-restore tooling, cron-safe operation (lock, timeouts, exit
  codes), and the run report.
- `enrichment-stage-tracking`: the per-File stage ledger — per-item status
  (`done`/`failed`/`empty` with reason) for every enrichment stage, driving
  retry-on-next-run and the coverage/poison-item reporting.
- `result-summarizer` (added): "PII-free context and summaries (person
  names)" enters the main specs with this change — the archived
  `summary-pii-guard` delta was never synced to `openspec/specs/` — amended
  with the street/district exemption described above.

### Modified Capabilities

(none besides the added `result-summarizer` PII requirement —
`oparl-import` and `data-enrichment` behaviour is unchanged; the
orchestrator only composes existing, already-specified behaviour)

## Impact

- **Code**: new `src/riskiUpdate.py` (orchestrator incl. the report helper) +
  `src/db/db_snapshot.py` (snapshot/restore helpers) + `src/db/stageLedger.py`
  (per-File stage status table + accessors); existing scripts gain nothing
  more than being moved into `src/update/` (re-export shims at their old
  paths); the PII-guard street/district exemption touches
  `src/search/pgResultSummarizer.py` only. Reuses the current entry points:
  `syncIncremental.sync()`, `pgOcr.run()`, `pgSummarize._run_summarizer()`,
  `pgAddSummaries.main()` (SystemExit on bad dirs), `pgTeasers.main()` (argv
  via `parse_args()`), `pgAddFileGeoRefs.main(["--prune"])` (GeoGate-gated;
  LLM env or `--no-gate`), `pgAddStreetRefs.main()`,
  `pgAddDistrictRefs.main()`, `pgCategorise.main()`, `pgCoverage.main()`,
  `oparlRunLog` stats.
- **Database**: one new on-demand table for the stage ledger (per-File, per-
  stage status). Snapshots land in the existing
  `/mnt_ai/data/riski/snapshots/` directory.
- **Risk**: enrichment phases that partially fail must leave no false "done"
  marks — the stage ledger is the source of truth, so each phase adapter must
  record item outcomes, not just phase-level exit codes; the geo phase now
  involves LLM gating (GeoGate) — the adapter must pass explicit argv and the
  gate's env requirements are part of the phase's environment contract;
  LLM-dependent phases can be long-running — per-phase timeouts and the
  incrementally re-rendered report keep cron runs bounded.
- **Tests**: unit tests for phase sequencing/skip/criticality logic, the stage
  ledger state machine, and the report (`pytest src/tests -m unit`; markers
  already registered in `src/tests/conftest.py`); unit tests for the PII-guard
  street/district exemption and the raw-text ordering guarantee; integration
  test for report data collection; snapshot helpers tested against a scratch
  database.
