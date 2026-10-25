# RISKI deployment configuration

The deployment decisions and their rationale live here as *templates* —
this repository is developed on a non-deployment machine, so every
host-specific value (paths, user, server name, TLS) is a placeholder
(`<REPO_DIR>`, `<SERVER_NAME>`, …) to be filled against the actual
deployment host. The repo↔host contract: when a host file differs from
these templates, either the host is stale or these templates are — resolve
the drift before the next change.

## Templates → host mapping

| Template | Host location | Apply |
|---|---|---|
| `riski-api.supervisor.conf` | `/etc/supervisor/conf.d/riski-api.conf` | fill placeholders → `sudo supervisorctl reread && sudo supervisorctl update` |
| `apache-riski.conf` | `/etc/apache2/sites-available/riski.conf` | merge rationale blocks into the real vhost → `sudo apachectl configtest && sudo systemctl reload apache2` |
| `crontab.example` | deployment user's crontab | fill `<REPO_DIR>`/`<OPERATOR>` → merge with `crontab -e` |

Verify drift: diff each host file against the template after every
deployment-related change (this is the rollout step, not an afterthought).

## Capacity model (change: api-capacity-hardening)

Three stacked limits determine how many users the API serves:

```
 anyio threadpool (40 threads)     ← ceiling for ALL concurrent requests
 DB pool (16 + 8 overflow = 24)    ← /search fan-out bursts ≤12 connections
                                     per request → ~2–3 heavy searches
 LLM endpoint throughput           ← the real bottleneck for /ask and
                                     inline summaries (10–90 s each)
```

- The LLM summary is **out of the `/search` hot path by default**
  (`summarize=false`); clients use the async `POST /summarize` follow-up.
- Saturation degrades as **503 + Retry-After** (fan-out budget
  `RISKI_FANOUT_BUDGET`, pool timeout `RISKI_DB_POOL_TIMEOUT`), never as
  raw 500s.
- Tuning envs (all optional, defaults tested): see the RISKI_* block in
  `riski-api.supervisor.conf` and API.md.
- **Single worker is the supported deployment** — the session store is
  in-memory; multiple workers behind round-robin break `/geo`,
  `/summarize`, `/sessions` (404s). Scale-out paths, if ever needed:
  sticky sessions at the proxy (cookie-based), or stateless session
  tokens.

## Security perimeter (change: api-security-hardening)

Two rate-control layers:

1. **Outer (this directory)**: security headers and any host-level
   throttling in the apache vhost — bounds floods before they reach
   uvicorn; TLS termination is host-specific.
2. **Inner (app)**: per-client sliding-window limiter
   (`src/apiRateLimit.py`) — tight budget on LLM-triggering endpoints
   (`RISKI_RATE_LIMIT_LLM`, default 10/min), loose on the rest
   (`RISKI_RATE_LIMIT_SEARCH`, default 60/min), 429 + Retry-After *before*
   any work.

The app trusts `X-Forwarded-For` only from `RISKI_TRUSTED_PROXIES`
(default `127.0.0.1`) — the vhost template sets the forwarding headers
accordingly. uvicorn binds loopback only; nothing else should ever reach
the API port.

## Nightly pipeline (change: unified-update-pipeline)

`crontab.example` runs `python src/riskiUpdate.py` (snapshot → sync →
enrich → report) under `flock -n` with exit codes 0/1/2 and mail on 1/2.
Failure semantics: `sync` is critical (stops the run, baseline stays put);
all enrichment phases are best-effort — failed items retry next run
automatically via the per-File stage ledger. Reports land next to the
snapshots (`update_report_*.md` in the snapshot directory).

## Rollout checklist

1. Supervisor: fill placeholders → copy → `supervisorctl reread && update`
   → `supervisorctl status riski-api` → `curl http://127.0.0.1:<port>/health`.
2. Apache: merge the rationale blocks into the real vhost (keep the
   host's TLS/server-name configuration) → `apachectl configtest` →
   reload → smoke checks below.
3. Cron: merge `crontab.example` (placeholders filled) →
   `crontab -l | grep riskiUpdate`.
4. Drift check: diff each host file against its template.

### Smoke checks

```bash
# health through the proxy
curl -s https://<SERVER_NAME>/api/health
# security headers present (HSTS once TLS is on)
curl -sI https://<SERVER_NAME>/api/health | grep -iE 'x-content-type|referrer|strict-transport'
# rate limiting active: hammer /ask past the limit (10/min LLM budget)
# → expect 429 + Retry-After, and no LLM call in the API log for the 429s
# flock overlap: start riskiUpdate twice → second exits immediately with
# "another riskiUpdate run holds the lock"
# first cron run: check the report exists and the exit code was 0
tail <REPO_DIR>/update.log
```
