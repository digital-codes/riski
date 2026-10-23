# map-view Change Spec

## ADDED Requirements

### Requirement: Georeference collection for an answer set
The system SHALL collect streets and districts linked (via the existing
street/district ↔ agenda-item and street/district ↔ file association
tables) to the graph-connected answer set — the seed files and the
entities reached through the OParl traversal. The hybrid recall long tail
(matched entities not connected to the graph) SHALL NOT contribute to the
map, so weak matches do not flood it with unrelated streets. Presence
SHALL be reported with a `geo_available` flag on the search result.

#### Scenario: Recall tail excluded from the map
- **WHEN** hybrid recall returns weakly matching files (rank > top_k)
  that are linked to unrelated streets
- **THEN** those streets do not appear in the map's FeatureCollection

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
reprojected. The endpoint SHALL respond 404 for unknown sessions and
empty FeatureCollection when the answer set has no georeferences.

#### Scenario: Polygons for linked entities
- **WHEN** `/geo/{session_id}` is requested for a session whose answer
  set references a street and a district
- **THEN** the FeatureCollection contains both geometries with their
  names and referencing agenda-item keys

#### Scenario: No georeferences
- **WHEN** the session's answer set has no georeferences
- **THEN** the endpoint returns an empty FeatureCollection (200)

### Requirement: Map view at the bottom
The web app SHALL render a map view (Leaflet-based) at the bottom of the
page when the search result has `geo_available: true`, showing the
GeoJSON layer with popups (name, type, linking agenda items) and a
default view centred on Karlsruhe. When absent, no map SHALL be rendered.

#### Scenario: Map appears for georeferenced query
- **WHEN** a search with `geo_available: true` completes
- **THEN** a map is rendered at the bottom of the page showing the
  streets/districts of the answer set

#### Scenario: No map without georeferences
- **WHEN** a search completes with `geo_available: false`
- **THEN** no map section is rendered

### Requirement: Scroll hint in the summary header
When the map is presented, the SummaryCard header SHALL show a note that
a map is available further down the page.

#### Scenario: User is informed to scroll
- **WHEN** the map is rendered
- **THEN** the summary header displays a note (e.g. "Karte verfügbar —
  weiter unten") while the map exists

## Future Work (descoped)

- **POI layers** — point features from external sources (e.g. road
  constructions: transparenz.karlsruhe.de dataset via TBA geoserver WFS,
  `mobil.trk.de/geoserver/TBA/ows`), ingested into a POI table and merged
  into the `/geo` FeatureCollection. The GeoJSON format and map component
  already support Point features.
