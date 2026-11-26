# intent-routing Delta

## MODIFIED Requirements

### Requirement: Gremium meeting resolution
Gremium-scoped questions with a relative time expression ("letzter", "letzte
Sitzung") SHALL resolve the named organization and select the most recent
**held** meeting of that organization **that carries documents** (agenda
items or meeting files). Meetings whose documents are not yet published
(scheduled rows with zero agenda items/items/files) SHALL be skipped for
the answer and SHALL be explained in a clear note ("Dokumente für die
Sitzung am <date> sind noch nicht veröffentlicht — zuletzt mit Dokumenten:
<date>").

German month names (+ optional year) in the query SHALL select the target
meeting of the matched organization: "…im September" or "…im September
2026" → the held meeting in that month/year; a month without a year SHALL
default to the current year. When no held meeting with documents exists in
the requested month/year, the response SHALL state so explicitly and SHALL
NOT silently fall back to another month. Scheduled future meetings SHALL
never satisfy "letzte" or a month filter. The resolved meeting SHALL be
reported in the response.

#### Scenario: Latest held meeting wins
- **WHEN** "was wurde im letzten ortschaftsrat beschlossen?" is asked while
  the most recent scheduled meeting of that council lies in the future
- **THEN** the search is scoped to the most recently held meeting

#### Scenario: Latest meeting without documents is skipped
- **WHEN** the most recent held meeting row exists but carries no agenda
  items and no files, and the latest meeting with documents is older
- **THEN** the search scopes to that older meeting and the response notes
  that the newer session's documents are not yet published

#### Scenario: Month without year resolves to current year
- **WHEN** "themen der gemeinderatssitzung im september" is asked in the
  current year and the held September meeting carries documents
- **THEN** the search scopes to the September meeting of the current year

#### Scenario: Month filter without documents stated explicitly
- **WHEN** the requested month/year has no held meeting with documents
  for the organization
- **THEN** the response states that no documents exist for that month
  (with the neighbouring months if known), without falling back

#### Scenario: Unknown gremium falls through
- **WHEN** no organization matches the extracted gremium term
- **THEN** the request is answered with unscoped search and the response
  states that the gremium could not be resolved

### Requirement: Gremium session scopes are head-of-chain minimal views

The `ask_gremium_recent` intent SHALL resolve the gremium kind and the
meeting date (LLM extraction with JSON verdict, falling back to the
vocabulary/regex path on failure) and SHALL return ONLY the session
content: agenda topics with their files and the meeting documents —
computed by direct database aggregation, NOT the graph expansion (no
graph is built or attached at all for this intent). No graph, no timeline
card, no summary, no related documents, no refinement chips and no
follow-up questions SHALL be attached to a gremium-session response.
The topic list SHALL expose a popup on each topic with the topic
information (number, name, result, meeting date) and the document links
(download URL). A gremium session query is head-of-chain: the thread/context
state SHALL be reset (new thread, no sealed token flowing from the prior
conversation).

#### Scenario: Minimal session view

- **WHEN** a query resolves to `ask_gremium_recent`
- **THEN** the payload carries topics/files only — no `graph`/timeline card,
  no summary, no `related_documents`/chips, no `followups`

#### Scenario: Head-of-chain resets context

- **WHEN** a gremium session query follows a prior conversation
- **THEN** the thread restarts (no sealed token from the previous topic)

#### Scenario: Gremium and date extraction

- **WHEN** the query names a gremium kind and a date ("gemeinderat im
  april 2026", "letzte sitzung umweltausschuss")
- **THEN** the resolved target indicates that gremium kind and that date
  (relative "letzte" = latest held meeting with documents)
