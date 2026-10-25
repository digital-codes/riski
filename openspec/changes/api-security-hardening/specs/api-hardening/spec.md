# Spec Delta

## ADDED Requirements

### Requirement: Per-client rate limiting

The API SHALL enforce per-client request rate limits using a sliding
window. The client SHALL be identified from the socket address, or from the
`X-Forwarded-For` chain's last hop when the connection originates from a
configured trusted proxy range. Endpoints that trigger LLM calls SHALL
share a tighter budget than plain search/expand/facet endpoints; the
`/health` endpoint SHALL never be rate limited. A request exceeding its
group's limit SHALL be rejected with 429 and a `Retry-After` header before
any work (including LLM calls or database queries) is performed.

#### Scenario: LLM budget enforced before work
- **WHEN** a client exceeds the LLM-group limit on `/ask`
- **THEN** the request is rejected 429 with `Retry-After` and no LLM call
  is made

#### Scenario: Groups are independent
- **WHEN** a client exhausts the LLM budget
- **THEN** plain search/expand/facet requests from the same client still
  succeed within their own budget

#### Scenario: Forwarded identity trusted only from proxies
- **WHEN** a request arrives directly (not from a trusted proxy) with a
  spoofed `X-Forwarded-For`
- **THEN** the client is identified by the socket address, not the header

#### Scenario: Health endpoint stays unlimited
- **WHEN** monitoring polls `/health` at high frequency
- **THEN** responses are always served, never 429

### Requirement: Request input bounds

Query fields SHALL be bounded in length (default 512 characters); requests
exceeding the bounds SHALL be rejected with 422 before any processing.
Structured fields (filters, exclusion lists, signal toggles) SHALL be
bounded in item count.

#### Scenario: Oversized query rejected
- **WHEN** a query longer than the configured maximum is posted to
  `/search` or `/ask`
- **THEN** the API responds 422 without touching the database or the LLM

### Requirement: Sanitized error responses

Client-facing error responses SHALL contain stable, generic messages (plus
a correlation id); raw exception text, SQL fragments, and internal paths
SHALL appear only in the application log, never in response bodies.

#### Scenario: Database outage does not leak internals
- **WHEN** the database is unreachable and a request fails
- **THEN** the response body contains a generic message and correlation id,
  while the log records the full exception

#### Scenario: Unexpected exception on /ask
- **WHEN** the intent router raises an unexpected exception
- **THEN** the response body contains a generic message and correlation id,
  while the log records the full exception

### Requirement: Configurable CORS origins

Allowed CORS origins SHALL default to the local development origins and
SHALL be overridable via configuration (environment) for split
deployments; when unset in a same-origin production deployment, no
additional origins SHALL be allowed.

#### Scenario: Production origins via configuration
- **WHEN** `RISKI_CORS_ORIGINS` is set to a list of production origins
- **THEN** cross-origin requests from exactly those origins are accepted

## MODIFIED Requirements

(none — `search-api`'s endpoint contracts are unchanged; error-response
sanitization is specified above and applies to the existing endpoints'
failure paths)
