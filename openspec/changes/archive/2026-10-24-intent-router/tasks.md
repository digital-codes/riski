# Tasks

## 1. Decoder test harness alignment

- [x] 1.1 Make `utils/test_intent_decoder_extended.py` read endpoint/model from `src/private.py` (`SYSONE_URL`, `SYSONE_MDL`) with the localhost values as CLI-overridable defaults; verify: `python utils/test_intent_decoder_extended.py --help` and a run against the configured endpoint produces a results file.
- [x] 1.2 Create `results/` dir on write in the harness; verify: a run succeeds in a clean checkout (no results/ present).
- [x] 1.3 Support negative test cases: an intent may carry `negative: true` utterances (expected answer = fallback intent `search_topic`); verify: harness reports such cases as correct when the fallback intent is predicted.
- [x] 1.4 Add slot-extraction test mode: harness also measures, per model/mode, gremium-slot accuracy over the config's gremium utterances (criteria list from config + DB vocab); verify: results JSON contains a per-slot accuracy block.

## 2. Intent configuration

- [x] 2.1 Create `config/intents.yaml` with the three v1 intents (`search_topic` fallback, `ask_gremium_recent`, `ask_decision_date`) — each with name, German description, lowercase `choices` (including the minimal pairs "was/wann wurde ... beschlossen" and misspelled variants), routing metadata (handler, answer_mode, filters) and slot definitions with `sources:` (db + hard) entries; verify: `yaml.safe_load` succeeds and every intent has name/description/choices.
- [x] 2.2 Ensure the harness and a config-reader helper share one loader (no duplicated parsing); verify: both paths import the same function.

## 3. Organization classification backfill

- [x] 3.1 Implement `src/pgAddOrgClassification.py` (pgCategorise pattern: name-regex → classification, fills NULLs only, trims whitespace in names, `--dry-run`, idempotent); verify: `python src/pgAddOrgClassification.py --dry-run` prints a report of would-be changes; unit test for the regex mapping in `src/tests/test_unit_pgAddOrgClassification.py`.
- [x] 3.2 Run the pass against the DB and confirm: 92 NULL classifications filled, " CDU-Fraktion" whitespace fixed where applicable, re-run is a no-op; verify: SQL count of NULL classifications drops to ~0 and second run changes 0 rows.

## 4. Intent router implementation

- [x] 4.1 Implement `src/pgIntentRouter.py` config loader + vocabulary builder: resolve `sources:` (db table/column/where + hard values), normalise (trim, lowercase), build lowercase criteria lists; verify: unit test builds a gremium list containing "ortschaftsrat neureut" and "gemeinderat" from a seeded test DB (follow `src/tests/conftest.py` fixtures).
- [x] 4.2 Implement the SystemOne client: one payload with intent (noul mode) + slot questions, lowercase `state`, per-intent thresholds from config, timeout + exception handling; verify: unit test with a stubbed HTTP layer maps answers → intent/slots and falls back to `search_topic` on unreachable endpoint.
- [x] 4.3 Implement meeting resolution with org groups: config maps gremien to an org group (`gemeinderat → [Gemeinderat, "Gemeinderat - Beratungen zum DHH"]`, one-off sub-orgs merged at resolve time, not in DB); "gemeinderat" must NOT accidentally match unrelated orgs; latest `Meeting.start_date <= now()` across the group via `Meeting__organization__Organization`; unknown gremium → unresolved flag; verify: unit tests cover latest-held-wins with a future meeting present, group union includes the DHH sub-org's 2 meetings, and unknown-gremium fallthrough.
- [x] 4.4 Implement route execution: build structured filters for `ask_decision_date` (document-type tag facet, values read from DB at load; future meetings excluded by resolver-side date guard), delegate to `search_and_summarize`; verify: unit test asserts the derived filter dict for a decision-date query.
- [x] 4.5 Implement the empty-result ladder: scoped-empty → unscoped retry (filters dropped) → honest empty response with `{intent, filters_tried, scope}`; verify: unit test with a stubbed search returning [] then hits.

## 5. Ask endpoint

- [x] 5.1 Add `POST /ask` to `src/apiServer.py`: accepts query, optional sessionId, top_k/signals; response = search contract + `{intent, intent_scores, slots, applied_filters, fallback_notes}`; sessions stored as today with sessionId reuse accepted; verify: extend `src/tests/test_integration_api.py` with /ask cases (routed query shape, sessionId accepted, decision-model-down → intent `search_topic` + search results, 422 passthrough for invalid params).
- [x] 5.2 Update the apiServer module docstring (the `/ask — drafted but not implemented` note) to describe the implemented behaviour; verify: docstring matches endpoint behaviour.

## 6. Integration verification

- [x] 6.1 End-to-end: start API, post the starter questions ("was wurde im letzten ortschaftsrat neureut beschlossen?", "wann wurde der rückbau der herrenalber strasse beschlossen?", "erzähl was zur theatersanierung") and confirm: intent decoded, filters/slots echoed, results relevant, no 5xx; verify: recorded request/response transcript checked into `docs/` or test output.
- [x] 6.2 Run the full test suite (`python -m pytest src/tests/`) and `openspec validate intent-router`; fix regressions; verify: suite green, validation passes.

## 7. Frontend wiring (app/)

- [x] 7.1 Add `ask()` to `app/src/api.js` (`POST /ask` with query, optional sessionId, topK, summarize); verify: function posts to `/ask` and unwraps JSON like `search()`.
- [x] 7.2 Add `RouteInfo.vue` component: German intent label, scope chips (gremium orgs + meeting date, document-type values), muted fallback-notes line; renders nothing when no intent fields are present; verify: component renders chips for a gremium payload and nothing for a bare search payload (manual or component test).
- [x] 7.3 Switch `App.vue` search flow to `ask()`: pass sessionId, store intent/slots/applied_filters/gremium/fallback_notes/empty_response, render RouteInfo under the query header, show the honest empty block, keep summary/expand/geo flow unchanged; verify: `npm run build` in app/ succeeds and dev flow shows the route banner for the starter questions.
- [x] 7.4 Re-run backend integration suite + `openspec validate intent-router`; verify: suite green, validation passes.

## 8. Meeting-centric gremium answers

- [x] 8.1 Implement `meeting_scope_result` in `src/pgIntentRouter.py`: forward traversal from the resolved meeting via `graphModel.expand_neighbors` (merged depths: agenda items, Tagesordnung + aux files, agenda-item files/consultations/papers), `topics` list (agenda item number/result + files with downloadurl), top_files = Tagesordnung + session aux files; verify: live check on OR-Neureut's latest held meeting returns the meeting-centered graph with agenda items and the Tagesordnung file.
- [x] 8.2 Route `ask_gremium_recent` to `meeting_scope_result` (skip `search_and_summarize`; no LLM summary, no geo; keep intent/filter echo fields and empty-session note); verify: unit test asserts topics/answer_mode on a stubbed traversal and the unknown-gremium fallthrough still runs plain search.
- [x] 8.3 Frontend: `TopicList.vue` (agenda items with clickable files, emits `{kind:'node'}` selections like NetworkView); `App.vue` renders TopicList instead of SummaryCard when `answer_mode === "list_topics"` and skips the async `/summarize` call; verify: `npm run build` succeeds.
- [x] 8.4 Re-run full backend suite + `openspec validate intent-router`; record e2e transcript for the gremium question; verify: suite green, validation passes, transcript shows meeting-centered graph + topics + no map fields.
