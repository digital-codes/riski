# Design

## Context

The search stack (`pgHybridSearch` → `pgTimeline.search_and_summarize`) already
supports structured filters (facets: `paperType`, `year`, `result`, `role`,
`authoritative`, `tag`, `district`, `organization` — src/pgHybridSearch.py:121)
and the API already holds in-memory sessions (src/apiServer.py:62). What is
missing is the layer that decides *which* filters and answer mode a German
natural-language question implies. The SystemOne decision-model protocol
(question payload with `choice`/`noul`/`score` modes) is proven by the harness
`utils/test_intent_decoder_extended.py` against local ollama models (0.8b–2b,
4k context) and the hosted endpoint (`src/private.py`: `SYSONE_URL`,
`SYSONE_MDL` = "metis"). The harness reads `config/intents.yaml`, which does
not exist yet.

Observed data facts (checked in the live DB): 99 organizations, 92 with NULL
`classification`; councils with meetings ≈ 30 (Gemeinderat, 7 Ortschaftsräte,
~18 Ausschüsse/Beiräte/Betriebsausschüsse); factions live as `Person` rows
(" CDU-Fraktion", 5 rows, leading whitespace); `Meeting.start_date` includes
future forecast meetings (OR-Neureut's latest 3 are in the future as of
2026-10-24); `AgendaItem.result` is rich free text; `Consultation.authoritative`
is 8348 true / 6840 NULL.

## Goals / Non-Goals

**Goals:**
- One config file (`config/intents.yaml`) serving both the decoder test harness
  and the production router.
- Intent + slots from a *single* SystemOne round-trip per `/ask` request.
- Vocabularies from the DB at request time; no cache, no staleness.
- Useful behaviour on every input: fallback intent, filter-relax retry, honest
  empty response, graceful degradation when the decision model is down.
- The web app uses `/ask` for the search box and makes the routing decision
  visible (intent, scope chips, fallback notes, honest empty response).

**Non-Goals:**
- Conversation/follow-up handling (session context recorded but not consulted).
- "Preliminary" status tags, vote roll-call, geo intent, "nächste Sitzung".
- Retraining/fine-tuning models; prompt engineering beyond criteria text.
- Frontend redesign — the existing panes (graph, summary, timeline, map)
  stay as they are; only the query flow and an intent/scope banner change.

## Decisions

### D1: Decoder mode — `noul` per intent with thresholds, choice as harness baseline
The harness measures all three modes; production uses **`noul`** by default
(one yes/no question per intent, per-intent score). Rationale: `choice`/`score`
always answer *something* (no confidence signal → over-triggering), while
`noul` gives a per-intent score, parallelises, and supports "none ≥ τ →
fallback". `noul` also generalises to slot questions ("wird ein Gremium
genannt?"). Mode is selectable in the config so harness results can override.
Alternative rejected: `score` with legend — index-mapping forces the tiny model
to count; brittle.

### D2: Intent + slots in one payload
SystemOne accepts multiple questions per call. `/ask` sends intent questions
*and* slot questions (gremium, doc-type) in a single payload: `state` =
lowercased query. Budget checked: ~8–10 noul intent questions (~500 tokens) +
~30 council criteria (~500) + 5 faction criteria (~80) + query ≈ **~1.2k
tokens**, safely under the 4k local-model limit. Sequential (intent first,
then slot questions for the winner) doubles latency for no accuracy gain at
this intent count; re-evaluate when intents exceed ~15.

**Apply-phase discovery:** SystemOne score questions accept **at most 10
criteria levels** (422 otherwise), so the ~31-criteria gremium slot uses the
`choice` question type instead (verified working with per-criterion
probabilities against the hosted endpoint). Harness slot mode mirrors this.

### D3: Vocabulary resolution at request time, no cache
Slot vocab queries are trivial `SELECT`s over ≤100 rows. Loading per request
removes cache invalidation after every `syncIncremental` run. If profiling
shows the payload string-build dominates, add a TTL cache later — config
grammar does not change.
Party vocabulary comes from `Person.name` rows matching `Fraktion$|Gruppe$`
(factions are modelled as Persons in this OParl feed), merged with config
`hard:` values. Council vocabulary from `Organization` name+shortname, filtered
by classification (after the backfill) with a name-regex fallback
(`ortschaftsrat|gemeinderat|ausschuss|beirat`) so the router works even before
the backfill pass has run.

### D4: "Letzter <Gremium>" = latest held meeting via join, date-guarded
Resolve org → `Meeting` via `Meeting__organization__Organization`, pick latest
`start_date <= now()`. German "der letzte Ortschaftsrat" refers to the most
recent *session*, not the max row; and future forecast meetings must never
satisfy it. The mirror intent ("nächste Sitzung") is deliberately deferred;
the resolver accepts a direction parameter so adding it later is a config
entry, not new code.

### D4a: One-off sub-orgs merge into their parent at resolution time
The Karlsruhe-specific org "Gemeinderat - Beratungen zum DHH" (GR-DHH, 2
meetings) is a one-off sub-body of the Gemeinderat. A hard DB merge (retire
row, re-point `Meeting__organization__Organization`) would be regressed by
every additive `pgGen` re-import. Instead, the config defines an org **group**
per resolvable gremium: `gemeinderat → [Gemeinderat, Gemeinderat - Beratungen
zum DHH]`; the resolver unions the group's meetings and picks the latest held
one. Explicit questions about the sub-org still find its meetings through the
union. Alternative rejected: DB-level merge (undone by re-crawl).

### D5: Router lives in the API layer, search stays a primitive
New `src/pgIntentRouter.py`: `decode(query) → {intent, scores, slots}`,
`resolve(intent, slots) → {filters, scope, answer_mode}`, called by `/ask`,
which then delegates to the existing `search_and_summarize`. The empty-result
ladder (retry unscoped → honest empty) also lives here. Rationale: the search
pipeline remains filter-agnostic and `/search` semantics are untouched;
alternative (decoding inside `search_and_summarize`) would couple enrichment
layers to intent semantics.

### D6: Decision-type scope = document-type filter + future-meeting date guard
"Beschluss"-like filtering uses the existing `tag` facet with scheme
`document-type` (values derived by `pgCategorise`); the precise value list is
read from the DB (`SELECT DISTINCT` on document-type tags) at vocab-load time
rather than hardcoded. Exclusion of not-yet-held meetings is enforced by a
resolver-side check (meeting date ≤ now) rather than a new facet, because
`year`-range facet cannot express "held".

### D7: Org classification backfill follows the pgCategorise pattern
New pass `src/pgAddOrgClassification.py`: name-regex → classification value
(`ORTSRAT`, `AUSSCHUSS`, `BEIRAT`, `EIGENBETRIEB`, `AMT`, `FRAKTION`,
`SONSTIGES`), writes only NULL cells, idempotent, `--dry-run` support, plus
whitespace trim of names. Config values and regexes are in the script like
`_NAME_PATTERNS` in `pgCategorise.py`. Factions-as-Person rows are *not*
promoted to Organization — the config references Person, keeping OParl
re-imports clean. One-off sub-orgs (GR-DHH) get their parent's classification
pattern (sub-body marker) but are merged into the parent only at resolution
time (D4a), never in the database.

### D8: `/ask` response extends the search contract additively
Response = existing search result fields + `{intent, intent_scores, slots,
applied_filters, fallback_notes}`. `sessionId` accepted, stored as today.
Frontend can ignore the new fields; no contract break. `/search` is unchanged.

### D9: Frontend consumes `/ask` with additive rendering
The search box calls `/ask` (new `ask()` in `app/src/api.js`) instead of
`/search`; the summary/expand/geo flow is untouched (same sessionId
contract). A small `RouteInfo` component renders the routing outcome under
the query header: intent label (German, from a local map), scope chips
(gremium orgs + "Sitzung am <date>", document-type values), and
`fallback_notes` as a muted hint line. An `empty_response` shows an explicit
"nichts gefunden" block with the tried scope instead of silently empty
panes. Rationale for a dedicated component: App.vue stays the flow
orchestrator; intent display is cohesive and independently testable.
Alternative rejected: scattering the fields across existing panes.

### D10: Gremium answers are meeting-centric, not search-centric
The user validated the chips but rejected the generic search result behind
them: a gremium-scoped answer should *be the session*. The
`ask_gremium_recent` handler therefore skips `search_and_summarize`
entirely and builds a forward traversal from the resolved meeting using the
existing ADJACENCY machinery (`expand_neighbors`, merged depth 1→4:
Meeting → agenda items/Tagesordnung/aux files → agenda-item files and
consultations → papers → their files, bounded by `limit_per_relation`) —
the same graph vocabulary the timeline/search traversal logs, so
NetworkView, DetailPanel and `/expand` keep working unchanged. The answer
carries `topics` (agenda items with number/result and their files) and
`answer_mode: list_topics`; the frontend swaps the SummaryCard for a
TopicList when `answer_mode == "list_topics"`, file/topic clicks feed the
existing selection flow (`{kind:'node'}` → DetailPanel: downloadurl for
files, `webUrl` termin-page link for the meeting, already generated by
`graphModel`). No map: the response omits `geo_available`. Alternative
rejected: filtering hybrid search to the meeting — keeps the answer
scattered and unfocused.

## Risks / Trade-offs

- [Tiny-model accuracy on ~30-criteria slot lists] → Harness measures slot
  extraction as a separate accuracy number before freeze; if 0.8b fails,
  fall back to `pg_trgm` similarity matching of the raw query against
  `Organization.name` (lexical, no model) for the gremium slot.
- [Over-triggering on the fallback boundary ("was wurde … beschlossen" vs
  "wann wurde … beschlossen" minimal pairs)] → Minimal pairs are encoded as
  `choices` for both intents; thresholds tuned from harness score
  distributions, not guessed.
- [SystemOne endpoint adds a hard dependency to `/ask`] → Degrades to plain
  search with `intent: search_topic` on any exception/timeout; `/search`
  unaffected.
- [Classification backfill mislabels orgs] → Only fills NULLs (provenance
  preserved), `--dry-run` + report first; regex rules are conservative.
- [Vocabulary growth breaks 4k budget] → Payload-size asserted in harness;
  budget table in D2; at >15 intents switch to sequential slot questions.
- [Harness `results/` dir missing] → Create on write (`mkdir -p` semantics).

## Migration Plan

1. Ship config + harness alignment + classification backfill (no runtime
   change; `/ask` not yet mounted).
2. Run harness, pick mode/model from results.
3. Mount `/ask` behind the additive response contract; frontend unaffected.
4. Rollback: unmount `/ask`; nothing else touches existing behaviour.

## Open Questions

- Exact threshold τ for `noul` fallback (from harness score distributions).
- Exact document-type tag values for "Beschluss" — read from DB during
  implementation; expected set: Beschluss, Beschlussvorlage, Beschlussempfehlung
  (or German equivalents present in `Paper.papertype`).
