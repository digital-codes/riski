# Spec Delta (map-view)

## MODIFIED Requirements

### Requirement: Georeference collection for an answer set
The system SHALL collect streets and districts linked (via the existing
street/district ↔ agenda-item and street/district ↔ file association
tables) to the summary document list's enabled documents: once the
summarizer has produced the document list, only references from the
selected (not excluded, not summarizer-refused) documents of that list
SHALL contribute to the map. Graph-side entities reached only through the
OParl traversal (auxiliary files) and agenda-item links SHALL NOT
contribute in that state — their names cannot be correlated with the
document list. The hybrid recall long tail (matched entities not
connected to the graph) SHALL NOT contribute to the map in any state, so
weak matches do not flood it with unrelated streets. Until summary
verdicts exist (pre-summary fetch, meeting-mode answers), the
graph-connected answer set SHALL remain the map scope, with excluded and
refused documents removed. The map SHALL reflect exactly the enabled
document set and update as the user changes it. Presence SHALL be
reported with a `geo_available` flag on the search result.

#### Scenario: Recall tail excluded from the map
- **WHEN** hybrid recall returns weakly matching files (rank > top_k)
  that are linked to unrelated streets
- **THEN** those streets do not appear in the map's FeatureCollection

#### Scenario: Disabled document excluded from the map
- **WHEN** the user disables a document in the summary list and the client
  re-fetches `/geo`
- **THEN** streets/districts referenced only by that document do not
  appear in the FeatureCollection

#### Scenario: Traversal-only references drop once the summary exists
- **WHEN** the graph traversal links auxiliary files or agenda items to a
  street, but none of the summary list's selected documents reference it
- **THEN** the street does not appear in the FeatureCollection after the
  summary verdicts have arrived

#### Scenario: Street named in a query
- **WHEN** a search returns agenda items linked to the street
  "Herrenalber Straße"
- **THEN** the search result carries `geo_available: true` and the
  session retains the linked street/district references

#### Scenario: No georeferences in the answer set
- **WHEN** no agenda item of the answer set is linked to a street or
  district
- **THEN** the search result carries `geo_available: false`

### Requirement: GeoJSON endpoint
The API SHALL expose `GET /geo/{session_id}` returning a GeoJSON
FeatureCollection (WGS84 / EPSG:4326) with one feature per linked street
or district, carrying at least `name`, `type` (street|district) and the
documents that reference it (oparlKey + name; agenda-item references in
the pre-summary fallback scope). Source geometries in EPSG:25832 SHALL be
reprojected. References whose gate status is `boilerplate` (header/footer
address blocks, contact/signature or venue boilerplate) SHALL be omitted;
`content`, `unsure` and ungated references SHALL be served. The endpoint
SHALL respond 404 for unknown sessions and empty FeatureCollection when
the answer set has no georeferences.

#### Scenario: Polygons for linked entities
- **WHEN** `/geo/{session_id}` is requested for a session whose summary
  document list references a street and a district
- **THEN** the FeatureCollection contains both geometries with their
  names and the referencing documents' keys and names

#### Scenario: Boilerplate reference omitted
- **WHEN** a street↔file link is gated `boilerplate` (e.g. the street
  only appears in the document's sender address block)
- **THEN** `/geo` does not return that reference

#### Scenario: No georeferences
- **WHEN** the session's answer set has no georeferences
- **THEN** the endpoint returns an empty FeatureCollection (200)
