# Design

## Context

See proposal.md — Why. Relevant current-state constraints:

- `/ask` routes via a SystemOne decision-model call against the intent
  descriptions/choices in `config/intents.yaml`; slot resolution
  (`pgIntentRouter.py`) supports two source types: `db` (table/column +
  optional `where_regex`) and `hard`. `resolve_gremium` shows the established
  pattern for multi-match notes and fall-through.
- The hybrid recall path (`pgHybridSearch.hybrid_candidates`) never queries
  the geo association tables; they are presentation-only today (`pgGeo.py`,
  `/geo/{session_id}`).
- `pg_trgm` is already installed (`pgGen.ensure_project_schema`).
- Measured vocabulary size: 1,915 `Street` + 27 `District` names. Measured
  `word_similarity` full-sentence match ("was passiert am freidrichsplatz" →
  "Friedrichsplatz", 0.625): 26 ms cold, ~2 ms warm, sequential scan, no
  index.

## Goals / Non-Goals

**Goals:**
- Typo-tolerant resolution of place references in free-text queries.
- Deterministic recall of all geo-linked documents for a resolved location.
- Reuse of the existing rerank → top_files → summarize → map pipeline and
  response contract; purely additive routing.

**Non-Goals:**
- No POI table or unified location view in this change (vocabulary loader
  accepts extra sources; the POI table is added later as data).
- No changes to hybrid recall signals, rerank thresholds, or map scope rules.
- No geographic/coordinate reasoning (no "near", radius or geometry queries).
- No frontend changes (the map and doc list render from existing contracts).

## Decisions

### D1: `word_similarity(name, query)` over the whole query, not token matching or suffix gating

`word_similarity(a, b)` scores `a` against the best substring of `b`, so a
location name embedded in a sentence matches without tokenization, n-gram
extraction or suffix detection — one SQL expression handles typos ("ei"/"ie"),
multi-word names ("Friedrichstaler Allee") and surrounding context uniformly.

Alternatives considered:
- *Suffix pre-check* ("straße", "platz", "weg"…): misses districts and future
  POIs, and false-positives on topic queries ("radweg am terrainkurweg",
  "rückbau herrenalber strasse"). Kept only as a threshold booster.
- *`%` operator with GIN index*: index-oriented, but requires candidate-token
  extraction app-side and doesn't cover "name inside sentence" matching.
- *Name vectors (`*_name_vecs`)*: semantic but opaque and non-deterministic;
  trigram is exact, explainable and free at this vocabulary size.
- *Python-side matching on a cached vocabulary (rapidfuzz)*: equally viable
  (~2k names); kept as an optimization option behind the same interface, but
  the SQL query is chosen because it needs no cache invalidation story.

### D2: Resolver reads a unified vocabulary, assembled in code

One SELECT over `Street` + one over `District` (later: POI), each scored with
the same expression, results merged and sorted. A dedicated view/table and
GIN trigram index are deferred: at 2k rows a sequential scan is faster than
index planning overhead, and a view would complicate the later POI addition
(data-only change stays possible). If the vocabulary grows an order of
magnitude, add `USING gin (name gin_trgm_ops)` on a materialized location
table — a contained follow-up.

Threshold policy: base acceptance threshold (0.5 similarity) lowered when the
query contains a location suffix (e.g. −0.1) and raised when the query is
short and topic-like. Exact tuned values live in `config/intents.yaml`
alongside the suffix list, so calibration needs no code change.

### D3: New slot source type `trigram` in the intent router

Slot sources gain a `trigram` type: `{trigram: {tables: [...], column: name,
threshold: ...}}`. Resolution returns top-k rows with scores into the slot;
the response reports them like resolved gremiums (names + note on ambiguity).
This reuses the existing per-request vocabulary loading and normalization
plumbing, and the decoder harness config stays the single source of truth.

Ambiguity rule (mirrors `resolve_gremium`): accept the best match; when
runners-up score within a small delta of the best, keep them as alternates in
the note. "Friedrichsplatz" (0.722) vs "Friedrichstraße" — the delta keeps
this predictable and testable.

### D4: Retrieval via association tables, rerank downstream — not via candidate boosting

`location_scoped_search` resolves the location, then loads candidate sids
from the four association tables with the geo-gating filter
(`gate_status != 'boilerplate'`, same rule as `pgGeo._gate_filter`), and
feeds files into the existing `search_stage` post-recall machinery (rerank
with best chunk, top_k cap, summarizer). Agenda items linked to the location
contribute their files via the existing OParl traversal in the timeline stage
— same as today's flow.

Alternatives considered:
- *Boosting geo-linked files inside `hybrid_candidates`*: couples the recall
  engine to geo data, changes ranking for every query, contradicts the
  analysis finding that geo is presentation-only today.
- *Fake query embedding / synthetic filters*: fragile, hides the actual
  retrieval path from the response.

Reranking still gates hard (≥ 0.8), so deterministic candidate recall does
not mean low-precision output; if location answers prove over-filtered, the
follow-up lever is a per-intent rerank threshold, not a recall change.

### D5: Intent placement and fallback

`ask_location` sits alongside `ask_gremium_recent`/`ask_decision_date` in
`config/intents.yaml`; description written for the decision model ("Frage, die
sich primär auf einen Ort bezieht …"). Behavior on failure: unresolvable
location → unscoped `search_topic` answer + note (same degradation style as
an unreachable gremium). Decision-model outage → existing global fallback
unchanged; the trigram resolver is not consulted on that path.

### D6: Truncation for broad locations — newest-first plus hit note, not a clarification dialog

Plain location queries ("friedrichsplatz") can link hundreds of files
(Friedrichsplatz: 132 visible) with no relevance signal yet. Prototype
choice: cap at top_k, ordered by the **attached meeting's start_date**
(newest first; a file linked to a recent meeting outranks one only carried
by its publication date — "was passiert am X" means recent activity).
Files without a meeting link fall back to their own date. The response
states the total hit count and that only the newest are shown; narrowing
is possible immediately via the existing `/summarize` exclude/refine
mechanics and the rendered note.

Alternatives considered:
- *Clarifying-question loop* (present hit count, ask for period/topic,
  re-search): better precision, but needs new session state, a follow-up
  round-trip through the decoder and frontend dialog work — deferred to a
  follow-up change; this design keeps the door open (total count + note are
  exactly the data such a dialog needs).

## Risks / Trade-offs

- [Topic queries mentioning a street get captured by the new intent, e.g.
  "radweg am terrainkurweg"] → Decision-model disambiguation via intent
  descriptions/choices; `location_scoped_search` still answers usefully
  (documents linked to that street), and the summarizer refuses irrelevant
  files. Tunable via choices/negatives in intents.yaml.
- [Trigram ambiguity between similar street names] → top-k + delta rule +
  explicit note; acceptance threshold calibrated against the Friedrichsplatz/
  Friedrichstraße pair as the regression case.
- [Large geo-linked candidate sets (135 files) stress the reranker cost
  (one LLM call per candidate)] → Reuse `top_k` cap before rerank (fused
  ordering from association sids is stable); candidate volume stays bounded
  by the existing cap, not by link count.
- [Vocabulary drift when streets/POIs change] → Per-request loading (existing
  intent-router convention); no cache invalidation needed.

## Migration Plan

Purely additive; no schema or data migration. Deploy order: config + resolver
+ handler land together; `/ask` responses gain optional fields (resolved
location, note). Rollback = revert; no state to clean up. Feature can be
soft-disabled by removing the intent from `config/intents.yaml` (queries fall
back to `search_topic`).

## Open Questions

- Whether location-scoped answers should relax the 0.8 rerank cutoff
  (per-intent threshold) — deferred until real queries show over-filtering.
