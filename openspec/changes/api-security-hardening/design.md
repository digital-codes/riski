# Design

## Context

`src/apiServer.py` serves an unauthenticated, inference-expensive API. The
public surface is apache2 (loopback uvicorn behind mod_proxy). Existing
state: CORS hardcoded to dev origins, `_sessions` unbounded (bounded
separately in `api-capacity-hardening`), error handlers embedding raw
exception text, and no per-client throttling. The project already has
privilege separation in the DB layer (read-only role for search endpoints).

## Goals / Non-Goals

**Goals:**
- Bound the cost an anonymous client can inflict (LLM spend, pool, memory).
- Stop leaking exception details in responses.
- Make CORS deployment-aware without hardcoding a domain.
- Define the app↔proxy trust boundary precisely.

**Non-Goals:**
- No authentication/authorization (public open-data service; rate limiting
  is the control, auth is a future decision if abuse appears).
- No request signing or captcha.
- No IP blocking lists beyond the rate limiter's 429 behaviour.

## Decisions

**D1 — App-level sliding-window limiter, keyed by client.** In-process
middleware: per-client-ID deque of timestamps per protected endpoint group;
window (default 60 s) and per-group limits configurable
(`RISKI_RATE_LIMIT_LLM`, default e.g. 10/min; `RISKI_RATE_LIMIT_SEARCH`,
default e.g. 60/min). Exceeding → 429 + `Retry-After`. Rationale for
in-process: single-worker deployment (documented capacity constraint),
zero new dependencies; a shared-store limiter (Redis) only becomes
necessary with multi-worker scale-out, which is itself deferred. Alternative:
apache-only (mod_ratelimit measures bandwidth, not request rates per route;
mod_evasive is coarse) — kept as the outer coarse layer in
`deployment-config`, not the precise control.

**D2 — Client identity: last hop of the `X-Forwarded-For` chain.** The app
trusts forwarded headers only when the connection comes from the configured
proxy ranges (env `RISKI_TRUSTED_PROXIES`, default `127.0.0.1`); otherwise
the socket address is used. This prevents limiter bypass via spoofed
headers when running bare on a dev box, while working correctly behind the
proxy.

**D3 — Protected group = LLM-triggering endpoints.** `/ask`,
`/summarize`, and `/search` with `summarize=true` share the tighter LLM
budget (checked *before* any work is done); plain `/search`,
`/expand`, `/facets`, `/geo` get the looser search budget. `/health` is
never limited (monitoring).

**D4 — Generic error bodies.** Handlers for DB-unavailable and unexpected
exceptions return fixed messages ("database temporarily unavailable",
"internal error") + correlation id; full details go to the application log.
Rationale: exception text includes SQL fragments and internal paths; the log
already has them, so nothing diagnostic is lost to the operator.

**D5 — Input bounds at the schema.** `max_length=512` on `query` fields
(default, env-tunable is not needed — schema constant suffices); arrays
(filters, exclude, signals) bounded by pydantic `max_length` too. Rationale:
cheap, declarative, returns 422 automatically.

**D6 — CORS from env.** `RISKI_CORS_ORIGINS` (comma-separated) overrides the
dev defaults when set; the dev defaults remain for local work. Apache
serves the production frontend on the same origin, so production typically
needs no CORS at all — the env escape hatch is for split deployments.

## Risks / Trade-offs

- [Shared-NAT offices hit the LLM limit] → generous defaults, per-group
  separation, 429 + Retry-After (client can back off politely); limit
  configurable without code changes.
- [In-process limiter resets on restart] → acceptable for DoS cost-bounding
  (not billing enforcement); documented.
- [Spoofed X-Forwarded-For on misconfigured proxies] → trust is keyed to
  the proxy range env; default trusts only loopback.

## Migration Plan

1. Client-ID + trusted-proxy resolution + unit tests.
2. Sliding-window limiter middleware + unit tests.
3. Input bounds + generic error handlers + unit tests.
4. CORS env config + README/API.md security section.

Rollback: revert the commit; all controls are additive middleware/config.

## Open Questions

- Should 429 responses be counted/metrics-exported? (Deferred — no metrics
  stack in the project yet.)
