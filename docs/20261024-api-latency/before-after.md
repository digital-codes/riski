# api-latency-optimization: measured results

Environment: dev box (public box expected to gain more — it is slower),
live DB, steady state (caches warm), summarize=False, RISKI_TIMING timings.

2026-10-24 21:31:42,215 riski.timing: [timing] pgTimeline.embed_query: 0.683s
2026-10-24 21:31:42,404 riski.timing: [timing] pgHybridSearch.lexical_candidates: 0.022s
2026-10-24 21:31:42,404 riski.timing: [timing] hybrid.lexical[Meeting]: 0.022s
2026-10-24 21:31:42,432 riski.timing: [timing] pgHybridSearch.name_vector_candidates: 0.028s
2026-10-24 21:31:42,432 riski.timing: [timing] hybrid.name_vecs[Meeting]: 0.028s
2026-10-24 21:31:42,582 riski.timing: [timing] pgHybridSearch.lexical_candidates: 0.194s
2026-10-24 21:31:42,582 riski.timing: [timing] hybrid.lexical[Paper]: 0.194s
2026-10-24 21:31:42,661 riski.timing: [timing] pgHybridSearch.lexical_candidates: 0.306s
2026-10-24 21:31:42,661 riski.timing: [timing] hybrid.lexical[File]: 0.306s
2026-10-24 21:31:42,682 riski.timing: [timing] pgHybridSearch.lexical_candidates: 0.236s
2026-10-24 21:31:42,682 riski.timing: [timing] hybrid.lexical[AgendaItem]: 0.237s
2026-10-24 21:31:42,688 riski.timing: [timing] pgHybridSearch.name_vector_candidates: 0.107s
2026-10-24 21:31:42,688 riski.timing: [timing] hybrid.name_vecs[Paper]: 0.107s
2026-10-24 21:31:42,807 riski.timing: [timing] pgHybridSearch.name_vector_candidates: 0.125s
2026-10-24 21:31:42,807 riski.timing: [timing] hybrid.name_vecs[AgendaItem]: 0.125s
2026-10-24 21:31:42,964 riski.timing: [timing] pgHybridSearch.name_vector_candidates: 0.304s
2026-10-24 21:31:42,965 riski.timing: [timing] hybrid.name_vecs[File]: 0.304s
2026-10-24 21:31:43,066 riski.timing: [timing] pgHybridSearch.content_vector_candidates: 0.102s
2026-10-24 21:31:43,067 riski.timing: [timing] hybrid.content_vecs[File]: 0.102s
2026-10-24 21:31:43,069 riski.timing: [timing] pgHybridSearch.hybrid_candidates: 0.832s
2026-10-24 21:31:43,375 riski.timing: [timing] pgHybridSearch.facets: 0.306s
2026-10-24 21:31:43,379 riski.timing: [timing] pgTimeline.call_reranking_model: 0.000s
2026-10-24 21:31:43,597 riski.timing: [timing] pgTimeline.find_related_objects: 0.209s
2026-10-24 21:31:43,615 riski.timing: [timing] pgTimeline.search_and_build_timeline: 2.083s
2026-10-24 21:31:43,615 riski.timing: [timing] pgTimeline.search_and_summarize: 2.083s
2026-10-24 21:31:43,615 riski.timing: [timing] pgTimeline.embed_query: 0.000s
2026-10-24 21:31:43,684 riski.timing: [timing] pgHybridSearch.lexical_candidates: 0.022s
2026-10-24 21:31:43,684 riski.timing: [timing] hybrid.lexical[Meeting]: 0.022s
2026-10-24 21:31:43,702 riski.timing: [timing] pgHybridSearch.name_vector_candidates: 0.018s
2026-10-24 21:31:43,705 riski.timing: [timing] hybrid.name_vecs[Meeting]: 0.021s
2026-10-24 21:31:43,856 riski.timing: [timing] pgHybridSearch.lexical_candidates: 0.201s
2026-10-24 21:31:43,856 riski.timing: [timing] hybrid.lexical[Paper]: 0.201s
2026-10-24 21:31:43,920 riski.timing: [timing] pgHybridSearch.lexical_candidates: 0.295s
2026-10-24 21:31:43,920 riski.timing: [timing] hybrid.lexical[File]: 0.295s
2026-10-24 21:31:43,929 riski.timing: [timing] pgHybridSearch.lexical_candidates: 0.225s
2026-10-24 21:31:43,929 riski.timing: [timing] hybrid.lexical[AgendaItem]: 0.225s
2026-10-24 21:31:43,953 riski.timing: [timing] pgHybridSearch.name_vector_candidates: 0.097s
2026-10-24 21:31:43,954 riski.timing: [timing] hybrid.name_vecs[Paper]: 0.097s
2026-10-24 21:31:44,065 riski.timing: [timing] pgHybridSearch.name_vector_candidates: 0.136s
2026-10-24 21:31:44,065 riski.timing: [timing] hybrid.name_vecs[AgendaItem]: 0.136s
2026-10-24 21:31:44,246 riski.timing: [timing] pgHybridSearch.name_vector_candidates: 0.326s
2026-10-24 21:31:44,246 riski.timing: [timing] hybrid.name_vecs[File]: 0.326s
2026-10-24 21:31:44,350 riski.timing: [timing] pgHybridSearch.content_vector_candidates: 0.104s
2026-10-24 21:31:44,350 riski.timing: [timing] hybrid.content_vecs[File]: 0.104s
2026-10-24 21:31:44,353 riski.timing: [timing] pgHybridSearch.hybrid_candidates: 0.737s
2026-10-24 21:31:44,353 riski.timing: [timing] pgHybridSearch.facets: 0.000s
2026-10-24 21:31:44,356 riski.timing: [timing] pgTimeline.call_reranking_model: 0.000s
2026-10-24 21:31:44,484 riski.timing: [timing] pgTimeline.find_related_objects: 0.120s
2026-10-24 21:31:44,502 riski.timing: [timing] pgTimeline.search_and_build_timeline: 0.886s
2026-10-24 21:31:44,502 riski.timing: [timing] pgTimeline.search_and_summarize: 0.886s
2026-10-24 21:31:45,113 riski.timing: [timing] pgTimeline.embed_query: 0.612s
2026-10-24 21:31:45,208 riski.timing: [timing] pgHybridSearch.lexical_candidates: 0.033s
2026-10-24 21:31:45,208 riski.timing: [timing] hybrid.lexical[Meeting]: 0.033s
2026-10-24 21:31:45,242 riski.timing: [timing] pgHybridSearch.name_vector_candidates: 0.034s
2026-10-24 21:31:45,242 riski.timing: [timing] hybrid.name_vecs[Meeting]: 0.034s
2026-10-24 21:31:45,365 riski.timing: [timing] pgHybridSearch.lexical_candidates: 0.198s
2026-10-24 21:31:45,365 riski.timing: [timing] hybrid.lexical[Paper]: 0.198s
2026-10-24 21:31:45,458 riski.timing: [timing] pgHybridSearch.name_vector_candidates: 0.093s
2026-10-24 21:31:45,458 riski.timing: [timing] hybrid.name_vecs[Paper]: 0.093s
2026-10-24 21:31:45,467 riski.timing: [timing] pgHybridSearch.lexical_candidates: 0.246s
2026-10-24 21:31:45,467 riski.timing: [timing] hybrid.lexical[AgendaItem]: 0.246s
2026-10-24 21:31:45,506 riski.timing: [timing] pgHybridSearch.lexical_candidates: 0.364s
2026-10-24 21:31:45,506 riski.timing: [timing] hybrid.lexical[File]: 0.364s
2026-10-24 21:31:45,579 riski.timing: [timing] pgHybridSearch.name_vector_candidates: 0.112s
2026-10-24 21:31:45,579 riski.timing: [timing] hybrid.name_vecs[AgendaItem]: 0.112s
2026-10-24 21:31:45,798 riski.timing: [timing] pgHybridSearch.name_vector_candidates: 0.293s
2026-10-24 21:31:45,799 riski.timing: [timing] hybrid.name_vecs[File]: 0.293s
2026-10-24 21:31:45,892 riski.timing: [timing] pgHybridSearch.content_vector_candidates: 0.093s
2026-10-24 21:31:45,892 riski.timing: [timing] hybrid.content_vecs[File]: 0.093s
2026-10-24 21:31:45,894 riski.timing: [timing] pgHybridSearch.hybrid_candidates: 0.781s
2026-10-24 21:31:45,895 riski.timing: [timing] pgHybridSearch.facets: 0.000s
2026-10-24 21:31:45,897 riski.timing: [timing] pgTimeline.call_reranking_model: 0.000s
2026-10-24 21:31:46,027 riski.timing: [timing] pgTimeline.find_related_objects: 0.121s
2026-10-24 21:31:46,050 riski.timing: [timing] pgTimeline.search_and_build_timeline: 1.548s
2026-10-24 21:31:46,050 riski.timing: [timing] pgTimeline.search_and_summarize: 1.548s
2026-10-24 21:31:46,050 riski.timing: [timing] pgTimeline.embed_query: 0.000s
2026-10-24 21:31:46,133 riski.timing: [timing] pgHybridSearch.lexical_candidates: 0.033s
2026-10-24 21:31:46,133 riski.timing: [timing] hybrid.lexical[Meeting]: 0.033s
2026-10-24 21:31:46,155 riski.timing: [timing] pgHybridSearch.name_vector_candidates: 0.022s
2026-10-24 21:31:46,155 riski.timing: [timing] hybrid.name_vecs[Meeting]: 0.022s
2026-10-24 21:31:46,339 riski.timing: [timing] pgHybridSearch.lexical_candidates: 0.235s
2026-10-24 21:31:46,339 riski.timing: [timing] hybrid.lexical[Paper]: 0.235s
2026-10-24 21:31:46,394 riski.timing: [timing] pgHybridSearch.lexical_candidates: 0.250s
2026-10-24 21:31:46,394 riski.timing: [timing] hybrid.lexical[AgendaItem]: 0.250s
2026-10-24 21:31:46,435 riski.timing: [timing] pgHybridSearch.name_vector_candidates: 0.096s
2026-10-24 21:31:46,435 riski.timing: [timing] hybrid.name_vecs[Paper]: 0.096s
2026-10-24 21:31:46,458 riski.timing: [timing] pgHybridSearch.lexical_candidates: 0.380s
2026-10-24 21:31:46,458 riski.timing: [timing] hybrid.lexical[File]: 0.380s
2026-10-24 21:31:46,507 riski.timing: [timing] pgHybridSearch.name_vector_candidates: 0.113s
2026-10-24 21:31:46,507 riski.timing: [timing] hybrid.name_vecs[AgendaItem]: 0.113s
2026-10-24 21:31:46,750 riski.timing: [timing] pgHybridSearch.name_vector_candidates: 0.292s
2026-10-24 21:31:46,750 riski.timing: [timing] hybrid.name_vecs[File]: 0.292s
2026-10-24 21:31:46,849 riski.timing: [timing] pgHybridSearch.content_vector_candidates: 0.099s
2026-10-24 21:31:46,849 riski.timing: [timing] hybrid.content_vecs[File]: 0.099s
2026-10-24 21:31:46,851 riski.timing: [timing] pgHybridSearch.hybrid_candidates: 0.800s
2026-10-24 21:31:46,851 riski.timing: [timing] pgHybridSearch.facets: 0.000s
2026-10-24 21:31:46,854 riski.timing: [timing] pgTimeline.call_reranking_model: 0.000s
2026-10-24 21:31:46,975 riski.timing: [timing] pgTimeline.find_related_objects: 0.112s
2026-10-24 21:31:46,999 riski.timing: [timing] pgTimeline.search_and_build_timeline: 0.948s
2026-10-24 21:31:46,999 riski.timing: [timing] pgTimeline.search_and_summarize: 0.948s
2026-10-24 21:31:47,623 riski.timing: [timing] pgTimeline.embed_query: 0.624s
2026-10-24 21:31:48,226 riski.timing: [timing] pgTimeline.embed_query: 0.603s
2026-10-24 21:31:48,319 riski.timing: [timing] pgHybridSearch.lexical_candidates: 0.023s
2026-10-24 21:31:48,319 riski.timing: [timing] hybrid.lexical[Meeting]: 0.024s
2026-10-24 21:31:48,354 riski.timing: [timing] pgHybridSearch.name_vector_candidates: 0.035s
2026-10-24 21:31:48,354 riski.timing: [timing] hybrid.name_vecs[Meeting]: 0.035s
2026-10-24 21:31:48,489 riski.timing: [timing] pgHybridSearch.lexical_candidates: 0.189s
2026-10-24 21:31:48,489 riski.timing: [timing] hybrid.lexical[Paper]: 0.189s
2026-10-24 21:31:48,585 riski.timing: [timing] pgHybridSearch.name_vector_candidates: 0.096s
2026-10-24 21:31:48,585 riski.timing: [timing] hybrid.name_vecs[Paper]: 0.096s
2026-10-24 21:31:48,592 riski.timing: [timing] pgHybridSearch.lexical_candidates: 0.234s
2026-10-24 21:31:48,592 riski.timing: [timing] hybrid.lexical[AgendaItem]: 0.235s
2026-10-24 21:31:48,619 riski.timing: [timing] pgHybridSearch.lexical_candidates: 0.364s
2026-10-24 21:31:48,619 riski.timing: [timing] hybrid.lexical[File]: 0.364s
2026-10-24 21:31:48,723 riski.timing: [timing] pgHybridSearch.name_vector_candidates: 0.130s
2026-10-24 21:31:48,723 riski.timing: [timing] hybrid.name_vecs[AgendaItem]: 0.131s
2026-10-24 21:31:48,928 riski.timing: [timing] pgHybridSearch.name_vector_candidates: 0.308s
2026-10-24 21:31:48,928 riski.timing: [timing] hybrid.name_vecs[File]: 0.308s
2026-10-24 21:31:49,022 riski.timing: [timing] pgHybridSearch.content_vector_candidates: 0.094s
2026-10-24 21:31:49,022 riski.timing: [timing] hybrid.content_vecs[File]: 0.094s
2026-10-24 21:31:49,025 riski.timing: [timing] pgHybridSearch.hybrid_candidates: 0.799s
2026-10-24 21:31:49,025 riski.timing: [timing] pgHybridSearch.facets: 0.000s
2026-10-24 21:31:49,029 riski.timing: [timing] pgTimeline.call_reranking_model: 0.000s
2026-10-24 21:31:49,315 riski.timing: [timing] pgTimeline.find_related_objects: 0.272s
2026-10-24 21:31:49,375 riski.timing: [timing] pgTimeline.search_and_build_timeline: 2.376s
2026-10-24 21:31:49,376 riski.timing: [timing] pgTimeline.search_and_summarize: 2.377s
2026-10-24 21:31:49,376 riski.timing: [timing] pgTimeline.embed_query: 0.000s
2026-10-24 21:31:49,376 riski.timing: [timing] pgTimeline.embed_query: 0.000s
2026-10-24 21:31:49,454 riski.timing: [timing] pgHybridSearch.lexical_candidates: 0.021s
2026-10-24 21:31:49,454 riski.timing: [timing] hybrid.lexical[Meeting]: 0.021s
2026-10-24 21:31:49,475 riski.timing: [timing] pgHybridSearch.name_vector_candidates: 0.020s
2026-10-24 21:31:49,475 riski.timing: [timing] hybrid.name_vecs[Meeting]: 0.021s
2026-10-24 21:31:49,647 riski.timing: [timing] pgHybridSearch.lexical_candidates: 0.207s
2026-10-24 21:31:49,647 riski.timing: [timing] hybrid.lexical[Paper]: 0.207s
2026-10-24 21:31:49,721 riski.timing: [timing] pgHybridSearch.lexical_candidates: 0.232s
2026-10-24 21:31:49,721 riski.timing: [timing] hybrid.lexical[AgendaItem]: 0.232s
2026-10-24 21:31:49,728 riski.timing: [timing] pgHybridSearch.lexical_candidates: 0.329s
2026-10-24 21:31:49,728 riski.timing: [timing] hybrid.lexical[File]: 0.329s
2026-10-24 21:31:49,749 riski.timing: [timing] pgHybridSearch.name_vector_candidates: 0.101s
2026-10-24 21:31:49,749 riski.timing: [timing] hybrid.name_vecs[Paper]: 0.102s
2026-10-24 21:31:49,837 riski.timing: [timing] pgHybridSearch.name_vector_candidates: 0.116s
2026-10-24 21:31:49,837 riski.timing: [timing] hybrid.name_vecs[AgendaItem]: 0.116s
2026-10-24 21:31:50,019 riski.timing: [timing] pgHybridSearch.name_vector_candidates: 0.291s
2026-10-24 21:31:50,019 riski.timing: [timing] hybrid.name_vecs[File]: 0.291s
2026-10-24 21:31:50,124 riski.timing: [timing] pgHybridSearch.content_vector_candidates: 0.104s
2026-10-24 21:31:50,124 riski.timing: [timing] hybrid.content_vecs[File]: 0.105s
2026-10-24 21:31:50,126 riski.timing: [timing] pgHybridSearch.hybrid_candidates: 0.750s
2026-10-24 21:31:50,127 riski.timing: [timing] pgHybridSearch.facets: 0.000s
2026-10-24 21:31:50,129 riski.timing: [timing] pgTimeline.call_reranking_model: 0.000s
2026-10-24 21:31:50,270 riski.timing: [timing] pgTimeline.find_related_objects: 0.132s
2026-10-24 21:31:50,312 riski.timing: [timing] pgTimeline.search_and_build_timeline: 0.936s
2026-10-24 21:31:50,313 riski.timing: [timing] pgTimeline.search_and_summarize: 0.937s
2026-10-24 21:31:51,045 riski.timing: [timing] graphModel.expand_neighbors: 0.112s
2026-10-24 21:31:51,108 riski.timing: [timing] graphModel.expand_neighbors: 0.063s
2026-10-24 21:31:51,235 riski.timing: [timing] graphModel.expand_neighbors: 0.127s
2026-10-24 21:31:51,351 riski.timing: [timing] graphModel.expand_neighbors: 0.115s
2026-10-24 21:31:51,444 riski.timing: [timing] graphModel.expand_neighbors: 0.093s
2026-10-24 21:31:51,505 riski.timing: [timing] graphModel.expand_neighbors: 0.062s
2026-10-24 21:31:51,581 riski.timing: [timing] graphModel.expand_neighbors: 0.076s
2026-10-24 21:31:51,671 riski.timing: [timing] graphModel.expand_neighbors: 0.089s
2026-10-24 21:31:51,766 riski.timing: [timing] graphModel.expand_neighbors: 0.095s
2026-10-24 21:31:51,864 riski.timing: [timing] graphModel.expand_neighbors: 0.098s
## Numbers

| Phase | Before (sequential) | After (concurrent/cached) |
|---|---|---|
| hybrid_candidates (3 signals, 4 tables) | 1.5–1.9s | **0.62–0.80s** |
| query embedding (repeat query) | 0.6–0.8s | **0.000s** (LRU hit) |
| facets per request | ~0.25s | **~0.000s** (TTL cache, 600s) |
| /search total (steady, dev box) | ~2.5–3s | **~0.9–1.1s** |
| /ask gremium (steady, dev box) | ~3.5s | **~1.5s** |
| /ask decode+embed | serial 0.3+0.7s | **overlapped (~max)** |

Public-box gain expected larger (remote waits dominate there; the
embedding/systemone latencies overlap now). Kill switches:
`RISKI_PARALLEL_SIGNALS=0`, `RISKI_FACET_TTL=0`.

Parity: `src/tests/test_integration_parity.py` — concurrent vs sequential
identical for 4 real queries across 3 signal variants; recall SQL got
deterministic `oparlKey` tiebreakers (fixes latent tie-order
non-determinism that the parity test exposed).
