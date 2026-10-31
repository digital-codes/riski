# Tasks: sanitize-queries-and-initial-response

## 1. Query sanitation (backend)

- [x] 1.1 `validate_user_query()` helper in src/apiServer.py: trim, non-empty, ≤ 250 chars, allowed classes (Unicode letters incl. umlauts/ß, digits, whitespace, punctuation allow-list); raises HTTPException 400 with a German message naming the problem
- [x] 1.2 Apply in `/search` and `/ask` before any retrieval/decision-model work
- [x] 1.3 Unit tests: valid query 200 (mocked pipeline); control char / markup / emoji / >250 chars / whitespace-only → 400 with German detail; umlauts, ß, numbers and punctuation accepted; boundary 250 chars accepted, 251 rejected

## 2. Snapshot capture

- [x] 2.1 New `scripts/capture_initial_response.py`: run the staged pipeline for the default query from config/instance.yaml (`_stage1_search_fn` → `timeline_stage` → `graph_stage` documents scope → `ResultSummarizer` → geo FeatureCollection) and write `app/src/assets/sampleData.json` (`snapshot: true`, `sessionId: null`, capture date)
- [x] 2.2 Run the capture and verify the written JSON contains all staged fields (top_files, timeline, graph with expandable_types, summary, geo FeatureCollection)

## 3. Frontend canned start

- [x] 3.1 WorkPage: `snapshotMode` state; runSearch routes the trimmed default query to the snapshot (all panes from the file, no API call, subtle hint, no error banner); other queries unchanged; per-search reset clears snapshotMode
- [x] 3.2 loadSampleFallback reuses the same apply path (offline banner only in the unreachable case)
- [x] 3.3 Snapshot-mode guard: refine button, file toggles and neighbour expansion render disabled with hint; fetchGeo short-circuits (geo FeatureCollection from the snapshot)
- [x] 3.4 Frontend build check (`npm run build` in app/)

## 4. Verification

- [x] 4.1 `python3 -m pytest src/tests/test_unit_apiServer.py src/tests/test_integration_api.py -q` (or existing api test modules) — all pass
- [x] 4.2 Live check: `/ask` with the default query against the running backend still returns 200 and the same-shaped result as the snapshot fields; `/ask` with `<script>` and a 300-char query returns 400 with German messages
- [x] 4.3 Manual smoke: app with backend down shows the snapshot landing view with hint; a non-default search shows the offline banner as before
