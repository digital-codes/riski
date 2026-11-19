# Tasks

## 1. Scaffolding

- [x] 1.1 Create `src/kg/` package skeleton (`__init__.py`, `kgStore.py` SQLite store, `kgStatus.py` 10s-interval console reporter, `kgRemote.py` ollama-bounded model client) with type hints, docstrings and pytest unit tests for the store upsert/resume behavior; verify `python -m pytest src/tests/test_unit_kg_store.py -m unit` passes
- [x] 1.2 Seed `config/kg_vocabulary.yaml` with initial papertype/result/role mapping tables, party-name variants with era validity, and tag placeholders; verify YAML loads and mapping lookups resolve case/hyphen-insensitively (unit test)

## 2. Pair identification

- [x] 2.1 Implement `kgIdentify.py` structural traversal (Paper → Consultation → AgendaItem → Meeting, Gemeinderat filter) following the `src/pgTimeline.py` join pattern, emitting per pair the full input-document list (document id, file name, pair role: request/modification/response/attachment) with per-candidate provenance + confidence and read-only DB access; verify on a console sample run (`kgIdentify.py --sample 20`) that candidate fields and complete document lists round-trip
- [x] 2.2 Add the name-regex layer (tier 2) and vector/anchor layer (tier 3, bge-m3 similarity for show, LLM tier 4 behind `--allow-llm`); verify unmatched-wording items are reported and no item silently drops (unit test on the mapping layer + live sample run) 
- [x] 2.3 Write `docs/kgIdentify.md` (usage, output tables, sample invocation); verify the documented command runs as written and a full-DB run produces `results/` pair counts with the chunk-count, files-per-pair and modification-chain distribution report (spec: pair statistics + ≤5 chunk verification)
- [x] 2.4 Implement `kgProtocols.py` (design D9 amendment): attach agenda-item protocol files / meeting results protocols to pairs as role `response` only when TOP-number reference AND Beschluss-section outcome wording are verified against the pair; unverified stays unattached and counted; verify TOP/outcome checker on the verified sample numbers (219/244 top-match baseline) with unit tests + live run summary; document usage in `docs/kgProtocols.md`
- [x] 2.5 Implement `kgChains.py` (design D10 amendment): pre-stage flag (`pairs.pre_stage`) for all but the last pair per paper, consecutive `pair_links` table (first → … → last by meeting date), and role-derived outcome (`Kenntnisnahme` role only when result is NULL); verify on the 220 multi-meeting papers (199 with resolvable outcome) + unit tests; document in `docs/kgChains.md`

- [x] 2.6 Implement `kgAbstimmung.py` (design D13 amendment): ballot screenshots as response candidates (paper-linked + registry via name-TOP and File.date session signal), OCR vote-count cross-check vs. textual outcome with clipped-digit warnings, per-attachment verify_note (ensure_verify_note additive column); full run: 631 attached, 205 ok / 25 warn / 401 n.a., 792 pairs with response documents total; document in `docs/kgAbstimmung.md`

## 3. Tag schema + tags

- [x] 3.1 Implement `kgTagSchema.py` authoring the ris-ki tag table with one description per tag (https://ris-ki.de/ris/file-tags, qualifiers like Neubau/Sanierung/Erweiterung/Rückbau) into `config/kg_vocabulary.yaml` and the SQLite tag table; verify the seeded table renders with `kgTagSchema.py --list`
- [x] 3.2 Implement tag assignment with confidence + strictness threshold (no forced low-confidence tags; untagged counted in summary). First vector-tier `kgTags.py` (bge-m3, 50-doc sample); superseded 2026-11-18 by `kgTagSystemOne.py` (one SystemOne call per doc: all 23 tags + qualifiers, noul=confidence) — vector file removed, 20-doc SystemOne sample verified (17 tagged, conf 0.91–0.96)
- [x] 3.3 Write usage docs; verify documented commands run (`docs/kgTags.md` retired with the vector tier — SystemOne usage lives in `docs/kgStatus.md`)

## 4. Author identification

- [x] 4.1 Implement `kgAuthors.py` party extraction over request documents using the era-valid variant vocabulary (meeting-date keyed) with normalization provenance and empty-when-unknown semantics; verify on a sample spanning different years that variants normalize and unknown authors stay empty (unit test with fixture variants + live sample)
- [x] 4.2 Document usage in `docs/kgAuthors.md`; verify documented command runs

## 5. Statement extraction

- [x] 5.1 Implement `kgStatements.py` request-stage extraction (topic/title, type, meeting date, doc ids/filenames, author join, intended impact, audience, actor, precise action, start/end dates, expected benefit, cost; chunk-index source references; empty fields for absent info) with JSON-schema-constrained prompts; verify on a 10-pair sample that all required fields exist in the store, invented values absent, and resumability holds on interrupt-restart
- [x] 5.2 Implement response-stage extraction (response type, result, action, executor, expected cost, dates, modifications, dependencies/constraints like third-party funding or Haushaltssperre) and modification-chain linking (Änderungsantrag/Ergänzungsantrag → same original request; multiple responses supported); verify a sampled multi-response chain links correctly in the store
- [x] 5.3 Write `docs/kgStatements.md`; verify documented command runs

## 6. Cross-check

- [x] 6.1 Implement `kgCrossCheck.py` round-trip: render response statements to short German sample text, fact-compatibility verdict against source chunks (d3:2b decision pass, LLM tie-break); verify verdicts (pass/fail + reason) are stored and a known contradiction fixture fails. Include the extraction↔cross-check tuning loop (design D12): run cross-check on the same sample pairs after each extraction batch, adjust extraction prompts on recurring mismatch classes (max 3 iterations), record tried changes + residual rates in `results/kg_crosscheck_tuning.md`

- [x] 6.2 Implement `kgTune.py` failure diagnosis (design D14): failed cross-checks re-examined via the dedicated CCLLM route with reasons + system_issue classes; verdict upgrades (checker strictness) and pair resets for prompt-driven re-extraction; 429 retry/backoff in `systemone()` after rate-limit storms zeroed tagging batches; tuning report updated with real mismatch classes (40-pair pass: 24 checker / 14 prompt / 7 model)

## 7. Model selection

- [ ] 7.1 Implement `kgModelSelect.py` comparison harness over a fixed sample set (granite4.2:8b vs qwen3.5:4b vs mistral:latest on statement extraction + tagging quality metrics); verify `results/kg_model_selection.md` records per-model results and the selected model
- [ ] 7.2 Set the selected language model as the scripts' default and record the choice in `docs/kgModelSelect.md`; verify the default is applied when scripts run without `--model`

## 8. Export + integration

- [ ] 8.1 Implement `kgExport.py` JSON export of the store (pairs with tags, authors, statements, cross-check verdicts); verify exported JSON validates against the field sets in the specs
- [ ] 8.2 End-to-end integration run over the full DB (`kgIdentify → kgTagSystemOne → kgAuthors → kgStatements (inline crosscheck) → kgExport`): status output stays ≤10s interval, resume-safe re-run of a mid-stage interruption produces no duplicate rows, and a summary report (pair counts, tag coverage, author unknown rate, cross-check pass rate, chunk statistic) lands in `results/`; verify by running the full chain twice and diffing row counts

## Workflow follow-up

- Resume the interrupted bulk statements run per `docs/kgStatus.md`
  (`--commit-every` checkpointing; pairs at `status='statements'` are
  skipped). Then continue with 6.1 cross-check.
- Archive the change after review; copy spec purposes into main specs.
