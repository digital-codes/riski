# Tasks: categorization-indexing

## 1. Spikes (read-only, before design freeze)

- [ ] 1.1 Probe `Paper.data` JSON: `keyword[]` populated? coverage %
- [ ] 1.2 Probe `Paper.data` JSON: `originatorPerson`/`originatorOrganization`, `mainFile` populated?
- [ ] 1.3 Probe `File`: length distribution of `content`, split fulltext-vs-summary (5k cutoff)
- [ ] 1.4 Probe `Paper.paperType`: distinct values + coverage %; compare with `pgAddTags` group vocab
- [ ] 1.5 Probe name-vector tables: which `{item}_name_vecs` exist, row counts vs item tables
- [ ] 1.6 Record spike conclusions in this change's design.md (or link a report)

## 2. Schema + tag model

- [ ] 2.1 Extend `pgTagMgr`: add `scheme`, `source`, `confidence` columns to `{item}_tags_assoc` (additive, on-demand migration), preserve existing API
- [ ] 2.2 `pgGen.py`: add `File.contentKind` column (+ index), set by content loaders going forward; backfill heuristic for legacy rows
- [ ] 2.3 Unit tests: tag add/query with scheme/source/confidence; precedence helpers
- [ ] 2.4 Coverage report script: % files/items per layer (content, teaser, embeddings, name vecs, tags)

## 3. Category derivation + backfill

- [ ] 3.1 Implement `src/pgCategorise.py`: paperType → document-type tags (source=papertype)
- [ ] 3.2 Regex pass over AgendaItem/File names (reuse `pgAddTags` patterns) → document-type tags (source=name-regex)
- [ ] 3.3 Batch LLM pass over `File.teaser` for regex-misses → topic/document-type tags (source=llm), teaser-first escalation, bounded cost
- [ ] 3.4 (spike-dependent) Harvest `keyword[]` → topic tags (source=oparl-keyword); `originator*`/`mainFile` → columns or associations, else document "not populated"
- [ ] 3.5 Run backfill; produce coverage report; keep `pgAddTags` JSON export as compatibility shim
- [ ] 3.6 Unit + integration tests: derivation idempotency, precedence order, rerun safety

## 4. Hybrid search + filters in pgTimeline

- [ ] 4.1 Name-vector backfill: populate missing `{item}_name_vecs` (Paper, AgendaItem, Meeting, File) via NameVecs helper
- [ ] 4.2 Lexical recall: trigram `similarity()`/ILIKE candidate lists over indexed name columns (θ and top-N configurable)
- [ ] 4.3 RRF fusion of lexical + name-vector + content-vector lists (k=60 default, per-signal toggle)
- [ ] 4.4 Filter model: parse/validate structured filters; apply pre-fusion (paperType, year range with basis, result, role/authoritative, tag scheme values, district)
- [ ] 4.5 Facet listing: `facets` section (distinct paperType/result values, years, tag counts per scheme)
- [ ] 4.6 Result JSON: additive `matched_entities`, `facets`, `applied_filters` sections; `top_files` unchanged; graph section per add-network-view contract
- [ ] 4.7 Update/extend `src/tests/test_unit_pgTimeline.py` for fusion, filters, facets; regenerate `app/src/assets/sampleData.json`

## 5. Contract handoff (do not forget — ties to add-network-view)

- [ ] 5.1 Document the search-result + filter contract delta in `add-network-view/design.md` (node `attrs` from tags/facets; Person/semantic edge types)
- [ ] 5.2 File follow-up change draft for the interactive API layer (`/search`, `/expand`) consuming this contract
