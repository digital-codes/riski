# Spec Delta

## Purpose

Turn riski answers into a navigable conversation: after each answer the
backend emits 3–5 topic-relevant follow-up questions and passes
conversation state to the frontend as an opaque sealed token (the
auenBot backend-stateless pattern) — no server-side session shadowing.

## ADDED Requirements

### Requirement: Follow-up question generation
After each answered query (`/search` summary or `/ask` response) the
backend SHALL generate 3–5 German follow-up questions related to the
answer: a decision-model + statement-driven prompt over the answer, the document
statements, and the kg-topic tags of the top documents — one question
per heterogeneous aspect (outcome detail, cost, affected locations,
related topics, timeline). The questions reference the session scope,
not the user's private data.

#### Scenario: Outcome follow-up
- **WHEN** the answer is a document summary for a request that has a
  response statement "einstimmig zugestimmt" — including follow-ups
  sized 3–5 questions
- **THEN** at least one follow-up relates to the outcome (e.g. "Wurde
  die Maßnahme umgesetzt?").

#### Scenario: Statement- and document-linked follow-ups
- **WHEN** the answered pair references documents with kg-topic tags
  (e.g. Sports)
- **THEN** at least one follow-up relates to a suggested topic that
  shares those tags.

#### Scenario: 3–5 bounds honoured
- **WHEN** insufficient aspects are derivable from the answer
- **THEN** the backend emits fewer but never more than 5 follow-ups

### Requirement: Clarification mode for short/fuzzy queries
For queries that return documents spanning multiple kg-topic clusters
(top-5 documents spread over ≥ 3 distinct topics) or that resolve only
via the trigram/lexical signal (embedding match below threshold), the
first response SHALL operate in clarification mode instead of the plain
follow-up loop: the response presents clustered options derived from
the document clusters' dominant topics ("Meintest du X …, oder Y …?")
as follow-up chips sealed into the state token; the next turn replays
retrieval with the chosen cluster as the topic focus.

#### Scenario: Multi-cluster short query
- **WHEN** the query "staatstheater" resolves to 5 lexical documents
  whose kg-topic tags span Culture, Economy and Sport clusters
- **THEN** the response presents ≥ 3 follow-up chips naming the
  cluster topics with one representative document each, and the
  plain summary is shortened or omitted

#### Scenario: Single-topic query unchanged
- **WHEN** a short query's top documents share enough dominant topics
  (fewer than 3 clusters)
- **THEN** the regular follow-up loop runs (no clarification mode)

#### Scenario: Chosen cluster re-scopes retrieval
- **WHEN** the user picks a clarification chip (e.g. "die
  GfK-Kosten-Debatte")
- **THEN** the next turn applies the cluster's dominant topic as the
  topic focus (kg-topic-routing boost/filter) and the answer grounds in
  the cluster's statements

### Requirement: Stateless state via sealed session tokens
The conversation state (previous query, top doc ids, statement refs)
SHALL be conveyed by an opaque sealed token returned with the answer
and returned by the client on the next turn — AES-GCM sealed with a
key derived via HMAC-SHA256 over the server secret
(`STATE_TOKEN_SECRET`) and the session id, session id as associated
data (auenBot `seal_state`/`open_state` pattern, v1 token format,
expiry via sealed `_ts`). The backend SHALL not persist per-session
conversation state beyond the existing run/session store (aggregate
audit keeping: `kg_followups_runs`-class audit rows are permitted).
Tampered, foreign-session, or expired tokens SHALL be rejected with
400 + German error message.

#### Scenario: Stateless state transfer
- **WHEN** a client answers a follow-up with the sealed token
- **THEN** the backend recovers the state without a DB session lookup
  (no shadow session persistence beyond audit rows)

#### Scenario: Tampered token
- **WHEN** the client modifies a sealed token or uses it under a
  different session id
- **THEN** the API responds 400 with a German error message, mirroring
  the auenBot behaviour

#### Scenario: Token expiry
- **WHEN** a token's sealed `_ts` is older than
  `STATE_TOKEN_MAX_AGE` (default 7d)
- **THEN** the follow-up is accepted as a NEW query (no state, no
  error) and a fresh token is issued

### Requirement: Follow-up responses reuse stored context
A follow-up turn SHALL re-run the pipeline in a **scoped mode**: the
previous round's top documents and statements become part of the
grounding context (token payload), plus full retrieval over the new
question. The response SHALL always carry fresh follow-up tokens so
the conversation can continue; statements with failure flags are
excluded as in the primary summary.

#### Scenario: Follow-up grounded in prior outcome
- **WHEN** a follow-up asks "wurde die Maßnahme umgesetzt" after an
  outcome answer
- **THEN** the response grounding includes the retrieved pair's
  response statement fields (cheap, one round-trip)

## REMOVED Requirements

(none)
