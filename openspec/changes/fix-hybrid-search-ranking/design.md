# Design: fix-hybrid-search-ranking

## Context

`hybrid_candidates` (src/pgHybridSearch.py:724) fuses per-table signal lists — lexical trigram, name vectors, content vectors — with `rrf_fuse` (src/pgHybridSearch.py:351), where every signal contributes `1/(60+rank)`. Signal type is irrelevant in fusion: a direct name hit ranks by position only. `search_stage` (src/pgTimeline.py:1260) then reranks file candidates and drops anything scoring < 0.8 (src/pgTimeline.py:1400, 1434). A File whose name contains "beteiligungsplatform" but whose chunk/head text the reranker scores 0.6 gets dropped, so it never reaches `top_files` or the summarizer. Additionally, lexical similarity is discarded at recall: only membership is recorded in `signals`.

## Goals / Non-Goals

**Goals**
- Weighted fusion so lexical hits outrank weak vector hits.
- Lexical-only File hits survive the rerank gate and appear in `top_files` (and hence the summary input).
- Lexical similarity visible in per-file provenance.
- Kill switch + rollback path; no API shape changes.

**Non-Goals**
- No changes to embedding generation, chunking, or the import pipeline.
- No new UI; `match` gains an optional key only.
- No per-table weight tuning or ML-based fusion (e.g. LambdaMART); fixed scalar weights suffice for now.

## Decisions

1. **Signal weights inside `rrf_fuse` via optional weights argument, configured via instance config**
   `rrf_fuse(ranked_lists, k=RRF_K, weights=None)`; `hybrid_candidates` passes the weights for the non-empty lists. Order of non-empty lists must map to named weights — `_table_recall` builds `(lex, nv, vc)` explicitly, so a `{signal: weight}` dict keyed by name avoids index bugs. All weight settings live in a new `search` section of the instance config (src/instanceConfig.py `DEFAULTS["search"]` + `config/instance.yaml`), following the existing resolution order `RISKI_SEARCH__<KEY>` env → config file → code defaults:
   - `search.fusion_weights: {lex: 1.5, nv: 1.2, vc: 1.0}`
   - `search.weighted_fusion: true` — kill switch; false falls back to plain RRF (all weights 1.0)
   
   This reuses the deployment-instance machinery (change: instance-agnostic-config) instead of ad-hoc `os.getenv` parsing in `pgHybridSearch.py`, so second instances can tune weights per deployment without code edits and ops can override live via `RISKI_SEARCH__FUSION_WEIGHTS__LEX`.
   *Alternative*: separate re-score stage after fusion — rejected as redundant; RRF with weights is equivalent and keeps one code path.

2. **Lexical-gate override for Files, not global score change**
   In `search_stage`, after the rerank loop, track Files whose provenance in `hybrid_match_info[oparlKey]` contains `lexical` (with `lexical_sim` above threshold — always true if present). Files rejected by the rerank cutoff but lexically matching get a merged score `(fusion_score * rerank_score) <= (fusion_score * cutoff)` still below accepted files, preserving accepted-file ordering. Concretely: keep `(oparlKey, fusion_score * min(rerank_score, CUTOFF))` for lexical hits, keep `(oparlKey, fusion_score * rerank_score)` for accepted ones. Gate + cutoff are instance-config options in the same `search` section: `search.rerank_cutoff: 0.8` (env `RISKI_SEARCH__RERANK_CUTOFF`) and `search.lexical_rerank_override: true` (env `RISKI_SEARCH__LEXICAL_RERANK_OVERRIDE`). Applied in both `RERANK_MODE == "chat"` and batch modes.
   *Alternative*: bypass the gate whenever lexical hit exists and rerank < cutoff but > 0 — equivalent outcome; the multiplied score is simpler and monotonic.

3. **Propagate lexical similarity through the candidate dicts**
   `lexical_candidates` already returns `(oparlKey, name, sim)`; `_table_recall` currently throws `sim` away (src/pgHybridSearch.py:697). Keep `lex_sim: Dict[str, float]` alongside `lex` and store `signals_hit["lexical_sim"] = round(sim, 4)`. This flows into `matched_entities` and `file_signals` → `hybrid_match_info` → `top_files[].match` for free.

4. **Rerank-order preservation for the override set**
   The final sort uses `fusion * effective_rerank` backwards; existing accepted files keep their relative order since the formula is unchanged for them.

## Decisions on documentation (code + docs folder, sync rule)

The semantics of the weights are documented in two places that must stay in sync:

- `pgHybridSearch` module docstring: weighted-RRF formula — `score(id) = Σ_signals w_s / (k + rank_s)` — plus what "lexical weight 1.5" means operationally (a top-1 lexical hit is worth a top-N vector hit within the same k window), that weights only re-weight contributing ranks (missing signals contribute nothing), and where the values come from.
- `rrf_fuse` docstring: worked example with numbers.
- Instance config: every `search.*` entry commented in `config/instance.yaml` and mirrored in `DEFAULTS` (existing convention).
- `docs/search-weights.md` (new): the user-facing explanation — signals, formula, worked example, config entry points, kill switches, tuning guidance.

**Sync rule:** the code docstring and `docs/search-weights.md` each carry a mutual reference stating the other location must be updated whenever the weight behaviour changes; the task list makes updating both mandatory in the same commit. The doc marks the code as the source of truth, the docstring links to the doc for the long-form explanation.

## Risks / Trade-offs

- [Weights make a typo'd lexical hit outrank a perfect semantic hit] → 1.5 is modest; RRF rank term still dominates extreme cases; `search.weighted_fusion: false` reverts instantly.
- [Lexical override re-adds noise the reranker intentionally filtered] → override only applies when `lexical_sim` ≥ threshold (already guaranteed by `lexical_candidates`) and ranks below accepted files.
- [Overriding in chat mode changes previously "clean" behaviour] → override is instance-config default-on but kill-switchable via `search.lexical_rerank_override: false`; integration test asserts parity with the switch off.

## Migration Plan

1. Deploy code: new env vars default to weighted fusion + lexical override ON.
2. Verify with the existing verification script `scripts/verify_content_unification.py` query set ("beteiligungsplatform", "bürgerbeteiligung" added to it).
3. Rollback: `search.weighted_fusion: false` (or `RISKI_SEARCH__WEIGHTED_FUSION=false`) restores plain RRF; `search.lexical_rerank_override: false` restores the strict rerank gate. Each behaviour reverts independently per instance.

## Open Questions

None.
