# Proposal: Intent Router

## Why

User questions to RISKI are currently answered by a single path: hybrid search
plus a generic summary. German council questions, however, differ in *what kind
of answer they want* ("erzähl was zur Theatersanierung" vs. "wann wurde der
Rückbau der Herrenalber Straße beschlossen" vs. "was wurde im letzten
Ortschaftsrat beschlossen"). Without a routing layer, questions that should be
scoped (e.g. only decision-type documents, only a specific gremium's most
recent meeting) are answered by unscoped search, producing vague or misleading
results. A fast, small "system-1" decision model (SystemOne protocol, 0.8b–2b
models) can classify each user question and route it to the right handler
cheaply — the harness `utils/test_intent_decoder_extended.py` already proves
the protocol works against local ollama models.

## What Changes

- New `POST /ask` endpoint in the API layer that decodes the user question via
  the SystemOne decision model and routes to a handler (v1: scoped search or
  fallback to existing `search_and_summarize`); returns the decoded intent and
  applied filters alongside the normal result contract so clients can show
  what was routed.
- New intent configuration file `config/intents.yaml` defining intents
  (name, description, example utterances) plus routing metadata (handler,
  answer mode, structured filters) and slot vocabularies.
- Slot/criterion vocabularies are loaded **from the database at request time**
  (councils/Ortschaftsräte from `Organization`, factions from `Person`) merged
  with hard-coded values in the config; vocabulary is normalised
  (lowercase, trim) and queries are lowercased before the model call.
- Database extension pass that backfills `Organization.classification`
  (currently NULL for 92/99 orgs) via name-regex rules (Ortschaftsrat,
  Ausschuss, Beirat, Eigenbetrieb, Amt, Fraktion, ...) so intent vocabulary
  queries can filter by org type. Data-quality fixes on load: trim leading
  whitespace in names (" CDU-Fraktion").
- Meeting resolution for gremium-scoped questions: "letzter Ortschaftsrat X"
  resolves to the most recent **held** meeting of Organization X
  (`start_date <= now()`), never the next scheduled one; future meetings are
  excluded from decision-type scopes.
- Empty-result fallback ladder: when a routed search returns nothing, retry
  without the intent's filters and present both outcomes, plus an honest
  "nothing found" response that names what was tried.
- Session plumbing: `/ask` accepts an optional `sessionId` (ignored in v1,
  recorded for a future follow-up/conversation intent class).
- Test harness alignment: `utils/test_intent_decoder_extended.py` reads
  endpoint/model from `src/private.py` (`SYSONE_URL`, `SYSONE_MDL`) instead of
  hardcoding localhost, and negative (no-intent) test cases are supported.
- **Frontend wiring (app/)**: the search box calls `/ask` instead of `/search`,
  renders the decoded intent and the derived scope (gremium, meeting date,
  document-type) as filter chips, surfaces fallback notes as hints, and shows
  the honest empty response with the tried scope. Intent metadata is ignored
  gracefully by older clients — the result contract stays additive.

Out of scope (later changes): "Preliminary" status tags for documents
published ahead of future meetings, vote roll-call lookup, geo-intent
(`ask_location`), conversation/follow-up handling, "nächste Sitzung" intent.## Capabilities

### New Capabilities

- `intent-routing`: Decision-model-based intent decoding and question routing —
  config grammar with DB-backed vocabularies, SystemOne decoder integration,
  gremium meeting resolution, structured-filter derivation, empty-result
  fallback ladder, and the `POST /ask` endpoint contract.

### Modified Capabilities

- `data-enrichment`: New requirement for the organization classification
  backfill pass (name-regex → `Organization.classification`), following the
  existing pgCategorise pattern.

## Impact

- **New code**: `src/pgIntentRouter.py` (decoder + router + meeting resolver),
  `config/intents.yaml`, likely `src/pgAddOrgClassification.py` (backfill).
- **Modified**: `src/apiServer.py` (`/ask` endpoint, session plumbing),
  `src/private.py` (SYSONE_* already present — consumed, not changed),
  `utils/test_intent_decoder_extended.py` (config/endpoint alignment),
  `app/src/api.js` + `app/src/App.vue` (+ a small route-info component) for
  the ask-driven UI.
- **Database**: `Organization.classification` values written by the new
  enrichment pass (additive, idempotent, re-runnable like other enrichers).
- **Dependencies**: `httpx` + `yaml` + `rich` (already used by the test
  harness) added to runtime path of the router; SystemOne endpoint
  (`SYSONE_URL`/`SYSONE_MDL`/`SYSONE_KEY`) becomes a required runtime service
  for `/ask` (degrades to plain search when unreachable).
- **Unaffected**: search pipeline (`pgHybridSearch`, `pgTimeline`,
  `search_and_summarize`), existing `/search` contract, frontend.
