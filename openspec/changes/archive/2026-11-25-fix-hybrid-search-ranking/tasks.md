# Tasks: fix-hybrid-search-ranking

## 1. Fusion weights

- [x] 1.1 Extend `rrf_fuse` (src/pgHybridSearch.py) with a `weights: Optional[Dict[str, float]]` parameter keyed by signal name (`lex`, `nv`, `vc`); plain RRF when absent
- [x] 1.2 Instance config: new `search` section in `src/instanceConfig.py` DEFAULTS and `config/instance.yaml` — `search.fusion_weights: {lex: 1.5, nv: 1.2, vc: 1.0}`, `search.weighted_fusion: true`, `search.rerank_cutoff: 0.8`, `search.lexical_rerank_override: true` (env override via `RISKI_SEARCH__*` comes free from the existing resolution order)
- [x] 1.3 Thread named signal labels through `_table_recall` so the non-empty signal lists map to the correct weights; pass them into `rrf_fuse`
- [x] 1.4 Unit tests: weighted RRF ordering (lexical-only File above vector-only Files); config resolution (defaults, env `RISKI_SEARCH__*` wins, kill switch parity with unweighted results)
- [x] 1.5 Documentation (code + docs folder, kept in sync): module docstring in `src/pgHybridSearch.py` (weighted-RRF formula, what a weight means, ordering semantics), `rrf_fuse` docstring with a worked number example, config comment block in `config/instance.yaml` + DEFAULTS explanation; plus `docs/search-weights.md` describing how the weights work (signals, formula, worked example, config entry points, kill switches, tuning guidance) — both locations carry a mutual sync note: the code docstring references `docs/search-weights.md` and the doc references the code as the source of truth, with the rule that any behavioural change to weights/scripts MUST update both in the same commit

## 2. Lexical similarity provenance

- [x] 2.1 In `_table_recall`, keep `lex_sim` dict from `lexical_candidates` triples and store `signals_hit["lexical_sim"]` in the provenance loop of `hybrid_candidates`
- [x] 2.2 Unit test: a lexically-recalled candidate exposes `lexical_sim` in `matched_entities[].signals` and `file_candidates[].signals`

## 3. Rerank gate override in search_stage

- [x] 3.1 Read `search.rerank_cutoff` and `search.lexical_rerank_override` from the instance config (added in 1.2) in `search_stage`
- [x] 3.2 In `search_stage` (src/pgTimeline.py), in the `RERANK_MODE == "chat"` branch: keep lexically-matching files rejected by the cutoff with merged score `fusion * min(rerank, cutoff)`
- [x] 3.3 Same override in the batch reranker branch; overriden entries fall below accepted files (monotonic formula), keep existing ordering otherwise
- [x] 3.4 Unit tests (test_unit_pgTimeline.py): lexical-only File with rerank 0.6 survives and ranks after accept files; override kill switch restores strict gate

## 5. Recall-depth extension (rerank before top_k cut)

- [x] 5.1 Instance config: `search.per_signal` (default 100) and `search.rerank_max_candidates` (default 60) in DEFAULTS + `config/instance.yaml`
- [x] 5.2 `hybrid_candidates`: resolve `per_signal` default from the config; cap `file_candidates` at `max(top_k, per_signal)` instead of `top_k`
- [x] 5.3 `search_stage` (both rerank modes): rerank the first `rerank_max_candidates` candidates by fused score, clamped fallback `fusion × cutoff` for candidates beyond the window; sort by kept score and cut to `top_k` after the gate
- [x] 5.4 Unit tests: clamped fallback ranks at/below accepted files; window config honoured; deep candidate survives the default top_k cut when reranked well
- [x] 5.5 Update `docs/search-weights.md` + module docstring (per-sync rule) and re-verify live: "Bürgerbeteiligungsplattform"/"beteiligungsportal" surface 677051 within the *default* top_k=10 API path — extension wiring verified; end-to-end lift requires a configured reranker (this env runs pass-through), window/depth knobs verified for their fallback semantics and 428 unit tests pass (3 pre-existing unrelated failures unchanged)

## 6. Fusion mode: score blending (no re-ranker path)

- [x] 6.1 Instance config: `search.fusion_mode` ("scores" | "rrf", default "scores") and calibration anchors in `search.fusion_score_calibration` (lex_floor, vec_near, vec_far) in DEFAULTS + `config/instance.yaml`
- [x] 6.2 `pgHybridSearch`: score-blend fusion — per-signal normalized scores (absolute calibration: lexical on trigram sim, vectors on cosine distance anchors) weighted by the same `fusion_weights`; deterministic tie-break on oparlKey; `rrf` mode preserved (kill switch)
- [x] 6.3 Unit tests: normalization bounds/clamping, score fusion ordering beats rank-only RRF for known cases, kill-switch parity, deterministic ordering
- [x] 6.4 Docs + docstring sync (`docs/search-weights.md`, module docstring)
- [x] 6.5 Live re-verification with the extended query set (beteiligungsportal / Bürgerbeteiligungsplattform / bürgerbeteiligung / öffentlichkeitsbeteiligung) — anchors calibrated live (lex_floor 0.35 / vec_near 0.20 / vec_far 0.85): direct lexical hits rank #1 for "beteiligungsportal"/"bürgerbeteiligung"/"öffentlichkeitsbeteiligung", Feb-2026 package in top 10 for all three; "Bürgerbeteiligungsplattform" still nv-only at default top_k (needs reranker/listwise-B); full unit suite 428 pass

## 4. Verification

- [x] 4.1 Add "beteiligungsplatform" and "bürgerbeteiligung" to the query set in `scripts/verify_content_unification.py` and run it against a live DB to confirm direct hits surface in `top_files` — both queries return direct lexical hits at rank 1 with `lexical_sim` provenance
- [x] 4.2 Run test suite (`pytest src/tests/test_pgHybridSearch.py src/tests/test_unit_pgTimeline.py`) — 62 passed; 3 pre-existing unrelated failures in kg_queries/oparlUpdate unchanged
- [x] 4.3 Confirm no API-contract change: search-api integration tests exist but are skipped in this environment (RW_USER/RW_PWD not set in .env); contract verified via live read-path run in 4.1 instead — `top_files[].match` keeps all previous keys, only additive `lexical_sim`

## 7. Fragment B: listwise chat rerank (SUMMARY_MDL)

- [x] 7.1 Prompts `rerank-listwise` / `rerank-listwise-user` in `config/instruction_prompts.json`
- [x] 7.2 `search_stage`: listwise window config (`search.listwise_rerank: true`, `search.listwise_window: 50`), `listwise_rerank()` (remote.chat, strict-JSON parse, failure→fused order), verdict merge into the gate with keyword-centred snippets (German-compound suffix walk)
- [x] 7.3 Unit tests: decay scores, failure/parse fallback, out-of-range indices, prompt-registry ids, keyword-centred snippets
- [x] 7.4 Docs + design sync; live re-verified: "Bürgerbeteiligungsplattform" → minutes 677051 at rank 6; package in top 10 for all variants; 437 unit tests pass
- [x] 7.5 Weights rebalance from live tuning: `nv 0.8 / vc 1.2` (name-vector ghosts saturate)

## Workflow follow-up

- After implementation, run `/opsx-verify` then archive with `/opsx-archive`.
