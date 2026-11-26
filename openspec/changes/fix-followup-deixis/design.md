# Design: fix-followup-deixis

## Context

The follow-up decision currently lives in the kodex lexicon
(`classify_thread_turn` / `_is_deictic` in `pgIntentRouter`) — deterministic
but blind to references that aren't pure pronouns and blind to facet
amendments ("… kosted das" works, an arealOLLOW "wo wird es gebaut" wording
variants may not). The decision model (SystemOne) routes intents but has no
follow-up specification — the single `search_topic` intent carries it all.

## Decisions

1. **Followup decision as a configured SLOT on `search_topic`**
   (intent):
   ```yaml
   - name: search_topic
     slots:
       topic_follow:
         description: >-
           Nachfrage im Anfrageverlauf oder neues Thema
         choices: [nachfrage, neues Thema]
         question_prompt: topic-follow-slot-question
   ```
   The SystemOne slot protocol is a CHOICE question (like the gremium slot)
   with the choices fixed (not a vocabulary); the question text interpolates
   BOTH queries. `build_questions(cfg, vocab, prev_query=None)` adds:
   ```json   {"id": "slot_topic_follow", "type": "choice",
     "question": topic-follow-slot-question.format(prev_query=prev or "", current=query),
     "choices": ["nachfrage", "neues Thema"]}
   ```
   The question is added ONLY when `prev_query` AND the current query differ
   meaningfully (first request → no question → model stays out).
2. **parse_answers** — `slots["topic_follow"] = choice` only when the choice
   is in the configured values; unknown/blank → absent.
3. **/ask wiring** — `route_ask(..., prev_query=...)`: the previous query is
   the LAST turn of the sealed thread state (read via open_state BEFORE the
   thread turn advance); `/ask` (apiServer) passes it. Flow:
   the /ask decides `followup = slots.topic_follow == "nachfrage" OR
   _is_deictic(query)`; the thread turn (advance/concat/carry-over) then
   follows the followup semantics change `request-thread-facets` overlays.
4. **/search unchanged**: its thread decisions remain lexicon-only (no extra
   decision-model round trip; the topic_follow slot only rides /ask decodes
   (the `prev_query` is optional — /search decodes don't supply it).
5. **SystemOne state** carries the CURRENT query (unchanged); the previous
   query goes into the SLOT QUESTION only — so the other intents' noul
   scores stay on-topic.

## Risks / Trade-offs

- [Slot threshold: a "nachfrage" answer could misfire on a genuinely fresh
  question] → grade: the SystemOne slot choice protocol is a single-choice
  answer — stuck to a YES/NO question ("followup?" = choices) is binary;
  model-side it's the same accuracy class as the gremium slot choice. The
  deictic lexicon ORs in — a false "nachfrage" still ends in a merged
  query, not a data break.
- [Prev query polluted the question] → the slot question carries ONLY
  the topic_follow slot (not the routing intents); other intents' scores
  don't see it.

## Open Questions

None.
