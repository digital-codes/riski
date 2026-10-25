# Tasks

## 1. Deployment directory

- [ ] 1.1 Create `deploy/riski-api.supervisor.conf`: current command/user/directory plus `stopasgroup=true`, `killasgroup=true`, log rotation settings (`stdout_logfile_maxbytes`, `stdout_logfile_backups`), documented `RISKI_*` env placeholder; rationale comments.
- [ ] 1.2 Create `deploy/apache-riski.conf`: vhost template with TLS, `ProxyPass`/`ProxyPassMatch` to loopback with `retry=0`, `ProxyTimeout 300`, `ProxyPreserveHost On`, `X-Forwarded-For`/`X-Forwarded-Proto`, security headers (HSTS, `X-Content-Type-Options`, `Referrer-Policy`, frame-ancestors), mod_ratelimit/mod_evasive outer-layer block (generous thresholds); rationale comments per block.
- [ ] 1.3 Create `deploy/crontab.example`: nightly `flock -n` entry for `python src/riskiUpdate.py`, log file, mail-on-exit-1/2 wrapper with report path in the body; off-peak non-round schedule; comments referencing `unified-update-pipeline` exit codes.
- [ ] 1.4 Create `deploy/README.md`: capacity model (threadpool / DB pool / LLM as the three limits), single-worker constraint (in-memory sessions; scale-out paths: sticky sessions or stateless tokens), repo→host file mapping table, rollout steps (`supervisorctl reread && update`, `apachectl configtest` + reload, crontab install), smoke checks (`curl -I` header assertions, `/health` via proxy, flock overlap test, report check after first cron run).

## 2. Cleanup & docs

- [ ] 2.1 Remove `riski-api.supervisor.conf` (repo root) and `scripts/restart-api.sh`; README "Setup"/"Usage" updated to reference `deploy/` and `supervisorctl restart riski-api`.
- [ ] 2.2 README deployment section cross-links: capacity → `api-capacity-hardening`, security → `api-security-hardening`, cron contract → `unified-update-pipeline`; `openspec validate --changes` passes.
