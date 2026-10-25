# Design

## Context

Current state: `riski-api.supervisor.conf` (repo root) runs
`python3 -m uvicorn src.apiServer:app --host 127.0.0.1 --port 11384` as
user `okl`; `scripts/restart-api.sh` does a pkill-based restart; the apache
vhost lives only on the host. Analyses from 2026-10-25 established: apache
`Timeout` (60 s default) < LLM latency (up to 90 s + retries); security
headers/rate limiting unconfigured; cron wiring undocumented
(`unified-update-pipeline` provides the exit-code contract).

## Goals / Non-Goals

**Goals:**
- One versioned, commented place for deployment truth.
- Encode the proxy timeout, header, and throttling decisions.
- A cron entry that uses the pipeline's lock and exit-code contract.

**Non-Goals:**
- No application code changes, no new Python dependencies.
- No containerization/systemd migration — supervisor is in use and works.
- No multi-host or load-balancing setup.

## Decisions

**D1 — `deploy/` as the single source.** All deployment artifacts live in
the repo, each with rationale comments; `deploy/README.md` maps repo files
→ host paths so drift is checkable (`diff` step in the rollout). Alternative:
keep pieces where they are — rejected (that is the current archaeology
problem).

**D2 — Proxy settings.** `ProxyTimeout 300` (above the 90 s LLM timeout +
retries, see `api-capacity-hardening` D3); `ProxyPreserveHost On` and
explicit `X-Forwarded-For`/`X-Forwarded-Proto` (the app's trusted-proxy
logic in `api-security-hardening` D2 relies on these being set by exactly
this vhost); `retry=0` so a briefly busy backend is not marked down.
Response buffering stays on (default) — search responses are small; the
long calls are the LLM-bound ones which are single-shot responses anyway.

**D3 — Security headers + coarse throttle at the proxy.** HSTS,
`X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`,
and a frame-ancestors policy; mod_ratelimit/mod_evasive as the coarse
outer layer (connection/bandwidth floods), with the app-level per-client
limiter (`api-security-hardening`) as the precise inner control. Rationale:
defense in depth with different granularity — the proxy cannot know about
LLM costs, the app cannot block floods before they reach uvicorn.

**D4 — Cron entry.**
`flock -n /tmp/riski-update.lock python src/riskiUpdate.py >> log 2>&1`,
mailing only on exit codes 1/2 (per `unified-update-pipeline` D8/D10) with
the report path in the body. `flock -n` (not waiting) because an overlap
means yesterday's run is still going — queueing would only delay it
further. Nightly timing off-peak (e.g. 02:17 — non-round minute, after the
crawler's own window).

**D5 — Supervisor unit refinements.** `stopasgroup`/`killasgroup=true`
(uvicorn spawns a process group; without this, restarts leak workers);
`environment` gains the documented `RISKI_*` variables placeholder;
stdout/stderr logs kept with supervisor's own rotation
(`stdout_logfile_maxbytes`). The pkill-based `scripts/restart-api.sh` is
removed — `supervisorctl restart riski-api` is the supported path (the
script's `pkill -f` pattern is fragile and bypasses supervisor state
tracking).

## Risks / Trade-offs

- [Host/repo drift] → README documents host paths + a diff verification
  step in the rollout.
- [Proxy timeout still exceeded by pathological requests] → the app-side
  bounded fan-out and phase timeouts make such requests rare; the 503 +
  Retry-After contract covers the rest.
- [mod_evasive false positives behind shared NAT] → thresholds set
  generously; the precise app-level limiter is the authoritative control.

## Migration Plan

1. Add `deploy/` (supervisor unit, apache vhost template, crontab example,
   README with rollout + smoke checks).
2. Apply on host: supervisor `reread`/`update`, staged apache config +
   `apachectl configtest` + reload, crontab install.
3. Remove `riski-api.supervisor.conf` (repo root) and
   `scripts/restart-api.sh` after the host runs the new unit.

Rollback: revert the commit; host-side rollback is restoring the previous
vhost/unit (kept in place per the README's rollout step).

## Open Questions

- TLS certificate provisioning (existing certbot setup assumed — to be
  confirmed against the host).
