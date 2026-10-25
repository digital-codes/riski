# Design

## Context

See proposal.md for motivation. Relevant current state:

- `POST /ask` (`src/pgIntentRouter.ask`) and `POST /search` both funnel into `search_and_build_timeline` (`src/pgTimeline.py:885`), which returns intent + top_files + timeline + graph + geo availability in one response. Measured end-to-end: ~0.9–1.1 s (`/search`), ~1.5 s warm (`/ask`), up to ~2.4 s cold.
- The expensive part is embedding (0.6–0.8 s cold) + hybrid recall (0.6–0.8 s). The file list is derived right after recall + rerank (`pgTimeline.py:1046–1066`), before the related-objects traversal (0.12–0.27 s, `pgTimeline.py:1074`) and graph/timeline serialization.
- **Coupling detail**: `find_related_objects` output feeds both `build_graph` (`pgTimeline.py:1079`) and `build_timeline` (`pgTimeline.py:1093`). Line 1079 mutates the shared dict via `related_objects.pop("edges", [])` — a latent bug the split must handle.
- Sessions: `_sessions` dict in `apiServer.py:62` holds per-session results in memory; `/summarize` (POST, per-session, with `in_progress` guard) and `/geo/{session_id}` already follow the staged two-phase pattern. There is no SSE/websocket/polling anywhere.
- Frontend: `WorkPage.vue` clears all panes then awaits one `apiAsk` call and fills everything in `applyResult` (L238–257). `TimeLine.vue` renders both the file list and the timeline cards from a single `searchData` prop. `NetworkView` and `GeoMap` are already async-loaded components.
- The semantic timeline CLI also uses `search_and_build_timeline` (semantic-search spec), so the monolithic entry point must keep working.

## Goals / Non-Goals

**Goals:**
- File list visible right after recall (the only stage the file list depends on).
- Timeline visible before the graph; network view appears when the graph arrives.
- Per-pane loading states so the user sees continuous progress.
- Keep the existing staged endpoints (`/summarize`, `/geo`) and their behavior unchanged.

**Non-Goals:**
- No streaming (SSE/websockets), no polling loops — plain sequential requests, matching the existing two-phase pattern.
- No result caching beyond what exists (embedding LRU, facet TTL).
- No changes to recall quality, ranking, enrichment, or the summary/topic flow.
- No mobile-specific loading UX work beyond reusing the existing styles.

## Decisions

### 1. Client-driven staging with three sequential requests (not background tasks + polling)

After `POST /ask` (or `/search`) returns stage-1 results (intent, sessionId, top_files, matched_entities, facets, applied_filters), the client calls `POST /timeline {session_id}` and then `POST /graph {session_id}`.

- Alternatives: (a) server runs stages 2–3 in a background task and the client polls — rejected: introduces a polling mechanism that does not exist anywhere in the codebase, plus race handling, for a pipeline whose post-recall stages cost only ~0.3 s combined; (b) keep one endpoint and ship the file list early via SSE — rejected for the same reason.
- Cost: two extra localhost HTTP round trips (milliseconds) versus a much earlier time-to-content. Wall-clock total stays roughly the same.

### 2. Split `search_and_build_timeline` into composable stage functions

Refactor into: `recall_stage(...)` (embedding → hybrid candidates → rerank → top_files), `timeline_stage(session, stage1_result)` (find_related_objects → build_timeline → grouping), `graph_stage(session, stage1_result)` (build_graph → geo availability). `search_and_build_timeline` becomes a thin composition of the three so the semantic timeline CLI keeps its single-call behavior.

- Stage 2 stores `related_objects` (with the edges list **copied**, not popped — fixing the shared-mutation hazard) in the session payload; stage 3 reuses it instead of re-traversing.
- Geo availability moves into the graph stage (it reads graph nodes, `pgTimeline.py:1087–1090`) and is stored so `/geo/{session_id}` keeps working as before — the client already fetches geo after the graph is in.

### 3. New endpoints `POST /timeline` and `POST /graph`, keyed by sessionId

Payload contract mirrors `/summarize` (POST body with session id, in-memory `_sessions` lookup). Requesting the graph when stage 2 has not run yet computes stage 2 first (stages are idempotent per session, guarded like `/summarize`'s `in_progress` flag), so out-of-order calls are safe.

- Alternative: GET with path param like `/geo/{session_id}` — rejected: `/timeline` may trigger computation, which should not be a GET.

### 4. Frontend: per-stage state in `WorkPage.vue`, `TimeLine.vue` split by prop

- `api.js` gains `timeline(sessionId)` and `graph(sessionId)` wrappers alongside the existing pattern.
- `runSearch` clears panes and sets three independent loading flags; each response fills only its own slice of state (stage-1: intent/facets/top_files; then timeline; then graph). `applyResult` is dissolved into three smaller appliers. `NetworkView` (async component) only mounts once `graph` is set.
- `TimeLine.vue` stops deriving both cards from one `searchData` prop: the file list and timeline become independent props, each with its own loading flag, so the "Dateien" card can render while the "Zeitachse" card still shows its loading state. Splitting into two components is deliberately avoided — the cards share styling and the component stays small.
- Stale-response guard: a monotonically increasing search token; late responses from a superseded search are dropped (no AbortController machinery needed for a prototype).

### 5. Empty-result fallback ladder stays in stage 1

The intent router's fallback ladder (reruns with relaxed scope) operates on recall results only, so it is unaffected by the split; the ladder logic stays inside the stage-1 path of `/ask`.

## Risks / Trade-offs

- [Total latency slightly increases from two extra round trips] → Stages 2–3 cost ~0.3 s combined; round trips are localhost; perceived time-to-content improves by ~1 s (the whole point).
- [`related_objects.pop("edges")` mutation, currently masked by single-use] → Copy the edges list when storing stage-2 results; add a regression check that both timeline and graph stages produce complete results from one traversal.
- [`/summarize` may read pipeline fields computed in later stages] → Audit `/summarize`'s inputs (`apiServer.py:197–261`); it works from the stored session result, so it must only run after stage 1 (unchanged ordering — the client already calls it after the search response) and must not depend on graph-only fields.
- [In-memory `_sessions` means a server restart or multi-worker deployment breaks follow-up calls] → Pre-existing constraint for `/summarize` and `/geo`; unchanged. Single-process deployment (supervisor conf) assumed.
- [Spec/API contract break for external clients] → Accepted per proposal: the bundled frontend is the only consumer and is updated in the same change; `API.md` documents the new contract.

## Migration Plan

1. Land backend split + new endpoints with the monolith preserved as composition (CLI unaffected).
2. Update frontend to the staged flow in the same change (both deploy together; single-repo prototype).
3. Update `API.md`.
4. Rollback: revert the commit; no schema or persistent-state changes involved.

## Open Questions

None.
