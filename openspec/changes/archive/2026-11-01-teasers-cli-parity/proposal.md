# Proposal

## Why

`pgTeasers.py` is the last backfill script with hand-rolled infrastructure: it
opens its own `psycopg2.connect(host='localhost', database='riski_agentic', ...)`
with `-u`/`-p` CLI credentials and talks to the LLM via its own
`requests` plumbing bound to `RISKI_LLM_URL`/`RISKI_LLM_MDL`. Every other
script resolves the database through the shared `src.db` layer and LLM calls
through `src.remote` — so teasers currently ignore the deployment's configured
summary endpoint/model and break on any host where the DB is not
`localhost:5432/riski_agentic`.

## What Changes

- **BREAKING (CLI)**: `-u/--user` and `-p/--password` flags are removed — the
  database connection resolves via `src.db.get_engine()` (private.py → env →
  defaults), exactly like `pgAddSummaries`, `pgCategorise`, etc.
- Teaser generation switches from the local `requests`/retry implementation to
  the shared `src.remote` client: `remote.chat(...)` with the **summary
  model** (`SUMMARY_URL`/`SUMMARY_MDL`, falling back to the legacy
  `LLM_URL`/`LLM_MDL` names) instead of the script-local
  `RISKI_LLM_URL`/`RISKI_LLM_MDL` envs.
- Optional `--model` override passes through to `remote.chat(model=...)` for
  one-off runs; default remains the configured summary model.
- Retry/backoff/429 handling is inherited from `src.remote._post` (the
  script-local `MAX_RETRIES`/`RETRY_DELAY` loop is retired).
- Unchanged: teaser content behavior — chunk-aware map-reduce generation,
  word budget, teaser length ceiling, dedup/`--force`/`--chunked-only`
  filters, per-file transaction handling (incl. the recent rollback fix).

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `document-teasers`: requirement-level change — teasers are generated through
  the shared LLM client using the configured summary model/endpoint (not
  script-local environment variables), and the script connects through the
  shared database access layer instead of hardcoded local connection
  parameters.

## Impact

- `src/pgTeasers.py` — rewritten DB/LLM plumbing; CLI loses `-u`/`-p`, gains
  `--model`.
- Callers/docs: README usage examples with `-u wiski` must be updated.
- No schema changes, no API changes, no other scripts affected.
- Tests: any test invoking `pgTeasers.main()` must now patch `src.db` /
  `src.remote` instead of monkeypatching psycopg2/`requests`.
