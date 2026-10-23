# Proposal: add-map-view

## Why

Some queries hit documents with georeferences — e.g. "wie stehts mit dem
Rückbau der Herrenalber Straße" names a street. The database already
links agenda items to streets and districts (`Streets_items_AgendaItems`,
`Districts_items_AgendaItems` via `pgAddStreetRefs`/`pgAddDistrictRefs`)
and stores their geometries (GeoJSON-derived `geo` columns in `Street`/
`District`). Today that spatial dimension is invisible in search results:
a user asking about a street gets documents but never sees *where*.

## What Changes

- **Backend**: for each search result, collect the streets/districts
  linked to the answer set's agenda items and expose their geometries as
  a GeoJSON FeatureCollection via a new `GET /geo/{session_id}` endpoint
  (kept out of `/search` — polygons are heavy and the map loads async).
  The search result gains a cheap `geo_available` flag so the frontend
  knows whether to ask.
- **Frontend**: a `GeoMap.vue` component (adapted from the
  klimaDashboard `SimpleMap.vue` — Leaflet + proj4, EPSG:25832→4326
  reprojection, popups) rendered **at the bottom** of the page when
  georeferences exist. The SummaryCard header shows a note ("Karte
  verfügbar …") when the map is present, so users know to scroll down.
- **POIs (descoped)**: point-layer support in the GeoJSON format is
  designed in (properties already fit), but POI ingestion — e.g. road
  constructions from transparenz.karlsruhe.de via the TBA geoserver WFS —
  is future work.

## Capabilities

### New Capabilities
- `map-view`: Search results with street/district georeferences SHALL be
  accompanied by a map view rendering the linked geometries as a GeoJSON
  layer, with a scroll hint in the summary header.

### Modified Capabilities
- `search-api`: the session SHALL retain the answer set's georeferences
  and expose them via `GET /geo/{session_id}`; `/search` results SHALL
  carry a `geo_available` flag.

## Impact

- **Code**: `src/apiServer.py` (geo endpoint + session extension),
  `src/graphModel.py` or new `src/pgGeo.py` (geometry collection),
  `app/src/components/GeoMap.vue` (new), `App.vue` / `SummaryCard.vue`
  (integration + note), `app/package.json` (leaflet, proj4).
- **No graph/timeline changes** — the map is an additional view fed by
  the same answer set.
- **Format note**: geometries are served as GeoJSON WGS84 (EPSG:4326);
  EPSG:25832 source data is reprojected (proj4, as in klimaDashboard).
