# Proposal: fix-followup-deixis

## Why

Follow-up detection is implicit: `classify_thread_turn` uses a deictic lexicon
("das/es…"), while the request-thread history ("was ist das forum Recht" →
"wo wird es gebaut"; "es" refers to the prior subject) and the SystemOne
decision model routing have no dedicated follow-up specification. Live trace:
"wo wird es gebaut" classifies followup in some paths but the routed intent is
computed separately — the ROUTING and the thread semantics are not one decision.

The user's design: there SHOULD be an explicit intent-like specification
(`topic_follow`) in the configs: the model is asked "the previous query was
X, the user now asks Y — is Y a follow-up (no subject of its own) or a fresh
topic?" — with a structured choices answer (nachfrage / neues Thema). Because
the model gets both questions, it decides follow-up vs fresh —

Wording rule: request = user input into intent routing; the follow-up then
amends the topic (facet amendment — change `request-thread-facets` overlays
the carry-over).

## What Changes

- **`topic_follow` as a slot of `search_topic`** in `config/intents.yaml`:
  a ModelOne slot decision with the fixed choices `["nachfrage",
  "neues Thema"]` and the CONTEXT question (prompt `topic-follow-slot-question`:
  "Frage im Verlauf: {prev_query}\nNeue Frage: {current_query}") — the
  decision-model decides follow-up vs fresh per request.
- `build_questions(cfg, vocab, prev_query=None)` — the slot question
  interpolates the previous query; the SystemOne payload stays
  single-purposed (the state carries the CURRENT query only).
- `parse_answers` exposes `slots["topic_follow"] = "nachfrage" | "neues
  Thema"` (validated againstChoices; unknown → None).
- `/ask` flow threading: the previous query reaches the decision via
  `route_ask(..., prev_query=...)`; the /ask's follow-up classification
  becomes `(slots.topic_follow == "nachfrage") OR deictic lexicon` (the
  model decision takes precedence, the lexicon is the fallback when the
  slot is unanswered). The thread state advances with the correct
  concatenated/facet semantics (change `request-thread-facets` overlays).
- The deictic lexicon stays as a fallback signal only (service protection
  for slots that did not answer).
- `/search` keeps its lexicon-only thread (no extra model decision there —
  the thread decisions belong to the request flow via /ask).

## Capabilities

- **Modified Capabilities**: `intent-routing` — the follow-up decision is a
  configured slot decision (topic_follow) with the previous query as context.

## Impact

- Config: `config/intents.yaml` (search_topic slot topic_follow).
- Code: `src/pgIntentRouter.py` (`build_questions`, `parse_answers`,
  `decode/ask` signature prev_query), `src/apiServer.py` (/ask wiring).
- Prompts: new `topic-follow-slot-question` registry entry.
- One decision-model call per /ask request (no additional round trip — the
  question joins the existing decode payload).
