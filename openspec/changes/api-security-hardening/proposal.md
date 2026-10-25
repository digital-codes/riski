# Proposal

## Why

The API is unauthenticated and sits behind a public apache2 proxy, and
several endpoints are inference-expensive: every `/ask`, every
`/search?summarize=true` and every `/summarize?refine=true` triggers LLM
calls against a configured (possibly paid) endpoint. Today nothing bounds
that: no rate limiting, no request-size caps beyond `min_length=1`, an
unbounded session store, and error handlers that echo raw exception text
(`503 detail=f"database unavailable: {exc}"`, `/ask`'s `500 detail=str(exc)`)
— leaking infrastructure details to any client. One anonymous visitor with a
script can exhaust the LLM budget, the DB pool, or the process memory. The
perimeter itself is also unconfigured: uvicorn is correctly bound to
loopback, but apache (the actual public surface) has no rate limiting,
security headers, or forwarding hygiene yet.

## What Changes

- **Rate limiting** — per-client request limits on the LLM-triggering
  endpoints (`/ask`, `/summarize`, `/search` with `summarize=true`),
  enforced in the application (per-client-ID sliding window, configurable;
  client ID from `X-Forwarded-For` chain, only trusting the proxy-set
  value). Exceeding a limit returns 429 with `Retry-After`. Apache-level
  throttling (mod_ratelimit/mod_evasive) is configured in
  `deployment-config` as the coarse outer layer; the app-level limiter is
  the precise one and also works when the app is exposed directly on a dev
  box.
- **Request hygiene** — maximum query length (default 512 chars) on
  `/search` and `/ask` via pydantic constraints; oversized or non-text
  bodies rejected 422.
- **Error hygiene** — client-facing errors carry stable, generic messages;
  exception details go to the log only. The 503-database and 500-intent
  paths stop echoing `{exc}` to clients.
- **CORS via configuration** — the dev origins stay as default; production
  origins come from an env var (`RISKI_CORS_ORIGINS`) so the real frontend
  domain is configured at deploy time, not hardcoded.
- **Proxy contract documented** — uvicorn stays loopback-only; the apache
  vhost (TLS, security headers, correct `X-Forwarded-*` handling, no
  direct-to-backend exposure) is specified in `deployment-config`; the app
  documents that it trusts forwarded headers only from the proxy.

## Capabilities

### New Capabilities

- `api-hardening`: request throttling, input size limits, sanitized error
  responses, and configurable CORS for the search API.

### Modified Capabilities

- `search-api`: error responses become generic (details logged, not
  returned); query length is bounded.

## Impact

- **Code**: `src/apiServer.py` (limiter middleware, pydantic bounds, error
  handlers, CORS config); `src/remote` untouched. No schema changes.
- **Risk**: rate limits can throttle legitimate shared-IP users (office
  NAT); limits default generously and are configurable. Overly strict
  error sanitization could hide useful diagnostics — the log keeps full
  detail.
- **Tests**: unit tests for the sliding-window limiter, client-ID
  extraction, query-length rejection, and generic error bodies; integration
  test that exception details never appear in responses.
