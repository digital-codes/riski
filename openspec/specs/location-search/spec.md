# location-search Specification

## Purpose

Location detection and location-scoped retrieval: place references in a user
query (streets, squares, districts; later POIs from the geoportal) are
resolved against the geo vocabulary via typo-tolerant trigram similarity,
and when a place is confidently identified the geo association tables become
the document recall path — deterministic retrieval of all linked agenda
items and files with the standard rerank/summarize/map pipeline on top.
Implemented by `resolve_location` in `src/pgIntentRouter.py` and
`src/pgLocationSearch.py`.

## Requirements

### Requirement: Location resolution from a free-text query

The system SHALL resolve place references in the query by comparing the
normalized query against the unified location vocabulary (street + district
names; later POIs) using trigram word similarity, returning top-k candidates
with scores. Matching SHALL be typo-tolerant, applied to the full normalized
query, and SHALL NOT require token extraction. A location-suffix list SHALL
only lower the acceptance threshold — a query SHALL NOT be rejected from
resolution merely for lacking a suffix.

#### Scenario: Typo'd location name is resolved

- **WHEN** the query "was passiert am freidrichsplatz" is resolved against a
  vocabulary containing "Friedrichsplatz"
- **THEN** "Friedrichsplatz" is returned as the top candidate above the
  acceptance threshold

#### Scenario: Bare location name is resolved

- **WHEN** the query consists only of a location name ("friedrichsplatz")
- **THEN** the location is resolved without requiring additional query words

#### Scenario: Suffix is not required

- **WHEN** a query names a place without a location suffix (e.g. a district
  name "durlach")
- **THEN** the location is resolved the same way as suffixed names

### Requirement: Location-scoped retrieval via geo association tables

When a location resolves confidently, the handler SHALL retrieve documents
through the geo association tables instead of generic hybrid recall: all
non-boilerplate-gated agenda items and files linked to the resolved location
SHALL be candidates. Retrieved files SHALL pass through the existing rerank,
top-file, and summarizer stages unchanged, so the response contract SHALL be
identical to a search answer.

#### Scenario: All linked documents are candidates

- **WHEN** a location with 16 linked agenda items and 135 linked files (3 of
  them boilerplate-gated) is resolved
- **THEN** all 16 agenda items and the 132 non-gated files are retrieval
  candidates, independent of embedding similarity or spelling variants

#### Scenario: Rerank and summary pipeline unchanged

- **WHEN** a location-scoped query is answered
- **THEN** the returned document list and summary are produced by the same
  rerank/summarize stages as a topic search, and the map scope follows the
  existing map-view rules for the summary document list

### Requirement: Truncated hit list for broad location answers

When the number of non-gated files linked to a resolved location exceeds
the document-list cap, the handler SHALL cap the list, preferring files
attached to the most recent meetings (meeting start date; publication date
as fallback). The response SHALL state the total matching-file count and
that only the newest ones are shown.

#### Scenario: Newest meetings win the cap

- **WHEN** a location links 132 visible files and the document list cap is
  10
- **THEN** the listed files are those attached to the most recent meetings,
  and a file linked to a recent meeting outranks one only linked via an
  older publication date

#### Scenario: Truncation is reported

- **WHEN** the linked-file count exceeds the document-list cap
- **THEN** the response states how many files match the location in total
  and that only the newest are listed

### Requirement: Ambiguity and confidence handling

Location resolution SHALL accept a match only above a minimum similarity
score. When several locations match closely (e.g. "Friedrichsplatz" vs
"Friedrichstraße"), the resolved location(s) SHALL be reported with the
response and the ambiguity SHALL be noted in the response in the same manner
as multi-match gremium resolution. When no location resolves confidently,
the request SHALL fall back to the unscoped topic search path and the
response SHALL state that no location could be resolved.

#### Scenario: Ambiguous match is reported

- **WHEN** "friedrichsplatz" matches both "Friedrichsplatz" and
  "Friedrichstraße" above threshold
- **THEN** the response identifies the matched location(s) and carries a note
  naming the alternatives

#### Scenario: Unresolvable location falls back

- **WHEN** no vocabulary name scores above the acceptance threshold
- **THEN** the query is answered as an unscoped topic search and the response
  states that no location was recognized
