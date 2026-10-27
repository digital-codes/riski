# intent-routing Specification

## Purpose

Routes natural-language user questions to appropriate answer handlers using a
fast decision model (SystemOne protocol): decodes the question into an intent
via `config/intents.yaml`, resolves slot vocabularies from the database and
config (exact/regex and trigram free-text sources), derives structured
filters, scopes gremium questions to the correct meeting, and guarantees a
useful fallback (unscoped search or an honest "nothing found") for every
query.

## Requirements

### Requirement: Ask endpoint

The API SHALL expose `POST /ask` accepting a query, an optional sessionId, and
optional search parameters (top_k, signals); it SHALL run the first pipeline
stage (recall) and return the first-stage result contract (top_files,
matched_entities, facets, applied_filters) plus the decoded intent, resolved
slots, and echoed derived filters. The timeline and graph SHALL NOT be part of
this response; clients retrieve them via the staged follow-up endpoints using
the returned sessionId. The endpoint SHALL fall back to plain unscoped search
when the decision-model endpoint is unreachable.

#### Scenario: Routed question returns decoded intent and result

- **WHEN** "was wurde im letzten ortschaftsrat neureut beschlossen?" is posted
- **THEN** the response contains the gremium-scoped first-stage result
  (top_files, no timeline/graph payload), the decoded intent name, the
  resolved gremium/meeting slots, and the derived filters; timeline and graph
  arrive via the staged follow-up endpoints

#### Scenario: Decision model unreachable degrades to search

- **WHEN** the SystemOne endpoint cannot be reached
- **THEN** `/ask` returns plain first-stage results with intent `search_topic`
  and does not fail

#### Scenario: Session id accepted

- **WHEN** a previously returned sessionId is passed
- **THEN** the request succeeds and the session is reused (v1: context is not
  yet consulted)

### Requirement: Intent configuration file
Intent definitions SHALL live in `config/intents.yaml`. Each intent SHALL
define at minimum a unique `name`, a German `description` used as decoder
criterion, and example utterances (`choices`) usable as decoder test cases;
optional routing metadata (handler, answer mode, structured filters) and slot
definitions SHALL be read from the same file. A fallback intent (`search_topic`)
SHALL exist and be used when no other intent matches confidently.

#### Scenario: Harness and router share one config
- **WHEN** the decoder test harness and the `/ask` router load the config
- **THEN** both resolve the same intent names, descriptions, and example
  utterances without duplication

#### Scenario: Fallback intent
- **WHEN** a query matches no specific intent above threshold
- **THEN** the query is routed to the fallback intent and answered with plain
  unscoped search

### Requirement: Database-backed slot vocabularies
Slot vocabularies SHALL be resolvable from a list of value sources: database
queries (table, column, optional filter, e.g. councils from `Organization`,
factions from `Person`), trigram similarity matches against a database table
(table, column, acceptance threshold — resolving a free-text query to the
best-matching rows rather than exact or regex matches, e.g. locations from
`Street`/`District`), and hard-coded config values. Loaded values SHALL be
normalised (trimmed, lowercased); the user query SHALL be lowercased before
the decoder call. Vocabularies SHALL be loaded per request (no cache required).

#### Scenario: Councils come from the database
- **WHEN** the gremium slot vocabulary is built
- **THEN** it contains the council organization names/shortnames known to the
  database (e.g. "ortschaftsrat neureut", "gemeinderat") merged with the
  hard-coded config values

#### Scenario: Case-insensitive matching
- **WHEN** the query contains mixed-case or the vocabulary contains names with
  leading whitespace (" CDU-Fraktion")
- **THEN** matching is performed in normalised lowercase space and still
  succeeds

#### Scenario: Trigram source resolves free text to table rows
- **WHEN** a slot declares a trigram source (e.g. the `location` slot against
  `Street.name` / `District.name`) and the query contains an approximate or
  embedded location name ("was passiert am freidrichsplatz")
- **THEN** the slot resolves to the best-matching table rows above the
  source's acceptance threshold, with similarity scores, instead of requiring
  an exact or regex match

### Requirement: Gremium meeting resolution
Gremium-scoped questions with a relative time expression ("letzter", "letzte
Sitzung") SHALL resolve the named organization and select the most recent
**held** meeting of that organization (latest `start_date` that is not in the
future). Scheduled future meetings SHALL never satisfy "letzte". The resolved
meeting SHALL be reported in the response.

#### Scenario: Latest held meeting wins
- **WHEN** "was wurde im letzten ortschaftsrat beschlossen?" is asked while
  the most recent scheduled meeting of that council lies in the future
- **THEN** the search is scoped to the most recently held meeting

#### Scenario: Unknown gremium falls through
- **WHEN** no organization matches the extracted gremium term
- **THEN** the request is answered with unscoped search and the response
  states that the gremium could not be resolved

### Requirement: Decision-type scoping
Questions asking when/that something was decided ("wann wurde X beschlossen")
SHALL scope the search to decision-type documents and exclude documents whose
controlling meeting lies in the future. The derived filters SHALL be echoed in
the response.

#### Scenario: Beschluss filter applied
- **WHEN** a decision-date question is routed
- **THEN** the search carries a document-type filter restricting results to
  decision-type documents

#### Scenario: Future meetings excluded from decisions
- **WHEN** a document is attached to a meeting that has not taken place
- **THEN** it does not satisfy a decision-date question

### Requirement: Meeting-scoped answer presentation
A gremium-scoped answer SHALL present the resolved session as the answer
center instead of a generic search result: the graph centered on the
resolved meeting including its agenda items with their documents, and the
session's Tagesordnung plus auxiliary files as the primary documents.

#### Scenario: Graph centered on the resolved meeting
- **WHEN** a gremium-scoped question is resolved to a meeting
- **THEN** the graph contains the meeting node, its agenda items, the
  Tagesordnung and auxiliary files, and the agenda items' documents

### Requirement: Meeting-scoped topic summary
The summary pane for a gremium-scoped answer SHALL show a topic list
(agenda items with their files, each clickable) instead of the generic LLM
summary, and the answer SHALL not offer the map.

#### Scenario: Topic list with clickable files
- **WHEN** the meeting-scoped answer is rendered
- **THEN** the summary pane lists the agenda items with their files and
  clicking a file opens it in the detail panel

#### Scenario: No map for meeting scope
- **WHEN** a meeting-scoped answer is returned
- **THEN** the response does not offer georeferenced results and the UI
  shows no map

### Requirement: Meeting-scoped node interactions
Clicking a file or meeting in a meeting-scoped answer SHALL open the
existing detail panel with its links.

#### Scenario: Node clicks behave as before
- **WHEN** the user clicks the meeting node in the answer
- **THEN** the detail panel shows the link to the session's calendar page

### Requirement: Empty-result fallback ladder
When a routed search returns no results, the router SHALL retry once without
the intent-derived filters; if the unscoped retry also returns nothing, it
SHALL return an honest empty response naming the intent, the filters tried,
and the resolved scope so the user can reformulate.

#### Scenario: Over-filtered query retries unscoped
- **WHEN** a decision-filtered search returns zero results but unscoped search
  finds hits for the same topic terms
- **THEN** the response contains the unscoped result and reports that the
  decision filter found nothing

#### Scenario: Truly empty
- **WHEN** neither scoped nor unscoped search finds results
- **THEN** the response is an explicit "nothing found" with the tried scopes
  and no fabricated content

### Requirement: Decoder mode selection
The intent decoder SHALL use one of the SystemOne question modes (`choice`,
`noul` per-intent, `score`) selectable via configuration; the mode and the
model SHALL default to the values configured in `src/private.py`
(`SYSONE_URL`, `SYSONE_MDL`). The decoder test harness SHALL read the same
endpoint/model configuration instead of hardcoding them, and SHALL support
negative test cases (utterances belonging to no intent).

#### Scenario: Harness uses configured endpoint
- **WHEN** the decoder test harness is run
- **THEN** it calls the endpoint and model configured in `src/private.py`

#### Scenario: Negative cases can fall through
- **WHEN** a test utterance belongs to no intent
- **THEN** the harness records the fallback intent as an acceptable answer

### Requirement: Ask UI feedback
The web app search box SHALL call `/ask` and SHALL make the routing outcome
visible: the decoded intent (as a German label), the derived scope as filter
chips, and fallback notes as hint text.

#### Scenario: Routed answer shows its scope
- **WHEN** a gremium-scoped question is answered
- **THEN** the UI shows the intent label and a chip with the resolved
  council and its meeting date

#### Scenario: Over-filtered retry is visible
- **WHEN** the fallback ladder retried unscoped after an empty scoped search
- **THEN** the UI shows the fallback note so the user knows the filter
  found nothing

### Requirement: Ask UI empty state
When the `/ask` response contains an explicit empty response, the UI SHALL
show its message with the tried scope instead of silently rendering empty
panes.

#### Scenario: Honest empty state
- **WHEN** neither scoped nor unscoped search finds results
- **THEN** the UI shows the empty-response message with the tried scope and
  no fabricated content

### Requirement: Ask UI tolerant to plain search responses
The UI SHALL keep working when the routing fields are absent (plain
`/search` responses).

#### Scenario: Tolerates missing routing fields
- **WHEN** the response has no intent/routing fields (e.g. plain search
  contract)
- **THEN** the UI renders results without a route banner and without errors
