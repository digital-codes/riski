# Proposal: fix-hybrid-search-ranking

## Why

Simple, highly-specific queries like "beteiligungsplatform" or "bürgerbeteiligung" fail to surface documents whose names/heads directly contain those terms. Two causes: (1) RRF fusion weights all recall signals identically regardless of signal type, so a strong lexical hit ranks below weak vector hits; (2) the rerank stage silently discards any file scoring < 0.8 — including lexical-only matches that the reranker scores imperfectly on a head/chunk — so such documents never reach `top_files` and cannot be considered for the summary.

## What Changes

- Add per-signal weights to the RRF fusion in `src/pgHybridSearch.py` (lexical > name-vector > content defaults), so a text match on a name column beats distant vector-only hits.
- Guarantee lexical-hit survival: a File with a direct lexical hit above the similarity threshold cannot be dropped from `top_files` solely because its rerank score is below the cutoff — it is kept and ranked via combined fusion+rerank score instead.
- Make the rerank cutoff configurable and pass rerank scores through so the acceptance decision can distinguish "reranked well" from "reranked weakly but lexically certain".
- **Extension (recall depth)**: make the per-signal recall depth configurable (`search.per_signal`, default 100) and apply rerank gating over a wider rerank window (`search.rerank_max_candidates`, default 60) *before* the `top_k` cut, so deep-but-relevant content matches (e.g. Gemeinderat minutes whose chunk mentions the searched platform keyword) survive into `top_files` even at the API default `top_k=10`. Motivated by live verification: minutes "Protokoll GR 24.02.2026 TOP 3" (beteiligungs-plattform budget decision, Feb 2026) is recalled only at content rank ~85/50-boundary and otherwise unreachable.
- All new settings (fusion weights, kill switches, rerank cutoff) live in a new `search` section of the instance config (`config/instance.yaml` + `src/instanceConfig.py` DEFAULTS), following the established env → config file → code defaults resolution.
- Expose the per-file signal provenance (including lexical similarity) in `top_files[].match` so the summarizer/debug can see why a file was included.
- **Extension B (listwise chat rerank)**: with the cross-encoder reranker dropped in favour of the SystemOne decision model (`RERANK_URL` unset), `search_stage` orders the fused-first candidates via **one** `SUMMARY_MDL` call — new `rerank-listwise` prompts in `config/instruction_prompts.json`, keyword-centred 600-char snippets (progressive suffix walk handles compounds), configurable `search.listwise_window` (default 50), model-relevant candidates floored at the rerank cutoff and ordered by model decay; not-relevant ones rejected (lexical override still applies); every failure degrades silently to fused order.
- **Extension A2 (weights rebalance)**: live tuning moved the defaults to `fusion_weights {lex: 1.5, nv: 0.8, vc: 1.2}` (name-vector ghost matches saturate the scale; content evidence is more discriminative).
- No API-contract breaking changes: `file_candidates`, `matched_entities`, and `top_files` keep their shapes; `match` gains an optional `lexical_sim` key.

## Capabilities

- **New Capabilities**: none
- **Modified Capabilities**:
  - `semantic-search` — recall fusion gains signal weights; rerank gating gains a lexical-hit override; provenance includes lexical similarity.

## Impact

- Code: `src/pgHybridSearch.py` (`rrf_fuse`, `_table_recall`, `hybrid_candidates`), `src/pgTimeline.py` (`search_stage` rerank gating for the chat and batch rerank modes).
- Tests: `src/tests/test_pgHybridSearch.py`, `src/tests/test_unit_pgTimeline.py`.
- Env: new optional `RISKI_SEARCH__*` overrides; kill-switchable behaviour so rollback is trivial.
- No database or import-pipeline changes; no API schema changes.
