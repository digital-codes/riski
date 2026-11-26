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