# Tasks

## 1. Instance config loader

- [x] 1.1 Create `src/instanceConfig.py`: `DEFAULTS` (today's Karlsruhe constants: system URL, folders, log name, page size 1000, delay 0.25, Karlsruhe URL rewrite, address city "Karlsruhe", venue-noise regex, THH canonicalization on, org classification rules, district columns NAME/NUMMER, branding, map center 49.0069/8.4037), `get_instance_config()` with lru-cache, `RISKI_INSTANCE_CONFIG` path resolution and `RISKI_<SECTION>__<KEY>` env overlay; verify with unit tests for precedence (env > yaml > default), nesting and cache invalidation
- [x] 1.2 Ship `config/instance.yaml` as a commented example (all keys, Karlsruhe values, a München-flavoured alternative block commented out); verify `load_intents_config`-style validation errors on malformed files and that `get_instance_config()` with the shipped file equals the defaults

## 2. Crawler instance-independence

- [x] 2.1 `oparlUpdate.py`: read system URL/folders/log name/page size/delay/URL rewrites through the loader (CLI flags still override); unit-test that constants resolve via config and CLI precedence holds
- [x] 2.2 Replace `/bodies/0001` with enumeration of `system.bodies` (config `oparl.bodies` filters); abort with a clear error when enumeration fails; unit-test collection-URL building for a stubbed two-body system and the abort path
- [x] 2.3 Convert `fix_karlsruhe_url` to the configured rewrite list; unit-test an empty list (no rewriting) and the Karlsruhe default entry producing today's URLs

## 3. Instance-agnostic enrichment rules

- [x] 3.1 `geoGate.py`/`pgGeoGateCleanup.py`: build `_PLZ_CITY` and the prompt's city references from the configured city; unit-test the regex for "München" and that the Karlsruhe default matches exactly the old pattern
- [x] 3.2 `pgAddFileGeoRefs.py`: venue-noise patterns from config (list of regexes); unit-test an empty list and the Karlsruhe default
- [x] 3.3 `pgCategorise.py`: gate `Haushalt THH <n>` canonicalization behind `rules.doc_type_canonicalization.haushalt_codes`; unit-test pass-through when disabled and unchanged behavior when enabled
- [x] 3.4 `pgAddOrgClassification.py`: classification rules + fallback label from config with today's defaults; unit-test a custom two-rule config and default parity
- [x] 3.5 `pgAddDistricts.py`: GeoJSON attribute columns from config; unit-test with a fixture using different column names

## 4. Instance endpoint and frontend branding

- [x] 4.1 Add `GET /instance` to `apiServer.py` serving the whitelisted frontend projection; API-level test asserts the payload and that unknown/unreachable config degrades to current strings
- [x] 4.2 Frontend: fetch `/instance` at startup into a store with fallback to current hardcoded values; wire title, footer, legal pages, map center (`GeoMap.vue`), data-source list (`DocsPage.vue`) and default query (`WorkPage.vue`); verify the dev app renders identically with the Karlsruhe defaults and `npm run build` succeeds

## 5. Bootstrap and documentation

- [x] 5.1 Create `scripts/bootstrap_instance.sh` (createdb → pgGen schema → syncIncremental → OCR/chunks/summaries/embeddings → geo load → gate cleanup) reading `RISKI_INSTANCE_CONFIG` + `DB_NAME`/`POSTGRES_URL`; shellcheck-clean, `set -euo pipefail`
- [x] 5.2 README section "Running a second instance": config walkthrough, env overrides, credential hygiene note (private.py gains env fallbacks); verify the documented command sequence is consistent with the script
- [x] 5.3 Add env fallbacks for every `src/private.py` key/endpoint (pattern: env var read in `src/remote`/`db` before the private attribute); unit-test one representative key (env wins over private.py, private.py wins over nothing)

## 6. Verification

- [x] 6.1 Full test suite green (`python -m pytest src/tests`); no existing test modified except where the loader replaced constants
- [x] 6.2 Karlsruhe regression: `syncIncremental --dry-run` (or a short real crawl) produces identical targets/URLs as before the change; `/search` and `/ask` answers unchanged against the live DB
- [x] 6.3 Second-instance smoke test — re-scoped per user decision (no second database on this host; pg_hba is database-specific and cannot be extended here): config resolution, live body enumeration (Karlsruhe + Dresden incl. the singular-`body` quirk), and a real crawl + resource save into the configured Dresden folders with no database involved; the schema/import step runs via `scripts/bootstrap_instance.sh` once an operator hba entry exists
