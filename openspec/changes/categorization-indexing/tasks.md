# Tasks: categorization-indexing

## 1. Spikes (read-only, before design freeze)

- [x] 1.1 Probe `Paper.data` JSON: `keyword[]` populated? coverage %
- [x] 1.2 Probe `Paper.data` JSON: `originatorPerson`/`originatorOrganization`, `mainFile` populated?
- [x] 1.3 Probe `File`: length distribution of `content`, split fulltext-vs-summary (5k cutoff)
- [x] 1.4 Probe `Paper.paperType`: distinct values + coverage %; compare with `pgAddTags` group vocab
- [x] 1.5 Probe name-vector tables: which `{item}_name_vecs` exist, row counts vs item tables
- [x] 1.6 Record spike conclusions in this change's design.md (or link a report)

## 2. Schema + tag model

- [x] 2.1 Extend `pgTagMgr`: add `scheme`, `source`, `confidence` columns to `{item}_tags_assoc` (additive, on-demand migration), preserve existing API
- [x] 2.2 `pgGen.py`: add `File.contentKind` column (+ index), set by content loaders going forward; backfill heuristic for legacy rows
- [x] 2.3 Unit tests: tag add/query with scheme/source/confidence; precedence helpers
- [x] 2.4 Coverage report script: % files/items per layer (content, teaser, embeddings, name vecs, tags)

## 3. Category derivation + backfill

- [x] 3.1 Implement `src/pgCategorise.py`: paperType → document-type tags (source=papertype)
- [x] 3.2 Regex pass over AgendaItem/File names (reuse `pgAddTags` patterns) → document-type tags (source=name-regex)
- [x] 3.3 Batch LLM pass over `File.teaser` for regex-misses → topic/document-type tags (source=llm), teaser-first escalation, bounded cost
- [x] 3.4 (spike-dependent) Harvest `keyword[]` → topic tags (source=oparl-keyword); `originator*`/`mainFile` → columns or associations, else document "not populated"  *(spike 2026-10-23: all probed fields 0% populated — recorded in design.md; no harvest needed)*
- [x] 3.5 Run backfill; produce coverage report; keep `pgAddTags` JSON export as compatibility shim  *(papertype: 13,528/13,528 Papers; regex: File 74.7%, AgendaItem 27.7%; LLM escalation pool = 25,119 unmatched names — full LLM backfill deferred to operator run)*
- [x] 3.6 Unit + integration tests: derivation idempotency, precedence order, rerun safety

## 4. Hybrid search + filters in pgTimeline

- [ ] 4.1 Name-vector backfill: populate missing `{item}_name_vecs` (Paper, AgendaItem, Meeting, File) via NameVecs helper  *(deferred: ~82k embedding calls — operator run; hybrid degrades gracefully to lexical+content meanwhile)*
- [x] 4.2 Lexical recall: trigram `similarity()`/ILIKE candidate lists over indexed name columns (θ and top-N configurable)
- [x] 4.3 RRF fusion of lexical + name-vector + content-vector lists (k=60 default, per-signal toggle)
- [x] 4.4 Filter model: parse/validate structured filters; apply pre-fusion (paperType, year range with basis, result, role/authoritative, tag scheme values, district)
- [x] 4.5 Facet listing: `facets` section (distinct paperType/result values, years, tag counts per scheme)
- [x] 4.6 Result JSON: additive `matched_entities`, `facets`, `applied_filters` sections; `top_files` unchanged; graph section per add-network-view contract
- [x] 4.7 Update/extend `src/tests/test_unit_pgTimeline.py` for fusion, filters, facets; regenerate `app/src/assets/sampleData.json`

## 5. Contract handoff (do not forget — ties to add-network-view)

- [x] 5.1 Document the search-result + filter contract delta in `add-network-view/design.md` (node `attrs` from tags/facets; Person/semantic edge types)
- [x] 5.2 File follow-up change draft for the interactive API layer (`/search`, `/expand`) consuming this contract  *(drafted: openspec/changes/api-search-expand/proposal.md)*
