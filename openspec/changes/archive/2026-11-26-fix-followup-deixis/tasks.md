# Tasks: fix-followup-deixis

## 1. Config + prompts

- [x] 1.1 `config/intents.yaml`: the `topic_follow` slot on `search_topic` (choices nachfrage/neues Thema, `question_prompt: topic-follow-slot-question`)
- [x] 1.2 New `topic-follow-slot-question` prompt in `config/instruction_prompts.json` ("Frage im Verlauf: {prev_query} — Neue Frage: {current_query}" + Nachfrage-kriterien narrative)

## 2. Router plumbing

- [x] 2.1 `build_questions(cfg, gremium_vocab, prev_query=None)`: the topic_follow slot question (only with prev_query; choices from the config)
- [x] 2.2 `parse_answers`: `slots["topic_follow"]` validated against the configured choice values
- [x] 2.3 `IntentRouter.decode(query, *, prev_query=None)` passes prev_query into build_questions; `pgIntentRouter.ask(..., prev_query=None)` threads it through

## 3. /ask wiring

- [x] 3.1 `/ask`: read the previous query (last sealed turn) and pass `route_ask(..., prev_query=…)`; the thread turn's classification becomes `slots.topic_follow == "nachfrage" OR _is_deictic(query)` (the model decision wins)
- [x] 3.2 Options/option-turn path: `prev_query` also threads (option turn classification stays deterministic)

## 4. Verification

- [x] 4.1 Live trace: "was ist das forum recht" → "wo wird es gebaut" → slot answers nachfrage → effective query = the concatenation; thread carries the turns
- [x] 4.2 "terrainkurweg" → "was macht die stadt beim klimaschutz" → neues Thema → thread break (no carry-over)
- [x] 4.3 Unit tests: build_questions slot emission (with/without prev), parse_answers validation, /ask flow followup mixture
- [x] 4.4 Full suite green (458 pass, 1 tracked audit failure); README wording synced — the followup decision is a configured slot decision (model answer + deictic fallback OR)

- [x] 4.5 UI: the stage-1 /ask flow hydrates the thread state (`_consumeThreadState(result)` — the missing call left threadState null after a normal search, so the browser followup sent {fresh:true} and never reached the topic_follow decision; the state machine per docs/request-thread.md)

- [x] 4.5 Deictic lexicon re-scoped (live defect from the 3-query sequence): user queries arrive LOWERCASE — the mid-sentence capitalization rule matched everywhere ("was ist das forum recht" → deictic on turn 1; the stale thread then leaked into q3). Kept: last/first-word proforms only; mid-sentence goes to the topic_follow model decision
- [x] 4.6 Carry-over sid fix (the /timeline + /graph 500 KeyError): carried entries now include the File sid (timeline_stage builds file_sids from top_files)
- [x] 4.7 Sequence verified: "was ist das forum recht" → "was ist mit der umweltbelastung" (neues Thema/Break) → "wie kam es zum neuen ksc stadion" (frisch, kein Nachfolge-Echo der ersten Frage); /timeline /graph /summarize 200 on a carry-over answer

## Workflow follow-up

- `/opsx-archive` after apply.

## 5. Shipped follow-through (session 2026-11-26 — grounding, gating, pinning)

- [x] 5.1 Grounding degrade: `kgFollowups.generate_followups` never raises on malformed LLM JSON (brace-region fallback + deterministic question salvage); `/followup` seals the fresh token BEFORE generation and `/search`'s `_kg_enrich` seals independently — an LLM outage no longer breaks the token chain. Verified by `test_unit_kgFollowups.py` (salvage, degrade-empty, bare-list, seal continuity for both endpoints).
- [x] 5.2 Fresh requests have no follow-ups (fix-followup-deixis principle applied to the chips): `_kg_enrich(..., followup=)` gates generation on `turn["concatenated"]` in /search and /ask; a fresh request seals its state only. Verified by `TestFreshRequestNoFollowups` (fresh → no followups, generation not called; followup turn → questions).
- [x] 5.3 Follow-up keeps the search type: /ask forces the thread's ORIGIN intent (sealed `intent`, default `search_topic`) for concatenated turns — the follow-up text's decode can no longer flip topic search into the gremien flow; fresh requests decode freely. Verified by `TestFollowupKeepsSearchType` (live case "sanierung staatstheater" → "wer hat das beschlossen" stays topic search; fresh → decode decides).
- [x] 5.4 UI: "Mögliche Vertiefungen" card suppressed next to a real hit list / summary with selected files (same guard as the related-hints card, `app/src/components/WorkPage.vue`). Verified: `npm run build` passes.
- [x] 5.5 Docs synced: `docs/request-thread.md` (sequence note: followups only for follow-up turns; the keeps-search-type rule), `README.md` (session popup links the stored download URL), module docstrings (`kgFollowups.generate_followups`, `apiServer._kg_enrich`, `pgIntentRouter.meeting_scope_result`).
