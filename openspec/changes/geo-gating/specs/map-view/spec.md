# Spec Delta (map-view)

## MODIFIED Requirements

### Requirement: Georeference collection for an answer set
The system SHALL collect streets and districts linked (via the existing
street/district ↔ agenda-item and street/district ↔ file association
tables) to the graph-connected answer set — the seed files and the
entities reached through the OParl traversal. The hybrid recall long tail
(matched entities not connected to the graph) SHALL NOT contribute to the
map, so weak matches do not flood it with unrelated streets. References
from documents the user has excluded in the summary document list
(`summary_excluded`) SHALL NOT contribute, in addition to the already
excluded summarizer-refused documents — the map SHALL reflect exactly the
enabled document set and update as the user changes it. Presence SHALL be
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
agenda items that reference it. Source geometries in EPSG:25832 SHALL be
reprojected. References whose gate status is `boilerplate` (header/footer
address blocks, contact/signature or venue boilerplate) SHALL be omitted;
`content`, `unsure` and ungated references SHALL be served. The endpoint
SHALL respond 404 for unknown sessions and empty FeatureCollection when
the answer set has no georeferences.

#### Scenario: Polygons for linked entities
- **WHEN** `/geo/{session_id}` is requested for a session whose answer
  set references a street and a district
- **THEN** the FeatureCollection contains both geometries with their
  names and referencing agenda-item keys

#### Scenario: Boilerplate reference omitted
- **WHEN** a street↔file link is gated `boilerplate` (e.g. the street
  only appears in the document's sender address block)
- **THEN** `/geo` does not return that reference

#### Scenario: No georeferences
- **WHEN** the session's answer set has no georeferences
- **THEN** the endpoint returns an empty FeatureCollection (200)
