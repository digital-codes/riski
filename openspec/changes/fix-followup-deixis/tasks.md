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
