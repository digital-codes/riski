# Tasks: add-map-view

## 1. Backend

- [x] 1.1 Spike: inspect `Street.geo` / `District.geo` column format and CRS on the live DB (GeoJSON bytes vs WKB/WKT; EPSG) — record findings in design.md  *(result: GeoJSON FeatureCollection bytes, already WGS84; streets=LineStrings, districts=Polygons; 1833+27 with geometry — no reprojection needed)*
- [x] 1.2 Implement geo collection: for a set of agenda-item sids, resolve `Streets_items_AgendaItems` / `Districts_items_AgendaItems` → street/district rows → geometries; reproject to EPSG:4326 if needed; build GeoJSON FeatureCollection (properties: `name`, `type`, `agendaItems`)
- [x] 1.3 `geo_available` flag in `search_and_build_timeline` results (join-existence check over the answer set's agenda-item sids); session store retains the sids
- [x] 1.4 `GET /geo/{session_id}` endpoint: FeatureCollection (200, possibly empty), 404 for unknown sessions
- [x] 1.5 Integration tests: flag correctness for a georeferenced vs. non-georeferenced query, endpoint shape, empty-collection case, 404

## 2. Frontend

- [x] 2.1 Add `leaflet` + `proj4` dependencies; port klimaDashboard `SimpleMap.vue` → `app/src/components/GeoMap.vue` (API URL data source, distinct styles for streets/districts, popups with name/type/agenda items, fit-bounds, lazy-loaded like NetworkView)
- [x] 2.2 `App.vue`: render `GeoMap` at the bottom when `result.geo_available`; clear on new search
- [x] 2.3 `SummaryCard`: map-available note in the header ("Karte verfügbar — weiter unten") via `mapAvailable` prop
- [x] 2.4 Mobile check: map height/touch behavior consistent with the network view fixes

## 3. Verification

- [x] 3.1 End-to-end: query "Rückbau der Herrenalber Straße" → geo flag true, FeatureCollection contains linked district (Stupferich) with TOP backlink; the street itself has only 2 linked agenda items whose generic names rank outside top-10 (recall depth, not a map issue — POI/WFS ingestion is the future fix for road works)
- [x] 3.2 End-to-end: non-georeferenced query → no flag, no map, no note
- [ ] 3.3 README: map view section (config-free reuse of Street/District data; POI future work)
