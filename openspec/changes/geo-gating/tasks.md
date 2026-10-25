# Tasks

## 1. GeoGate (`src/geoGate.py`)

- [x] 1.1 Prompt building (content bounded to `max_content_chars`, mention contexts extracted around matches) and defensive verdict parsing (code-fence stripping, per-name lookup, parse failure → all `unsure`/reason); unit tests with a stubbed `src.remote.chat` (`pytest src/tests -m unit`).
- [x] 1.2 `gate_file` / `gate_agenda_item` (one batched call per document) and `write_verdicts` (UPDATE `gate_status`, `gate_reason`, `gated_at`, `gate_model`); LLM failure → `unsure` with reason "llm error", never raises; unit tests (`pytest src/tests -m unit`).
- [x] 1.3 Column migration helper: `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` for the four assoc tables (pgTagMgr pattern); unit test on a scratch schema (`pytest src/tests -m unit`).

## 2. Map gating (defect: disabled documents)

- [x] 2.1 `/geo`: exclude `result["summary_excluded"]` keys in addition to `summary_refused`; files not yet in `summary_files` stay visible; unit tests with a fake session (`pytest src/tests -m unit`).
- [x] 2.2 `pgGeo.collect_geo`: filter `gate_status <> 'boilerplate'` on all four assoc tables (NULL/content/unsure pass); unit + integration test (`pytest src/tests`).
- [x] 2.3 Frontend check: confirm `fetchGeo()` fires on every toggle/refine (already wired in `App.vue`) — add a regression note/test if needed. *(Wiring confirmed in `WorkPage.vue` — the component `App.vue` grew into: `onToggleFile`/`onRefine` → `runSummarize` → `fetchGeo()` when `geoAvailable`, plus the initial summary response; no frontend test infra exists (no vitest), so no regression test added.)*

## 3. Write-time gating in the geo scripts

- [x] 3.1 `pgAddFileGeoRefs.match_files`: after flushing new links per file, batch-gate via `GeoGate` (try/except → NULL on failure); `--no-gate` flag to skip; unit tests with stubbed gate (`pytest src/tests -m unit`).
- [x] 3.2 `pgAddStreetRefs` / `pgAddDistrictRefs`: gate new agenda-item links against the item name; same failure semantics; unit tests (`pytest src/tests -m unit`).
- [ ] 3.3 (deferred — gate-only per ops decision) Deterministic pre-filter: extend evidence extraction with an address-line heuristic (PLZ+Karlsruhe line blocks) feeding the gate's context; keep `_VENUE_NOISE`; unit tests (`pytest src/tests -m unit`).

## 4. Cleanup pass (`src/pgGeoGateCleanup.py`)

- [x] 4.1 Batch iteration over `gate_status IS NULL` rows per assoc table, gate via `GeoGate`, write verdicts; resumable (cursor = ungated query); `--batch`, `--limit`, `--table`; unit tests (`pytest src/tests -m unit`).
- [x] 4.2 `--dry-run` (verdict distribution report, no writes) and `--reprocess unsure`; `--purge-boilerplate` (optional DELETE with confirmation prompt); unit tests (`pytest src/tests -m unit`).
- [x] 4.3 Integration test (live DB, rollback-free on the assoc tables only): gate a handful of NULL rows, verify map filter honours them (`pytest src/tests -m integration`). *(`src/tests/test_integration_geoGate.py`: boilerplate hidden from link set + collect_geo features; NULL/unsure/content pass; gate-status changes committed and restored in `finally` — verdict counts after the test match the apply run exactly.)*
- [x] 4.4 Run the cleanup against the live database; record before/after counts in the change summary. (**done** — apply run 2026-10-25, `docs/geo-gate-apply-2026-10-25.md`; incremental dry-run log superseded at `docs/geo-gate-dryrun-2026-10-25.md`. Before: 44,918 ungated rows (all NULL). After: 39,800 content · 5,060 boilerplate (hidden from map) · 58 unsure · 0 errors, 0 NULL left. Per table: Streets_items_Files 20,930 → 18,684/2,208/38 · Districts_items_Files 19,174 → 16,398/2,765/11 · Streets_items_AgendaItems 2,355 → 2,347/3/5 · Districts_items_AgendaItems 2,459 → 2,371/84/4.)

## 5. Verification & docs

- [x] 5.1 Live verification: default query — Hebelstraße no longer on the map; toggle document #2 off → its refs disappear; re-enable → back. *(Default query: Hebelstraße's 2 answer-set links are both `boilerplate` now — pre-gating it was the ONLY street on the map, post-gating `collect_geo` returns no Hebelstraße features. Toggle on "rückbau herrenalber strasse": 467 features → exclude file 1087 → 369 → re-enable → 467. Excluding a file without exclusive refs (15722, shared streets) legitimately leaves the count unchanged.)*
- [x] 5.2 README (geo refs section) + `openspec validate --changes`. *(README map-view section now documents the gate + cleanup workflow; validation below.)*
