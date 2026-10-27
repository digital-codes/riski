# Tasks

## 1. Location resolver

- [x] 1.1 Add `resolve_location(session, query, cfg)` to `src/pgIntentRouter.py`: unified vocabulary over `Street` + `District` names (per-request load, normalized lowercase), scored with `word_similarity(lower(name), lower(query))`, returning top-k rows with scores; verify with a psql/pytest check that "was passiert am freidrichsplatz" resolves to Friedrichsplatz (score ≥ 0.5)
- [x] 1.2 Implement the suffix-threshold policy (suffix list + threshold deltas from `config/intents.yaml`): query with a location suffix lowers the acceptance threshold, no suffix never blocks resolution; unit-test "durlach" (no suffix) resolves and a non-location query scores below threshold
- [x] 1.3 Implement the ambiguity rule (accept best; runners-up within the configured delta become alternates) and verify "friedrichsplatz" surfaces "Friedrichstraße" as alternate in the note, mirroring `resolve_gremium`'s note format

## 2. Intent configuration and slot plumbing

- [x] 2.1 Add the `trigram` slot source type to the slot-resolution code path (tables/column/threshold, returns rows + scores like a vocabulary) and verify the harness and router still load `config/intents.yaml` identically (`utils/test_intent_decoder_extended.py` passes)
- [x] 2.2 Add the `ask_location` intent to `config/intents.yaml` (description, route `location_scoped_search`, `location` slot with trigram source, suffix list + thresholds, choices "informationen zum friedrichsplatz" / "was passiert am friedrichsplatz" / "friedrichsplatz", negatives incl. "was gibt es neues zum radweg am terrainkurweg") and verify the decoder harness classifies the choices as `ask_location` and the negatives as fallback
- [x] 2.3 Add `location_scoped_search` handler registration to the `/ask` routing table; verify a mocked decode of an `ask_location` query dispatches to the new handler and `search_topic` queries still dispatch unchanged

## 3. Location-scoped retrieval

- [x] 3.1 Create the retrieval helper (e.g. `src/pgLocationSearch.py`): load candidate agenda-item/file sids from the four association tables with the `gate_status != 'boilerplate'` filter (same rule as `pgGeo._gate_filter`), cap files at `top_k` in fused order, and verify against the DB that street "Friedrichsplatz" yields 16 agenda items and 132 non-gated files
- [x] 3.2 Feed the candidates through the existing post-recall pipeline (rerank with best chunk, top-file list, facets, session result contract) so the response shape equals a search answer; verify with the existing pipeline tests that `top_files`/`matched_entities`/`facets`/`applied_filters` are all present
- [x] 3.3 Implement fallback: unresolvable location → unscoped `search_topic` path + note ("kein Ort erkannt"); decision-model outage → existing global fallback untouched; unit-test both paths

## 4. Response contract and API

- [x] 4.1 Extend the `/ask` response with resolved location(s) (names, types, scores) and the ambiguity note (additive fields only); verify via `src/tests` API-level test that a location query returns `location` + `note` and existing clients' fields are unchanged
- [x] 4.2 Confirm the summary/map flow on a location answer: `summary_files` scope drives `/geo/{session_id}` as today (no map-scope code change); verify a location query's map features come only from enabled summary documents per the map-view rules

## 6. Truncated hit list for broad locations (design D6)

- [x] 6.1 Order the file candidates by attached-meeting recency: `candidate_files` joins `File__meeting__Meeting → Meeting` (max start_date per file, fallback to `File.date`), sorts newest-first and returns the total non-gated hit count alongside the capped rows; verify with an integration test that a file attached to a recent meeting outranks one only carried by its publication date
- [x] 6.2 Add the truncation note: when the linked-file count exceeds the cap, `location_search_stage` reports the total ("N Dateien zu '<ort>' gefunden; die neuesten M werden angezeigt") in the response notes; unit- and integration-test the note's presence and absence (cap not reached)
- [x] 6.3 Run the location test files and the full suite; re-check the live end-to-end answer for "informationen zum friedrichsplatz" (note present, newest-first list)

## 5. Integration verification

- [x] 5.1 End-to-end check against the live DB/API for "informationen zum friedrichsplatz": response routes to `ask_location`, resolves Friedrichsplatz, returns reranked top files drawn from the 132 linked files, and states the note when "Friedrichstraße" scores within the delta
- [x] 5.2 Regression run of the full test suite (`src/tests`, incl. `test_integration_geo.py`, intent decoder harness) plus a spot check that "erzähl was zur theatersanierung" still answers as `search_topic`

## 5. Integration verification
