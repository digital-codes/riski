# Proposal

## Why

The deployment pieces exist but live in three different places (a supervisor
unit in the repo root, a restart script, an undocumented apache vhost on the
host) and none of them encode the decisions the last three analyses forced:
the proxy timeout must exceed LLM latency (apache's 60 s default silently
502s healthy 90 s summaries), the pipeline needs a concrete cron entry with
lock/exit-code handling, and the security perimeter (TLS, headers, forwarded
headers, coarse throttling) is nowhere specified. Operations today is
archaeology.

## What Changes

- **`deploy/` directory** in the repo as the single source of deployment
  truth, each file commented with its rationale:
  - `deploy/riski-api.supervisor.conf` — replaces the repo-root unit (adds
    `RISKI_*` env documentation, log rotation hints, explicit
    `stopasgroup`/`killasgroup`).
  - `deploy/apache-riski.conf` — vhost template: TLS termination,
    `ProxyPass` to loopback, `ProxyTimeout` above the longest legitimate
    request, `ProxyPreserveHost` + `X-Forwarded-*` hygiene, security
    headers (HSTS, `X-Content-Type-Options`, `Referrer-Policy`), coarse
    mod_ratelimit/mod_evasive as outer layer, static-cache rules.
  - `deploy/crontab.example` — nightly `riskiUpdate` entry: `flock`ed,
    report path in the mail body, exit codes 1/2 trigger mail.
  - `deploy/README.md` — the capacity model (threadpool / DB pool / LLM as
    the three limits), the worker-count constraint (sessions are
    in-memory → single worker, or sticky sessions/stateless tokens if
    scaled out), and step-by-step rollout.
- **Repo-root cleanup**: the old supervisor unit and `scripts/restart-api.sh`
  are replaced by documented supervisor usage (restart via `supervisorctl`
  restart riski-api); the ad-hoc `pkill`-based script is removed.
- **No application code changes** — this change is configuration and
  documentation only.

## Capabilities

### New Capabilities

- `deployment`: the operational configuration contract — process management,
  proxying, TLS/security headers, scheduled pipeline execution — as
  reviewable, versioned config with rationale.

### Modified Capabilities

(none)

## Impact

- **Code**: none. Files moved/added only; supervisor unit path changes
  require a one-time `supervisorctl reread && supervisorctl update` on the
  host.
- **Risk**: config drift between the repo and the host — mitigated by
  `deploy/README.md` stating the host file locations and a
  verify-diff step; apache changes are staged on the host before commit.
- **Tests**: not unit-testable; verification is a documented smoke check
  (`curl -I` for headers, `/health` through the proxy, `flock` overlap
  behaviour) in `deploy/README.md`.
