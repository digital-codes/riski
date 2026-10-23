# Design: categorization-indexing

## Spike Results (2026-10-23, read-only probes — tasks 1.1–1.5)

| Probe | Result | Consequence |
|---|---|---|
| `Paper.data.keyword[]` | **0% populated** (0/13,528) | Harvest step 3.4 for keywords is a no-op; documented "not populated" |
| `Paper.data` originator*/mainFile/submitter | **0% populated** | No free submitter/originator edges; submitter facet would need rule-based derivation (desinformationssystem pattern) — out of scope here |
| `File.content` length | 46,192/47,781 populated; **99.3% ≤5k chars** (p50=1,656); only 348 files >5k | The 5000-char cutoff barely bites; contentKind split matters less than assumed — heuristic backfill acceptable |
| `File.teaser` | 46,192 populated; p50=897 chars (max 16,000) | Teaser-first LLM escalation viable at full corpus scale |
| `Paper.paperType` | **100% coverage** (13,528/13,528). Top: Beschlussvorlage 8,168 · Antrag 1,844 · Anfrage 1,531 · Änderungs-/Ergänzungsantrag 788 · Informationsvorlage 670 · plus ~30 `Haushalt THH <n>` variants and Offenlage etc. | Authoritative document-type base needs a canonicalization rule: fold `Haushalt THH *` → `Haushalt` (keep THH code as association attr) |
| name_vecs tables | **NONE exist**; contentEmbeddings: 44,785/47,781 (93.7%) | Task 4.1 must create + populate Paper/AgendaItem/Meeting/File name vectors (~82k embeddings total — significant embedding job, batch it) |
| `AgendaItem.result` | 9,741/18,424 populated; rich values (Kenntnisnahme, einstimmig beschlossen, mehrheitlich abgelehnt, …) | Viable outcome facet; consider normalizing into wenige Kategorien (zugestimmt/abgelehnt/beschlossen/erledigt/…) for the filter UI |
| `Consultation.role` | 100% populated (Entscheidung 6,551 · unbekannt 4,050 · Kenntnisnahme · Vorberatung · …) | Viable role facet out of the box |

## Context

Search today (`pgTimeline.search_and_build_timeline`) is a single-signal
pipeline: embed query → pgvector cosine over `contentEmbeddings` (File
content, truncated at ~5–8k chars due to embedding-model context) →
threshold → rerank → neighborhood traversal. Infrastructure for more already
exists but is unwired: trigram GIN indexes on `name` (Paper, File,
AgendaItem, Meeting — `pgGen.py:445`), btree on `paperType`, name-vector
helper (`pgNameVecs` / `{item}_name_vecs`), tag tables (`pgTagMgr`), and the
text pyramid `content` (fulltext-or-summary) → `teaser` (~200-char LLM
compress) → `contentEmbeddings`.

## Goals / Non-Goals

**Goals:**
- One canonical, queryable category vocabulary with provenance.
- Hybrid recall (lexical + 2× vector) with existing indexes; reranker stays
  final arbiter.
- Structured, composable filters usable by search CLI, future API, and the
  network view.
- Zero breaking changes; all additions are additive columns/tables/JSON
  sections.

**Non-Goals:**
- Content chunking / re-embedding (documented tradeoff: the ~5k-char cutoff
  stays; acceptable because reranking arbitrates final quality).
- Full-text (tsvector) search over content; trigram-on-names is sufficient
  for now (tsvector on `name` remains a non-breaking future addition).
- Importing raw markdown into Postgres.
- API server / UI work (follow-up; see proposal note).

## Decisions

### 1. Canonical tag model (extends pgTagMgr)

```
{item}_tags:        id, tag (unique)          ← as today
{item}_tags_assoc:  tag_id, oparl_key         ← as today
  + columns:        scheme     VARCHAR(64)    -- document-type|topic|district|submitter|org
                    source     VARCHAR(32)    -- papertype|oparl-keyword|name-regex|llm|manual
                    confidence REAL DEFAULT 1.0
```

- Same tag name may exist under multiple schemes (e.g. "Bauantrag" as
  document-type from papertype, as topic from LLM) — scheme is part of the
  facet namespace, disambiguating the current vocabulary overlap.
- Precedence for document-type tags: papertype (1.0) > oparl-keyword (0.9) >
  name-regex (0.7) > llm (0.5). Consumers (search facets, graph styling)
  may filter by source/confidence.
- Existing `{item}_tags` API (add/query by all/any) is preserved; new columns
  are additive with defaults.

### 2. Category derivation pipeline (`pgCategorise.py`)

```
for each Paper:     paperType ──────────────▶ scheme=document-type, source=papertype
spike-dependent:    data.keyword[] ──────────▶ scheme=topic, source=oparl-keyword
for AgendaItem/File (name): FILE/AGENDA_GROUP_PATTERNS ─▶ document-type, source=name-regex
for File:           teaser ──regex fail?──▶ batch LLM classify ─▶ topic/document-type, source=llm
district:           reuse Districts_items_AgendaItems ▶ scheme=district (or keep as-is)
```

- Teaser-first escalation: LLM call only for files where regex found nothing
  (~bounded cost, teaser is 200 chars).
- Idempotent/backfillable; `--force` semantics follow pgTeasers precedent.
- Coverage report at the end: % items per table having ≥1 tag per scheme.

### 3. File contentKind + pipeline consistency

- `ALTER TABLE File ADD COLUMN contentKind VARCHAR(16)` — values
  `fulltext` | `summary` | NULL, set by the loader that writes `content`.
- Backfill by length-threshold heuristic (the loaders' documented cutoff),
  recorded in the report as approximate for legacy rows.
- Re-derivation order fixed and documented: content → teaser → tags →
  embeddings; each step detects stale inputs by timestamp/coverage, so
  partial reruns don't desync layers.

### 4. Hybrid recall + fusion

```
candidates( q ) =
   L  = trigram lexical: similarity(name, q) > θ_L  on Paper/File/AgendaItem/Meeting
        (GIN idx already exists; top-N per table)
   Vn = name vectors:  {item}_name_vecs <=> embed(q), top-N per table
        (coverage check + backfill task; Paper/AgendaItem seeding new)
   Vc = content vectors: contentEmbeddings <=> embed(q), top-N   (today's path)
FUSED = RRF( L, Vn, Vc, k=60 )            -- ~20 lines, rank-based, no score calibration
RESULT = rerank( FUSED.top_M )            -- existing reranker, File.content
```

- Name-vector coverage task: check which `{item}_name_vecs` tables exist and
  are populated; backfill via the existing NameVecs helper. Short text →
  embedding-model limit is a non-issue here.
- One embed(q) call shared by Vn and Vc.
- Seed-type expansion: results may now seed the graph from Paper/AgendaItem/
  Meeting directly (multiple entry points) — result JSON stays additive:
  current `top_files` unchanged, new `matched_entities` section.

### 5. Structured filter model (the facets users asked for)

```json
"filters": [
  { "facet": "paperType",  "op": "in",    "values": ["Beschlussvorlage"] },
  { "facet": "year",       "op": "range", "from": "2021", "to": "2022",
    "basis": "meeting" },        // Paper.date | meeting.start_date | File.date
  { "facet": "result",     "op": "in",    "values": ["beschlossen"] },   // AgendaItem.result
  { "facet": "role",       "op": "in",    "values": ["entscheidend"] },  // Consultation.role
  { "facet": "tag",        "scheme": "district", "op": "in", "values": ["Innenstadt-Ost"] },
  { "facet": "authoritative", "op": "eq", "value": true }               // Consultation
]
```

- Applied **pre-fusion** to candidate lists (WHERE clauses on indexed
  columns / tag assocs) — cheap, reduces rerank volume.
- Same filter model is echoed in results as `applied_filters` and, per
  add-network-view contract, node `attrs` carry facet values so the UI can
  filter the graph client-side too.
- Facet value listing (for UI dropdowns): `facets` section in results —
  distinct paperType values (indexed), result values (pgAddTags already
  extracts them), years present, tag counts per scheme.

## Risks / Trade-offs

- **RRF dilutes vector-only precision** if lexical candidates are noisy →
  mitigated by reranker + tunable per-signal top-N; can disable signals per
  query.
- **LLM classification cost** on ~46k files → bounded by teaser-first
  escalation; regex pass expected to cover the majority (pgAddTags group
  coverage suggests high hit rate on standard agenda wording).
- **keyword[]/originator spikes may come back empty** → design degrades
  gracefully: derivation (decision 2) is independent of the harvest.
- **contentKind backfill is heuristic for legacy rows** → documented, not
  load-bearing until loaders set it going forward.

## Migration Plan

1. Spike queries (keyword, originator, mainFile, content-length split,
   paperType coverage, name_vecs coverage).
2. Schema additions (assoc columns, contentKind) + pgTagMgr extension +
   unit tests.
3. pgCategorise backfill + coverage report.
4. pgTimeline: hybrid recall + filters + facets/`matched_entities` sections
   + tests.
5. Regenerate sample data; hand contract deltas to add-network-view tasks
   4.x and the future API change.
