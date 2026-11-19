# Migration Proposal: kg SQLite store → `riski_agentic` PostgreSQL

*Change proposal (draft) — 2026-11-18. Prepared from a schema
analysis of both databases as requested. Status: proposal — no code
written yet.*

---

## 0. TL;DR

The kg store migrates into `riski_agentic` as **new, additive kg
tables (`kg_*`)** keyed on **PostgreSQL-native identifiers (`sid`)**
plus the existing OParl key convention, rather than remixing
riski's association tables. Document tags map onto the **existing
`File_tags`/`*_tags_assoc` scheme** (provenance-aware, scheme
`kg-topic`); everything else — pairs, pair↔document roles, chains
(pre-stage), pair statements, cross-checks, qualifier vocabulary —
becomes a dedicated, self-contained `kg_*` block. Evolution (new
tags/qualifiers) is supported by the scheme columns and a
vocabulary-sync script; nothing is lost on re-run (all writes
idempotent upserts keyed on OParl ids/sids).

## 1. Identifier translation (the core of the analysis)

### 1.1 Key correspondences (verified live)

| Postgres | meaning | SQLite counterpart | translation rule |
|---|---|---|---|
| `File.sid` (e.g. 47258) | surrogate int PK | `doc_key` = `oparlKey` ('27739') | **`doc_key` IS `oparlKey` as string → join on `'File'."oparlKey" = doc_key::text`; sid lookup for FKs** |
| `File."oparlId"` | URL | `doc_id` | identical in both stores |
| `File.filename` | derived from oparlKey | `pair_documents.filename` | `filename = lpad(oparlKey, 8, '0') || '.pdf'` (verified: `'27739'→'00027739.pdf'`, `'661019'→'00661019.pdf'`) — SQLite value trustworthy but re-derive at import |
| `Paper.sid` / `Paper."oparlId"` | surrogate / URL | `pairs.paper_key` (= URL) | **split `pair_key` on '\|' → `paper_key` = `Paper."oparlId"`, `meeting_key` = `Meeting."oparlId"`** |
| `Meeting.sid` / start_date | surrogate / timestamp | `meeting_date` (text) | map date text → `Meeting.sid` via oparlId; keep the store's date as `kg_pairs.session_date::date` |
| `Consultation` | role/authoritative already normalized | — | pairs ≠ consultations: a pair selects the *decisive* consultation(s); `Consultation` remains source-of-truth, `kg_pairs` references `paper_sid + meeting_sid` |
| `*_tags` + `*_tags_assoc` | vocabulary + per-oparl_key attachments w/ `scheme`,`source`,`confidence` | `file_tags` (doc_key, tag, conf) | instruments **match** (`oparl_key` string, confidence float) → migrate to assoc w/ `scheme='kg-topic'`, `source` from the TagManager-valid vocabulary |

Gaps found during analysis:

* SQLite `doc_key` values are oparlKey strings; **5 files in the store
  carry no `File_chunks`** (Unzerwerte 'untexted' skipping) — the tag
  migration must LEFT-join to `File` and warn on misses.
* `warnings`: SQLite `pairs.pair_key` is a compound string; never
  re-parse it except for the documented split (two components, no
  escaping needed — OParl ids contain no `|`).

### 1.2 Association tables verdict (requested check)

`pair_documents` — the pair↔document role matrix — **does NOT map
onto riski's existing assoc tables**:

* `File__paper__Paper` etc. denote *untyped* attachments; our rows
  carry **role** (request/modification/response/attachment),
  **verify_note** (OCR-warn note, protocol verdicts) and **pair**
  context (a document may be 'response' in one pair and the same-dated
  paper's 'attachment' in another). Losing role/note would break the
  contradiction-inheritance built up by kgProtocols/kgAbstimmung.
* `Paper__consultation__Consultation` stays as is (source of truth);
  `kg_pairs` complements it with outcome/signal/chain semantics.

**Decision (proposal):** dedicated `kg_*` tables; no repurpose of
existing association tables. Instead kg data *references* them
(`doc_sid` FK) and *joins* like any riski table. The existing
`File_tags_assoc` is the one place we *reuse* — because the
scheme/source columns already anticipate provenance-stamped tags from
different vocabularies (that's exactly the 'different number of tags
later' requirement).

## 2. Target schema (additive, `kg_` prefix, typed)

```sql
-- vocabulary (evolvable: adding a tag/qualifier = INSERT, no DDL)
CREATE TABLE kg_tags (
    tag         VARCHAR(64) PRIMARY KEY,
    description TEXT NOT NULL,
    active      BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE TABLE kg_qualifiers (
    tag         VARCHAR(64) NOT NULL REFERENCES kg_tags(tag),
    qualifier   VARCHAR(64) NOT NULL,
    description TEXT NOT NULL,
    PRIMARY KEY (tag, qualifier)
);

-- pair layer (one row per (paper, meeting) — the sqlite 'pairs')
CREATE TABLE kg_pairs (
    pair_id       BIGSERIAL PRIMARY KEY,
    paper_sid     INTEGER NOT NULL REFERENCES "Paper"(sid),
    meeting_sid   INTEGER NOT NULL REFERENCES "Meeting"(sid),
    paper_oparl   TEXT NOT NULL,
    meeting_oparl TEXT NOT NULL,
    session_date  DATE,
    request_type  VARCHAR(64),
    outcome       VARCHAR(64),
    outcome_confidence REAL,
    outcome_signal VARCHAR(32),     -- column|regex|vector|protocol|db-partial
    pre_stage     BOOLEAN NOT NULL DEFAULT FALSE,
    status        VARCHAR(24) NOT NULL DEFAULT 'identified',
    UNIQUE (paper_sid, meeting_sid)
);

-- role matrix (the sqlite 'pair_documents' incl. verify_note)
-- PK fix (review finding 5): role joins the key — a file may appear in
-- two roles within one pair (Anlage that is also the response extract);
-- kgIdentify/kgProtocols currently emit one role per (pair, file) — the
-- wider PK makes that an invariant rather than an accident
CREATE TABLE kg_pair_documents (
    pair_id     BIGINT REFERENCES kg_pairs(pair_id),
    file_sid    INTEGER NOT NULL REFERENCES "File"(sid),
    role        VARCHAR(24) NOT NULL,   -- request|modification|response|attachment
    verify_note TEXT,
    PRIMARY KEY (pair_id, file_sid, role)
);

-- item history chain (design D10)
CREATE TABLE kg_pair_links (
    prev_pair_id BIGINT REFERENCES kg_pairs(pair_id),
    next_pair_id BIGINT REFERENCES kg_pairs(pair_id),
    relation     VARCHAR(16) NOT NULL DEFAULT 'next',
    PRIMARY KEY (prev_pair_id, next_pair_id)
);

-- statements (field bags stay JSON — the field list WILL evolve)
-- PK fix (review finding 3): an expression PK is invalid DDL and PK
-- columns cannot be nullable. Use surrogate id + expression unique index:
CREATE TABLE kg_statements (
    id          BIGSERIAL PRIMARY KEY,
    pair_id     BIGINT NOT NULL REFERENCES kg_pairs(pair_id),
    stage       VARCHAR(16) NOT NULL,   -- request|response|author|link
    doc_sid     INTEGER REFERENCES "File"(sid),  -- NULL = pair-level
    fields_json JSONB NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX kg_statements_uq
    ON kg_statements (pair_id, stage, COALESCE(doc_sid, 0));

-- staleness (review finding 4): regeneration is detected at the
-- kg_pairs level (outcome/signal changes on upsert) and statements are
-- rewritten in place via the unique index upsert; updated_at + the
-- pipeline_version marker on kg_pairs carry freshness (no separate
-- stale flag — absence of an updated statement AFTER an outcome change
-- is detectable by comparing kg_pairs.updated_at vs kg_statements.updated_at)
-- kg_pairs gains: updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), pipeline_version VARCHAR(32)

-- cross-check verdicts (round-trip)
CREATE TABLE kg_crosschecks (
    pair_id BIGINT PRIMARY KEY REFERENCES kg_pairs(pair_id),
    verdict VARCHAR(16) NOT NULL,       -- passed|failed
    reason  TEXT
);

-- grounded qualifier assignments
CREATE TABLE kg_doc_qualifiers (
    file_sid   INTEGER NOT NULL REFERENCES "File"(sid),
    tag        VARCHAR(64) NOT NULL REFERENCES kg_tags(tag),
    qualifier  VARCHAR(64) NOT NULL REFERENCES kg_qualifiers(tag, qualifier),
    confidence REAL NOT NULL,
    provenance VARCHAR(32) NOT NULL DEFAULT 'sysone',
    PRIMARY KEY (file_sid, tag, qualifier)
);

-- tag freshness (interplay analysis 2026-11-19): association rows
-- carry updated timestamps so derived tagging skips stale re-runs —
-- additive column on the EXISTING tables, serves both kg-topic and
-- the legacy document-type scheme; TagManager sets it on add
ALTER TABLE "File_tags_assoc" ADD COLUMN IF NOT EXISTS updated TIMESTAMPTZ;
ALTER TABLE "Paper_tags_assoc" ADD COLUMN IF NOT EXISTS updated TIMESTAMPTZ;
ALTER TABLE "AgendaItem_tags_assoc" ADD COLUMN IF NOT EXISTS updated TIMESTAMPTZ;

-- per-file chunk counts captured during identification
CREATE TABLE kg_file_meta (
    file_sid    INTEGER PRIMARY KEY REFERENCES "File"(sid),
    chunk_count INTEGER NOT NULL
);
```

Tags: the sqlite `file_tags` rows go into **`File_tags_assoc`**
(`oparl_key = doc_key`, `scheme='kg-topic'`, `source` from the TagManager-valid vocabulary,
`confidence=same`) with `kg_tags` synced into `File_tags` — so riski's
existing tag display/filter paths see them without new plumbing, and
later changes (extra tags/qualifiers) are pure data.

## 3. Migration script design (`src/kg/kgMigrate.py`)

Single idempotent script, stages in fixed order, **dry-run by
default**; `--apply` to execute:

```
1. connect pg (RW credentials, src.db layer) — mirrors current scripts
2. ensure schema — CREATE TABLE IF NOT EXISTS … (DDL of §2); additive
   changes later = ALTER TABLE ADD COLUMN IF NOT EXISTS (verify_note
   pattern reused)
3. vocab sync     — kg_tags/kg_qualifiers ← config/kg_vocabulary.yaml
                    (single source of truth, same rule as SQLite phase)
4. pairs          — read sqlite, split pair_key, resolve sids:
                    LEFT JOIN "Paper"/"Meeting" ON oparlId; report misses
                    before writing (expect 0; else fail with list)
5. pair_documents — per doc_key resolve File.sid via oparlKey join;
                    carry verify_note
6. pair_links     — remap sqlite pair_key→pair_id
7. statements     — fields_json→JSONB (jsonb validates; sqlite was
                    hand-JSON — parse strictly, report malformed)
8. crosschecks    — straightforward
9. tags           — File_tags upsert (tag list) + File_tags_assoc
                    upsert on (oparl_key, tag_id, scheme='kg-topic')
                    + kg_doc_qualifiers (grounded; rejects undefined via
                    dictionaries — no drift)
                    PREREQ (review finding 2): File_tags_assoc has NO
                    unique constraint on (oparl_key, tag_id, scheme) —
                    only the surrogate id PK. The migration (or
                    TagManager, better) creates a partial unique index
                    `ON (oparl_key, tag_id, scheme) WHERE scheme IS NOT
                    NULL` before the upserts; TagManager's
                    exists-then-insert stays as the runtime path
10. file_meta
11. verify counts — per-table sqlite rows vs pg rows; full-diff report;
                    mismatches abort (apply-mode) or list (dry-run)
```

* **Idempotent:** every step is ON CONFLICT upsert → re-runs merge; a
  partial first run resumes (the mandatory property from SQLite days).
* **Transaction-span control:** commit per step (learned from run6).
* **Execution time:** dominated by step 5 (~29k rows) and 9 (~53k
  existing assoc rows to consult) — minutes, not the statement era.
* Arguably run inside `src/` conventions (`_bootstrap`, `RO_USER`
  reads, RW writes) exactly like `pgGeoGateCleanup.py`'s style.

## 4. Extension plan for later evolution (the 'we might want changes' requirement)

* **new tags / qualifiers**: add to `kg_vocabulary.yaml` → migrating
  script upserts `kg_tags`/`kg_qualifiers` & `File_tags`; optional
  `--retag-after-sync` deletes `scheme='kg-topic'` assoc rows to force
  a re-classification pass (using kgTagSystemOne) — mirrors the
  SQLite-phase doctrine of 'definitions land on next run'.
* **new statement fields**: JSONB absorbs schema growth; the field
  list itself lives in `kg_statements.fields_json` and the extractor
  code, no DDL constraint guards.
* **new stages/methods**: `outcome_signal`/`source` columns are open
  domains (documented vocabularies, no CHECK), so a new pipeline
  generation can annotate without schema change.
* **pg-faceted filters**: `kg_*` tables get trigram indexes on
  pair-level column names where relevant (follow riski pattern) —
  deferred until the search layer consumes them (task 8.2, not part
  of the migration).

## 5. Updatable flow — new documents keep coming (design decision)

PostgreSQL is the *living* store (riski's syncIncremental feeds it
continuously), so the kg layer's ingestion cannot be a one-shot
migration — it must be a **re-runnable incremental update stage** in
the regular workflow:

```bash
# the established riski data-update workflow gains a kg step:
python src/syncIncremental.py                     # as today (PG grows)
python src/pgOcr.py … && python src/pgAddSummaries.py …   # as today
python -m src.kg.kgDryRun   # (replaced by) kgMigrate.py --apply  ← kg layer
python -m src.kg.kgStatements --endpoint olc …           # statements for the NEW pairs only
```

Update semantics (per layer):

| kg table | incoming-document behaviour |
|---|---|
| `kg_pairs` | kgIdentify re-run over the (now larger) Papers — the UNIQUENESS `(paper_sid, meeting_sid)` makes re-runs merge: existing rows keep verdicts/outcome only if the DB signal improves (upsert with `excluded.outcome_signal` priority order); new documents create new pairs with `outcome=NULL` |
| `kg_pair_documents` | new attachments arrive with protocols/ballots via the same kgProtocols/kgAbstimmung verification gates — verify_note carries the fresh verification; stale notes are refreshed by the rerun verdict (revisions ARE expected: OParl can deliver modified protocols) |
| `kg_statements` | extractor processes only `status='identified'` pairs (resumability semantics kept); outcome changes (e.g. vertagt → decided) **regenerate** the affected pair's statements by the same version-pegging mechanism riski uses (`modified` timestamps on Paper/AgendaItem rows) — a "statement stale before X" marker through `pipeline_version` |
| `File_tags_assoc` (scheme='kg-topic') | new Files get tagged by kgTagSystemOne on the next run (skips already-tagged doc_keys); vocabulary changes stay data-only |
| `kg_crosschecks` | recycled on rerun (verdict+reason refresh, unchanged pairs skipped) |

**Dependency chain (paradigmatic):** any stage can only touch rows
whose inputs changed since its last successful run — ACID by
checkpoint date table:

```sql
CREATE TABLE kg_ingestion_runs (
  stage VARCHAR(32) PRIMARY KEY,          -- identify|protocols|abstimmung|
        -- chains|tags|statements|crosscheck|migrate
  last_synced_at TIMESTAMPTZ NOT NULL,    -- cursor = riski baseline parity
  last_status  VARCHAR(16) NOT NULL,      -- ok|partial|failed
  last_count   INTEGER
);
```

So the kg ingestion follows the *oparlUpdateRuns* pattern (established
riski architecture, rights: when it fails, re-run is the recovery path
and no row is duplicated).

Deletion semantics (documents removed at source): VERIFIED in the
corpus (review finding 6) — `deleted` is an additive scalar column
pgGen creates when OParl delivers it (e.g. `Consultation.deleted` from
the 2026-10-26 crawl); live counts: Paper 4, Consultation 4, File 53
deleted=true rows. Caveat: the flag appears only when the source sends
it — removals that OParl communicates by *disappearance* (row vanishes
from the feed) are NOT flagged. The kg retired-path therefore fires on
`deleted=true` AND on sid-resolution misses during incremental runs
(a pair whose Paper vanished from PG entirely is retired, not
orphaned). The `--apply` requires a preceding riski baseline run —
otherwise the kg stage is a no-op.

## 5b. Review findings (mistral review, 2026-11-19) — disposition

| # | finding | disposition |
|---|---|---|
| 1 | `source='sysone'` rejected by TagManager `_VALID_SOURCES` | **fixed**: extend `_VALID_SOURCES` with kg sources (`sysone`, `llm-kg`) — TagManager stays the single write path |
| 2 | `File_tags_assoc` has no unique (oparl_key, tag_id, scheme) constraint — ON CONFLICT would fail | **fixed**: partial unique index `ON (oparl_key, tag_id, scheme) WHERE scheme IS NOT NULL` created by the migration (or TagManager); verified live: table only has the surrogate id PK, scheme nullable |
| 3 | `PRIMARY KEY (pair_id, stage, COALESCE(doc_sid, 0))` invalid DDL | **fixed**: surrogate id + expression-based unique index |
| 4 | staleness mechanism asserted but not designed | **fixed**: kg_pairs gains `updated_at` + `pipeline_version`; regeneration detected at pair level, statements rewritten via the unique-index upsert (staleness = pairs.updated_at > statements.updated_at) |
| 5 | `kg_pair_documents` PK forbids two roles for one file | **fixed**: role joins the PK (invariant stated) |
| 6 | `deleted=true` convention unverified | **verified live**: additive scalar column when OParl delivers it (Paper 4, Consultation 4, File 53 rows); caveat: disappearance-without-flag is not covered → sid-resolution misses in incremental runs also retire pairs |
| 7 | kg_tags duplicates File_tags; column-width mismatch | **kept** (kg_tags carries description/active which File_tags lacks) with sync direction fixed YAML → kg_tags → File_tags projection; width harmonized to VARCHAR(255) |

## 6. Open questions for the review

1. RW credentials for migration: `DB_USER` (riski) vs `.env`
   `RW_USER/RW_PWD` — script uses `src.db.get_engine()` (default), so
   the current principale applies; confirm.
2. `kg_pairs.status` — resolved as 'keep, repurposed' (see §5): the
   column becomes the *pairness* freshness marker for incremental
   ingestion (identified→statements→crosscheck etc.) rather than a
   one-shot migration art fact; new pairs enter at 'identified' like
   today's pipeline, indefinitely.
3. tag scheme naming: `kg-topic` proposed; alternative
   `topic-riski:<scheme-version>` — needs a decision.
4. Full Tristan check: sqlite `doc_key` ↔ `File.oparlKey` misses must
   be zero (initial sampling suggests yes: doc keys were sourced from
   PostgreSQL originally); if not, script lists them for a
   correction round.
