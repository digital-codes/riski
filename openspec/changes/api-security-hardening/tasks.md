# Tasks

## 1. Client identity & limiter

- [ ] 1.1 Client-ID resolution util: socket address, or last `X-Forwarded-For` hop when the peer is in `RISKI_TRUSTED_PROXIES` (default `127.0.0.1`); unit tests cover direct, proxied, and spoofed cases (`pytest src/tests -m unit`).
- [ ] 1.2 Sliding-window limiter middleware: per-client per-group deques, groups `llm` (`/ask`, `/summarize`, `/search` with `summarize=true`) and `search` (all other endpoints except `/health`); `RISKI_RATE_LIMIT_LLM` (default 10/min), `RISKI_RATE_LIMIT_SEARCH` (default 60/min); 429 + `Retry-After` before any work; unit tests for boundary, group independence, health exemption (`pytest src/tests -m unit`).

## 2. Input bounds & error hygiene

- [ ] 2.1 pydantic bounds: `query` `max_length=512`; `filters`/`exclude`/`signals` item-count bounds on `SearchRequest`/`AskRequest`/`SummarizeRequest`; 422 path; unit tests (`pytest src/tests -m unit`).
- [ ] 2.2 Generic error responses with correlation id (uuid logged per failure) for DB-unavailable (503) and unexpected exceptions (500) on all endpoints; full detail only in the log; unit test asserting no exception text in bodies (`pytest src/tests -m unit`).
- [ ] 2.3 Integration test: simulate a DB failure and an intent-router exception, assert generic bodies and logged details (`pytest src/tests -m integration`).

## 3. Configuration & docs

- [ ] 3.1 `RISKI_CORS_ORIGINS` env override (comma-separated) over the dev defaults; unit test (`pytest src/tests -m unit`).
- [ ] 3.2 API.md + README security section: threat model summary (anonymous, inference-expensive API behind public proxy), the controls, env reference, proxy trust boundary; `openspec validate --changes` passes.
