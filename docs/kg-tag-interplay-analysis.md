# kg ↔ legacy tag system interplay & update-integration analysis

*2026-11-19 — analysis requested before kgMigrate implementation.*

## 1. Overlap/interference check: `pgTagMgr`, `pgCategorise`, `pgAddTags` vs kg tagging

**Documented verdict: coexistence is safe by scheme isolation, with two
required code changes (already planned in kg-postgres-integration
tasks):**

| mechanism | tables | idempotency today | interference risk with kg |
|---|---|---|---|
| `pgCategorise` (papertype→regex→LLM escalation) | `*_tags`/`*_tags_assoc`, scheme `document-type`, sources `papertype/name-regex/llm` | re-runs skip already-tagged items (`already_tagged` counter); TagManager dedups silently | **none on rows** — different scheme; only shared resource is the tag *catalog* (`File_tags` tag names) — kg topic names (Mobility, Economy…) do not collide with document-type names (Anträge, Protokolle…) |
| `pgAddTags` (legacy influencer tags, withdrawn-name convention) | same assoc, scheme none/`document-type` | re-runs skip withdrawn prefixes | none — different scheme and tag names |
| kg `kgTagSystemOne` (SQLite today, PG later) | → `File_tags_assoc` scheme `kg-topic`, sources `sysone`/`llm-kg` | SQLite skips already-tagged `doc_key` | after migration: **must skip already-tagged oparl_keys in the kg scheme** (mirroring pgCategorise) — rule below |

**Schema detail that guarantees non-interference:** `File_tags_assoc`
has no per-scheme uniqueness yet (finding 2 of the mistral review);
once the partial unique index
`(oparl_key, tag_id, scheme) WHERE scheme IS NOT NULL` exists, the two
systems can write the *same document* with the *same tag name* under
*different schemes* without collision — and TagManager dedup stays
correct within each scheme. `source` is part of TagManager validation
(extended `_VALID_SOURCES` with kg sources) but NOT part of the unique
key: re-adding the same (key, tag, scheme) with a different source is
silently ignored by TagManager today — meaning **the kg re-tag with a
newer confidence would be a no-op unless the association is deleted
first**. → kg re-classification passes must `DELETE … WHERE scheme =
'kg-topic'` for the affected keys before re-adding (same rule the
`--retag-after-sync` step already defines).

**Catalog sharing:** `File_tags` is a shared name→id catalog. kg adds
23 topic names once; `pgCategorise.add_tags_to_catalog` tolerates
existing names. No conflict, but the `kg_tags.description` /
`active` metadata does NOT exist in `File_tags` (richer columns live
in `kg_tags` — kept by review finding 7).

## 2. Update integration: timestamps & dedup for the kg layer

**pgGen's precedent** (`ON CONFLICT DO UPDATE … WHERE excluded.modified
> existing.modified`, baseline advancement only after successful
import, crash recovery = re-run) is the pattern to copy — but kg rows
have **no `modified` timestamp of their own** in the OParl feed
(statements/tags are *derived* data). The derived layer therefore

* keys freshness on the **source objects' `modified` timestamps**
  (`Paper.modified`, `Meeting.modified`, `File.modified` — the riski
  import already updates those on change), not on invented clocks;
* and records **when kg last processed what** in `kg_ingestion_runs`
  (per stage; proposal §5).

Concrete per-stage dedup rules:

| stage | skips | refreshes |
|---|---|---|
| kgIdentify | pairs whose (paper_sid, meeting_sid) exists AND source `modified` unchanged since `kg_ingestion_runs.identify.last_synced_at` | new papers/meetings → new pairs; changed sources → outcome/verdict re-derivation (sql upsert, signal priority) |
| kgProtocols / kgAbstimmung | pair-documents already attached with the same verify verdict | files newly arriving (new `File.modified`) → attach-to-existing-pair pass (the mechanism kgAbstimmung used to jump 267→792 response docs mid-run) |
| kgStatements | pairs at `status='statements'` whose (paper.modified, meeting.modified) are older than the statement's `kg_statements.updated_at` | outcome/signal changed (`kg_pairs.updated_at` > statement `updated_at`) → re-extract; new pairs → extract |
| kgTagSystemOne | documents tagged under scheme `kg-topic` with `assoc.updated ≥ File.modified` — **requires adding a `modified`/`updated` timestamp to `*_tags_assoc`** (today the table has none — see below) | new/changed Files → tag |
| kgCrossCheck | pairs whose statements are fresh (per above) and a verdict exists | fresh statements without verdict, or statements re-generated after an outcome change |

**Required schema amendment (the "timestamps for tags" ask):** add an
additive column `*_tags_assoc.updated TIMESTAMPTZ DEFAULT now()` to the
three tag assoc tables (same `ADD COLUMN IF NOT EXISTS` pattern riski
uses everywhere) OR track tagging freshness only in
`kg_file_tag_runs`-style bookkeeping. The column is preferred — it
also serves the legacy `document-type` scheme (pgCategorise
backfills), giving ALL tagging the same freshness semantics.

**TagManager wiring:** `add_tags()` gains a `delta` guard parameter or
stays pure-insert (current: silently ignores duplicates) — for
re-classification the *caller* deletes scheme-scoped rows first (the
`--retag-after-sync` doctrine). For update flows the delete-then-add
keeps confidence/source fresh and avoids the silent-ignore trap.

## 3. Resolved conclusions

1. No interference between old and new tagging *by scheme*; two code
   changes make it explicit and orderly (unique index, `_VALID_SOURCES`
   extension) — both already in `kg-postgres-integration` tasks.
2. kg inherits pgGen's upsert doctrine and adds the derived-data
   refinement: freshness = source `modified` timestamps (per pair per
   stage) + `kg_ingestion_runs` cursors, NOT invented kg clocks.
3. New tag timestamp: add `*_tags_assoc.updated` column (additive) —
   serves both kg-topic and document-type schemes; TagManager should
   set it on add.
4. The running SQLite bulk processes do NOT migrate rows directly;
   `kgMigrate` reads the store at apply-time and the id-driven upserts
   make repeated migrations safe — the SQLite store stays the
   producer until the first `--apply`, after which the pg layer is
   normative (kgStatus doctrine).
