# Design: add-map-view

## Context

The data layer already links agenda items to streets/districts
(`Streets_items_AgendaItems`, `Districts_items_AgendaItems`, built by
`pgAddStreetRefs`/`pgAddDistrictRefs` via name matching) and stores
geometries in the `Street.geo` / `District.geo` columns (loaded from
GeoJSON by `pgAddStreets`/`pgAddDistricts`). The klimaDashboard project
(https://github.com/digital-codes/klimaDashboard) provides a proven
Leaflet map component (`SimpleMap.vue`: Leaflet + proj4, EPSG:25832→4326
reprojection, GeoJSON popups, multiple tile sources incl. GeoPortal
Karlsruhe) that is largely reusable.

Open question (spike): the exact on-disk format of the `geo` columns
(GeoJSON bytes vs. WKB vs. WKT) and CRS — `pgAddStreets` loads GeoJSON
"optionally with geometry"; `SimpleMap.vue` reprojects EPSG:25832.

**Spike result (2026-10-23, live DB):** the `geo` columns hold **GeoJSON
FeatureCollections as UTF-8 JSON bytes** — one per street/district:
- Streets: `LineString` features (segments), **already WGS84** (lon 8.4 /
  lat 49.05), no `crs` declaration
- Districts: `Polygon` features, **already WGS84**
- Coverage: 1833/1915 streets, 27/27 districts have geometry; 2298
  street↔agenda-item and 2394 district↔agenda-item links

Consequence: **no server-side reprojection needed** (and no proj4 in the
frontend) — parse the JSON bytes, tag features with
`{name, type, agendaItems}`, merge into one FeatureCollection.

## Goals / Non-Goals

**Goals:**
- Show the spatial dimension of an answer set: which streets/districts
  are involved, with popups linking back to the agenda items
- Async loading (map is heavy; search stays fast)
- Reuse the klimaDashboard map component with minimal adaptation

**Non-Goals:**
- POI ingestion (road constructions etc. via WFS) — the GeoJSON format
  supports Point features; ingestion is future work
- Geocoding arbitrary addresses; only existing street/district links
- Editing geometry or spatial queries beyond "collect linked entities"

## Decisions

### 1. Separate endpoint, not a `/search` field

`GET /geo/{session_id}` returns the FeatureCollection on demand. Reasons:
polygons are heavy (district boundaries are large), the map loads after
first paint, and the session store already holds the answer set. The
search result only carries the boolean `geo_available` flag (cheap to
compute — a join-existence check over the linked agenda-item sids).

### 2. Collection logic: answer-set agenda items → assoc tables → geometry

```
agenda item sids (from the search result's graph/street-district links)
  → Streets_items_AgendaItems → street_id → Street.geo/name
  → Districts_items_AgendaItems → district_id → District.geo/name
  → FeatureCollection (WGS84), one feature per street/district:
      properties: { name, type: "street"|"district",
                    agendaItems: [oparlKey, ...] }
```

- The session store gains the agenda-item sids (from `search`); `/geo`
  resolves them against the association tables at request time so links
  stay consistent with the DB.
- Reprojection happens server-side once (proj4 equivalent or GeoPandas,
  already a dependency) — the frontend receives EPSG:4326 GeoJSON ready
  for Leaflet.

### 3. Frontend: adapted SimpleMap → `GeoMap.vue`

Reuse the klimaDashboard component's structure (Leaflet init, tile
sources incl. BaseMapDE/GeoPortal KA, proj4 reprojection kept as a
safety net, popup rendering) with changes:

- Data comes from the API URL (`/api/geo/{sessionId}`) — matches
  SimpleMap's `dataUrl` prop design
- Styling: streets (lines/polygons) vs districts (polygons) get distinct
  colors + a small layer legend; popups list name, type and the linked
  agenda items
- Fit bounds to the returned features instead of fixed Karlsruhe view
- Props simplified: `sessionId`, `visible`; no chart-specific props

Dependencies: `leaflet`, `proj4` (both proven in klimaDashboard).

### 4. Summary header note

`SummaryCard` gains a `mapAvailable` prop; when true the header shows
"📍 Karte verfügbar — weiter unten" next to the query-guided summary
note. App.vue sets it from `result.geo_available` and keeps it until the
next search clears the panes.

## Risks / Trade-offs

- **Geo column format unknown** (spike first): if the binary is WKB,
  parsing needs `shapely`/`geojson` conversion — still server-side only.
- **Large district polygons** — served once per session; acceptable at
  city scale. If needed later: simplification (topojson) as follow-up.
- **Popup link target** — agenda items have no standalone page; popups
  list the item names/keys and the meeting calendar link is reachable
  via the network view. Keep popups informational.
- **Leaflet bundle size** (~150 kB) — loaded lazily with the map, same
  pattern as ECharts in NetworkView.

## Migration Plan

1. Spike: inspect `Street.geo`/`District.geo` format + CRS on the live DB.
2. Backend: geo collection + `/geo/{session_id}` + `geo_available` flag
   + tests.
3. Frontend: `GeoMap.vue` (port from klimaDashboard) + integration +
   summary note + build verification.
