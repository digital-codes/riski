# intent-routing Delta

## ADDED Requirements

### Requirement: Follow-up requests are facet amendments

A classified follow-up request SHALL be treated as an AMENDMENT of the
original request within the same topic: the effective query is the
concatenation of the request history with the new input, AND the prior
answer set persists — up to 5 of the prior request's selected documents
(`top_docs` in the sealed context) travel into the next response marked
`via: "aus Ihrer vorherigen Anfrage"`, ranked after the new search hits.

#### Scenario: Facet amendment carries the answer base

- **WHEN** a follow-up request (deictic or low-signal) runs against a
  prior request whose selected documents are in the sealed context
- **THEN** the response's file list contains the new search hits first and
  the prior documents (marked "via") after them

#### Scenario: Follow-up with an empty new search

- **WHEN** the new search part of a follow-up yields no hits
- **THEN** the carried documents remain the answer (no topic jump)

### Requirement: Slot-filling options for underspecified requests

When intent routing decodes a clear intent but a REQUIRED slot cannot be
resolved uniquely (e.g. ask_gremium_recent with no/ambiguous body), the
backend SHALL respond with a structured OPTIONS payload
(`{mode: "options", options: {facet, entries}}`) instead of running an
unscoped or guessed search. The user's selection travels as an `option`
selection and fills the slot deterministically. Options SHALL only be
offered when the residual space is enumerable and small (≤ 8 entries for
the gremium facet); otherwise the pipeline degrades as before.

#### Scenario: "wann war die letzte sitzung"

- **WHEN** the request is decoded as ask_gremium_recent but no body is
  determinable
- **THEN** the response offers the known bodies as options (topic = body
  name, example = its latest held meeting date) instead of results

#### Scenario: Option selection fills the slot

- **WHEN** the user selects a body option
- **THEN** the scoped gremium search runs with an organization filter for
  the selected body

#### Scenario: Options only in bounded spaces

- **WHEN** the ambiguity space exceeds the bound (e.g. too many matching
  organizations)
- **THEN** no options payload; the pipeline behaves as before (unscoped
  search/hint)