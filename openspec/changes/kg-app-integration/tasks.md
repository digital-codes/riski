# Tasks

## 1. kg data access helpers

- [x] 1.1 Implement `src/kg/kgRead.ts`-equivalent Python: `src/kg/kgQueries.py` (fetch statement blocks by paper_sid list, pair-doc joins for `kg_pair_documents`, related-docs shared-tag SQL ordered by confidence-weighted counting) — verify on the live store: 8,266 request statements fetchable in ONE parameterized query; verify the "≥ 2 shared tags" query returns plausible results for a known topical document (e.g. KSC / Straßenbahn)
- [x] 1.2 Unit tests for `kgQueries.py` helpers (mock fixtures mirror the real PG shapes, flagged-field exclusion rule) — verify `pytest src/tests/test_unit_kg_app.py -m unit`

## 2. Related-documents pane (backed by tags)

- [x] 2.1 Add `related_documents` to the `/search` response (documents sharing ≥ 2 kg-topic tags with the top-N results, confidence-weighted score, dedup against the top list, cap 10) — verify the field on a live query AND on a query with no shared tags (empty list case)
- [x] 2.2 Frontend `RelatedDocsList.vue` (list with download links, tooltip w/ shared tags) mounted on the work page — verify visually and via the existing `npm run build` (CI-friendly build check `npm run build` in `app/`)

## 3. Statement-grounded summarizer

- [x] 3.1 Update `pgResultSummarizer` to accept `grounding` entries and build the German grounding block (per spec: skip flagged fields unless `unsicher` note; skip pairs without statements; provenance footer extension `grounding=kg-StatementLayer/pairs=N`) — verify one prompt renders exactly the specified block, and flagged costs are excluded (test with a pair whose involved_cost was flagged)
- [x] 3.2 Wire the API layer to fetch grounding per top document from `kgQueries` and pass it to the summarizer — verify on a served query that the summary contains an outcome sentence extracted from the response statement (e.g. 'einstimmig zugestimmt' rendered as done)

## 4. Topic-focus step in the intent router

- [x] 4.1 Implement the topic vector cache (23 topic descriptions from kgTagSchema via bge-m3) in `pgIntentRouter` and compute per-query topic focus (score ≥ threshold) — verify topic focus is right on 10 curated German queries (Mobility/Sports/Energy/…) with expected topic labels
- [x] 4.2 Wire the retrieval boost (×1.2 multiplier on documents carrying the focus tag, per design D3) into the two consuming intents (`search_topic`, `ask_decision_date`) — verify lexical top hits survive the boost (spec scenario) and unscoped behaviour when no topic fires

## 5. Follow-up loop (sealed state token)

- [x] 5.1 Port auenBot `seal_state/open_state` into `src/kg/kgFollowups.py` with the operator's `STATE_TOKEN_SECRET` env (random fallback, loud warning), session-id validation (`^[A-Za-z0-9_-]{1,64}$`), 7d expiry — verify sealed/open round-trip + tampering raises + expiry raises (unit tests with a fixed secret)
- [x] 5.2 Implement follow-up question generation (3–5 German questions per answer, statement+tag-grounded, decision/model prompt; cap ≤ 5) inserts into `/search` results and `/ask` responses with a sealed `state` — verify on 3 sample queries the number of questions is within 3–5 and they reference answer aspects (outcome, cost, related topic, location, timeline)
-[x] 5.3 Implement the `/ask`-or-`/followup` scoped mode: state opened → prior top-docs + statements become grounding context → new answer + new followups + new sealed token (fresh `_ts`) — verify a fake conversation of 3 turns: token chain survives, each turn's answer contains the grounding block, tampered token → 400, expired token → treated as new query
- [x] 5.3b Implement the clarification mode (design D4b): multi-cluster / lexical-only queries respond with cluster chips instead of full summary; chosen chip re-scopes retrieval via kg-topic-routing and grounds in cluster statements — verify live with 'staatstheater' (spans ≥ 3 clusters) and with a single-cluster short query (no clarification, regular loop)
- [x] 5.4 Frontend: `FollowupChips.vue` (up to 5 chips; click calls `/followup` with question + state) — verify chips render after an /search and the click round-trips the state

## 7. Query threads with followup intent (D7/D8, added 2026-11-20)

- [ ] 7.1 Extend the sealed state payload to a thread record: `thread_id`,
      `turns` (query strings, oldest first), `turn_count`, `origin`
      ("chips" | "search") — verify seal/open round-trips the extra
      fields and a pre-amendment token (no thread fields) opens with
      empty turns (backward compatible)
- [ ] 7.2 Deterministic followup classifier in `pgIntentRouter`: deictic
      lexicon ("das", "die", "es", "sie", "dort", "damit" as head
      markers), no topic-vector fire ≥ threshold, router confidence
      < floor → `thread_followup`; verify on the 4 canonical turns of
      the "Forum Am Recht" example
      ("wo wird das forum am recht gebaut" → normal,
      "welche umweltauswirkungen hat das" → followup,
      "warum haben die grünen dem zugestimmt" → followup,
      "was macht die stadt beim klimaschutz" → break)
- [ ] 7.3 Query concatenation in the API layer: on `thread_followup`
      effective_query = " · ".join(turns[-3:] + [new query]) with the
      sanitization cap; topic focus computed on the concatenated string
      with turn-1 topic retained as boost anchor — verify a 3-turn
      chain keeps the original retrieval focus while recall widens
- [ ] 7.4 Thread budget: turn_count = 5 → force break (new thread_id,
      empty turns) plus an informational note field `thread_reset: true`
      in the response — verify the 6th query in a chain does NOT carry
      prior turns
- [ ] 7.5 Chips-mode gating: when the response carries
      `mode: "chips"` (app-load fallback, non-thematic intent, or below
      the recall confidence floor) suppress `summary`/`top_files`
      rendering fields downstream by the frontend, serve exactly 5 tag
      chips + hint text `Hinweis: Bitte präzisieren Sie Ihre Anfrage.`
      — verify no extra card data in the payload (only thread + chips)
- [ ] 7.6 Frontend thread flow in `WorkPage.vue`: on chips-mode render
      only the chip sheet; on chip pick send a plain `/search` and hide
      the sheet; regular turns send `{thread: {state, sessionId}}`;
      "Neues Thema" button after ≥2 turns clears the thread — verify
      via build + a scripted 6-turn conversation against the live API
- [ ] 7.7 Thread tests in `scripts/test_kg_api.py`: add cases for
      clarification branch (short fuzzy query → `mode: chips`),
      followup chain (3 concats), forced break at turn 6, forged
      token → 400, expired token → new thread (no 400) — verify
      PASS/FAIL matrix with all new rows PASS

## 6. Integration + config

- [x] 6.1 Add config flags `KG_APP_INTEGRATION` (0/1, default 0 until rollout) and `STATE_TOKEN_SECRET` handling w/ warning when unset (auenBot parity); verify with `KG_APP_INTEGRATION=0` the API responses are byte-compatible with today's shape (rollback path)
- [x] 6.2 End-to-end verification: run the API locally (`uvicorn src.apiServer:app`) and walk one query through all four features (related docs visible, grounded summary, topic focus displayed, follow-up chips click → grounded follow-up answer); verify via `curl` output showing the new fields chained

## Workflow follow-up

- After implementation: refresh the canned landing snapshot `app/src/assets/sampleData.json` via `scripts/capture_initial_response.py` if the API shape changed (the work page answers its default query from this snapshot).
- Consider extending `council-exploration-views` later to consume kg statements with its decision-facet design (kept out of this change deliberately).
