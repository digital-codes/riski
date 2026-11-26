# intent-routing Delta

## ADDED Requirements

### Requirement: Topic-follow slot decision (topic_follow)

The intent routing SHALL carry a dedicated follow-up decision as a
configured slot on `search_topic` (name: `topic_follow`, choices: nachfrage
/ neues Thema). The decision-model question SHALL include the previous
query as context ("Frage im Verlauf: {prev_query} — Neue Frage:
{current_query}") and decides per request whether the new request is a
follow-up (no subject of its own, refers to the prior topic) or a fresh
topic. `parse_answers` SHALL expose the structured answer in
`slots["topic_follow"]`. The /ask flow SHALL treat
`slots["topic_follow"] == "nachfrage"` OR the deictic-lexicon fallback as
a follow-up (facet amendment: effective query concat + answer-set
carry-over); anything else is fresh (thread break semantics).

#### Scenario: Pronoun followup detected by the model

- **WHEN** the previous query is "was ist das forum recht" and the new
  query is "wo wird es gebaut"
- **THEN** the topic_follow slot answers "nachfrage" and the effective
  query for the search is the concatenation of both queries

#### Scenario: Fresh topic decided by the model

- **WHEN** the previous query is "terrainkurweg" and the new query is
  "was macht die stadt beim klimaschutz" (a subject of its own)
- **THEN** the slot answers "neues Thema" and the thread resets (no
  carry-over, no concat)

#### Scenario: Lexicon fallback when the slot did not answer

- **WHEN** the slot answer is missing/unparseable but the query starts
  with a deictic proform ("wie viel kostet das")
- **THEN** the /ask treats it as a follow-up via the lexicon signal

#### Scenario: No previous query

- **WHEN** the request carries no thread history (first request)
- **THEN** no topic_follow question runs; the routing decides fresh by
  definition

### Requirement: Follow-up turns keep the search type

A follow-up turn SHALL never change the search type: when the turn amends
a prior query (concatenated request — option selection or nachfrage with
history), the routed intent SHALL be the thread's ORIGIN intent (carried
in the sealed state, defaulting to `search_topic`), not the follow-up
text's own decode. The origin intent SHALL be re-sealed so further turns
keep it. A fresh request (no prior turn) SHALL decode freely.

#### Scenario: Follow-up text decodes to another intent

- **WHEN** the thread started as a topic search ("sanierung
  staatstheater") and the follow-up "wer hat das beschlossen" alone
  decodes to the gremien intent
- **THEN** the follow-up turn routes as the origin intent (`search_topic`)
  with the concatenated query

#### Scenario: Origin intent persists across turns

- **WHEN** a follow-up turn completed
- **THEN** the sealed state carries the origin intent for the next turn

#### Scenario: Fresh request may change the search type

- **WHEN** a request carries no prior thread turn
- **THEN** the decode decides the intent without any pinning

### Requirement: Follow-up questions only for follow-up turns

Follow-up question generation (answer chips) SHALL run only for follow-up
turns — requests that amend a prior query. A fresh request SHALL NOT
generate follow-up questions (there is nothing to deepen yet); its sealed
state is still set so a later turn can open the thread. The frontend
SHALL additionally suppress the follow-up card ("Mögliche Vertiefungen")
next to a real hit list: it renders only for the nebulous case and never
next to a summary over selected files.

#### Scenario: Fresh request without questions

- **WHEN** an initial query returns an answer (e.g. "sanierung
  staatstheater")
- **THEN** the response carries no follow-up questions (generation does
  not run) but carries the sealed state

#### Scenario: Follow-up turn with questions

- **WHEN** a request amends a prior query
- **THEN** the response carries the follow-up questions grounded in the
  answer

#### Scenario: Card suppressed next to a summary with files

- **WHEN** the result view shows a summary with selected files (or a hit
  list)
- **THEN** no "Mögliche Vertiefungen" card renders

### Requirement: Follow-up grounding degrades without breaking the turn

A malformed LLM JSON answer during follow-up question generation SHALL NOT
fail the request: the payload is parsed with one brace-region fallback,
then quote-delimited question strings are salvaged deterministically,
else the questions degrade to an empty list. The sealed-state token
SHALL be sealed regardless of question-generation failures, so the token
chain survives an LLM outage in both /search and /followup.

#### Scenario: Malformed JSON salvaged

- **WHEN** the question generator returns JSON that no parser accepts but
  contains quoted question strings
- **THEN** the questions are recovered from the salvage pass (or are
  empty when none exist); the request does not error

#### Scenario: LLM outage keeps the token chain

- **WHEN** follow-up question generation fails in /search or /followup
- **THEN** the response still carries a fresh sealed state; /followup
  reports `state_refreshed` and empty questions