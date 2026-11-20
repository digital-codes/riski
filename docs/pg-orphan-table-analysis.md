# PostgreSQL orphan-table analysis (2026-11-19)

Scope: `riski_agentic` — identify tables left over from older
knowledge-extraction attempts, unused by the current update / API /
query scripts. Method: full table inventory (`pg_stat_user_tables`),
then grep of every table name across `src/`, `app/src/`, `config/`,
`scripts/`, `utils/` (the working tree = `main`), plus live row counts.

## Findings

### A. Old knowledge-extraction experiment — `utils/kg/*`

Reference set: `concept_schemes` (5), `concepts` (62),
`entity_concepts` (0), `semantic_triples` (13),
`registered_ontologies` (9), `oparl_semantic_mapping` (8),
`uri_mappings` (0), plus materialized views `mv_paper_enriched`
(13,540) and `mv_person_roles` (708).

**All references live exclusively in `utils/kg/`** — the early KG
attempt (`01_create_schema.sql`, `02_initial_data.sql`,
`triplestore.py`, `vocabulary.py`, `query.py`, …; last touched in the
"sample timeline app and very initial kg stuff" era). **Nothing in
`src/` (pipeline, API, search) or the app reads or writes them.**
→ Orphaned as a *system*; candidates for drop or archive-dump.

### B. Untyped association tables — structurally dead (0 rows)

`AgendaItem__consultation__Consultation`,
`AgendaItem__meeting__Meeting`,
`Consultation__agendaItem__AgendaItem`,
`Consultation__meeting__Meeting`,
`Consultation__paper__Paper`,
`Membership__organization__Organization`,
`Membership__person__Person`,
`Organization__body__Body`,
`Paper__body__Body`,
`Person__body__Body`,
`Person__location__Location`,
`LegislativeTerm__body__Body`,
`Body__system__System`

**0 rows each and 0 code references** — pgGen creates these
generically from observed OParl `*`-link fields; the real relations
run through scalar FK columns (`Consultation."paperSid"` etc.) or the
populated twins (`Consultation__organization__Organization` 15,193,
`Meeting__agendaItem__AgendaItem` 18,980 …).
→ Safe drops (pgGen will re-create them if the source ever delivers
those links).

### C. Populated-but-unreferenced twins

* `Organization__membership__Membership` (1,348),
  `Person__membership__Membership` (3,110),
  `Paper__location__Location` (1) — populated by pgGen from OParl
  JSON, but **no code reads them** (the API graph uses
  `Membership__*` scalar FKs instead). Keep (data, not junk) — flag
  as "unused by code, produced by import".

### D. `file_with_teasers` (0 rows) — remnant of the retired
`File.content`-based teaser flow (pre `unify-file-content-in-chunks`).
Zero references. → Drop candidate.

### E. `fileStageStatus` (16 rows) — belongs to the **pending**
`unified-update-pipeline` change: `src/db/stageLedger.py` exists on
`dev` (commit 28b896f) but is **not merged into main**; the table is
live in the DB (16 rows written by a dev-branch run). → Not orphaned
in the project sense; becomes active when that change lands. Do not
drop while `unified-update-pipeline` is open.

### F. Active systems — NOT orphans (for completeness)

* `*_tags`/`*_tags_assoc` (File 52,797 / Paper 13,835 / AgendaItem
  5,350 rows): written by `pgCategorise`/`pgTagMgr` today, and the
  kg-postgres-integration change will *add* to them (scheme
  `kg-topic`).
* `*_name_vecs`, `contentEmbeddings`: search layer.
* `Streets_items_*` / `Districts_items_*`: geo references (27 +
  references, map/location search).
* `oparlUpdateRuns`/`Items`/`TypeCounts`: incremental-sync cursor.
* `mv_paper_enriched`/`mv_person_roles`: see A — old kg experiment.

## Recommended action set

| set | tables | action |
|---|---|---|
| A (old kg experiment) | 7 core tables + 2 materialized views | `pg_dump` to an archive file, then `DROP` (the `utils/kg/` SQL can rebuild) |
| B (empty untyped twins) | 13 tables | `DROP` (auto-recreated by pgGen if ever needed) |
| D (teaser remnant) | `file_with_teasers` | `DROP` |
| E (dev-branch ledger) | `fileStageStatus` | keep until `unified-update-pipeline` merges |
| C (populated twins) | 3 tables | keep, document as import-produced |

Total reclaim: ~20 tables, of which only the two materialized views
and `semantic_triples` hold data of any volume (13.5k / 708 / 13 rows
— all rebuildable from `utils/kg/02_initial_data.sql` + live tables).

## Executed (2026-11-19)

* **Archive dump:** `/mnt_ai/data/riski/snapshots/kg_orphan_tables_2026-11-19.dump`
  (custom format, 52 KB, all 23 relations verified in the TOC — mixed-case
  names needed `-t '"Name"'` quoting for pg_dump).
* **Dropped:** all 23 (7 old-kg tables + 2 materialized views + 13 empty
  assoc twins + `file_with_teasers`), `DROP … CASCADE`.
* **Post-drop sanity:** Paper/File/File_tags_assoc/File_chunks/
  contentEmbeddings/geo/sync-cursor tables intact; API/search layer
  untouched; bulk kg runs unaffected (statements + tagger continued).
* Kept: `fileStageStatus` (dev-branch ledger) and the 3 populated
  unread twins per findings C/E.
