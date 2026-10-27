# Spec Delta

## MODIFIED Requirements

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
