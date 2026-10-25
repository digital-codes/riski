# Tasks

## 1. Pool & fan-out configuration

- [x] 1.1 `src/db/__init__.py`: read `RISKI_DB_POOL_SIZE` (default 16), `RISKI_DB_MAX_OVERFLOW` (default 8), `RISKI_DB_POOL_TIMEOUT` (default 30) from the environment into the engine kwargs; unit test asserts the kwargs are applied (`pytest src/tests -m unit`).
- [x] 1.2 Fan-out semaphore in the hybrid search path (module-level `threading.BoundedSemaphore`, `RISKI_FANOUT_BUDGET` default 24, acquired around the per-signal query burst, released in `finally`); on timeout raise a typed `CapacityError`; unit test with a held semaphore (`pytest src/tests -m unit`).

## 2. API behaviour

- [x] 2.1 `/search`: default `summarize=false`; keep `summarize=true` working; update API.md docstring (`src/apiServer.py`); unit test asserting the default produces no `summary` key (`pytest src/tests -m unit`).
- [x] 2.2 Map `CapacityError` and pool `TimeoutError` to 503 + `Retry-After: 5` in `/search` and `/ask`; unit tests (`pytest src/tests -m unit`).
- [x] 2.3 Session store: TTL (default 2 h) + max size (default 1000) with lazy eviction on insert, `RISKI_SESSION_TTL`/`RISKI_SESSION_MAX` envs; 404 semantics unchanged; unit tests for expiry, cap trimming, and no-background-thread (eviction happens within `create`) (`pytest src/tests -m unit`).

## 3. Tests & docs

- [x] 3.1 Integration test: two concurrent searches with a tiny pool + budget return valid results or clean 503s, never 500s (`pytest src/tests -m integration`).
- [x] 3.2 API.md + README: capacity model (threadpool/pool/LLM as the three limits), breaking-change note for the summarize default, worker-count constraint for session endpoints, env-var reference; `openspec validate --changes` passes.
