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

## 5. File georeferences + stale-link pruning + geo scope (added during review)

- [x] 5.1 `src/pgAddFileGeoRefs.py`: match street/district names against File `name` + `teaser` (boundary-valid matching via `local_geo_matching`), write `Streets_items_Files` / `Districts_items_Files` assoc tables (file_sid, name_match)  *(single matching mechanism: `prepare_street_matcher` from local_geo_matching — the same matcher as the agenda refs; 31805+16475 links; venue-boilerplate noise filter for "Rathaus am Marktplatz"; evidence-based name_match `[name|teaser] …excerpt…`)*
- [x] 5.2 Stale-link pruning for the existing agenda-item geo refs: delete links whose stored `name_match` no longer matches the current agenda-item name (fixes the Stupferich phantom reference)  *(root cause was worse: pgAddStreetRefs/pgAddDistrictRefs stored AgendaItem.id instead of sid — mis-joins looked like phantom references. Both scripts now store sid; agenda geo tables rebuilt: 2298+2394 rows, 100% sid-join; 75101 correctly unlinked)*
- [x] 5.3 Extend `pgGeo` (`collect_geo`, `geo_available_for_keys`) to include file-linked georeferences (File nodes/entities of the answer set)
- [x] 5.4 Run backfill + prune; verify file 614953 links to "Herrenalber Straße" and the street appears in the map for the street query  *(verified: street on map via 59 file references; top-10 files all Herrenalber Straße docs with lexical+name+content matches; `--rebuild` flag added to pgAddFileGeoRefs for clean re-runs)*
- [x] 5.5 Geo scope restriction: map reflects the graph-connected answer set only; matched_entities long tail excluded (analysis: 1475 features/65 streets → 175/13 for the Herrenalber query)

## 6. Document provenance + summarizer gating (added during review)

- [x] 6.1 Feature provenance: GeoJSON properties carry the referencing documents (`files` + `fileNames` for file links, `agendaItems` + `agendaItemNames` for agenda links); map popups list them
- [x] 6.2 Machine-readable relevance verdict: summarizer prompt lists refused documents by `Datei <Nummer>`; `_parse_refused` resolves them to `result["summary_refused"]` (oparlKey + name)
- [x] 6.3 `/geo` gates file keys on the verdict (refused documents' georeferences excluded); frontend refetches `/geo` when the summary verdict arrives (map may load before the async summary)
- [x] 6.4 GeoMap as pure renderer (FeatureCollection prop) + 4 new unit tests (verdict parsing); E2E live-verified: 4 documents refused, map gated accordingly
