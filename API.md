# RISKI API

The backend API runs as a FastAPI app served by uvicorn. Apache proxies `/api/` to the backend on port 11384.

## API behaviour notes (api-capacity-hardening)

- **`POST /search` defaults `summarize=false`** (breaking change, 2026-10-25):
  the query-guided LLM summary is produced by the async `POST /summarize`
  follow-up (returns the same contract, plus `summary`/`files`). Pass
  `"summarize": true` explicitly for the old inline behaviour — non-interactive
  consumers only; each inline summary pins a worker thread + LLM slot for
  10–90 s.
- **Pool saturation degrades gracefully**: when the recall fan-out budget
  (`RISKI_FANOUT_BUDGET`, default 24 permits) or the DB pool
  (`RISKI_DB_POOL_SIZE`/`RISKI_DB_MAX_OVERFLOW`, default 16+8) is exhausted
  within `RISKI_DB_POOL_TIMEOUT` (default 30 s), `/search` and `/ask`
  respond **503 + `Retry-After: 5`** instead of an opaque 500.
- **Sessions are bounded**: in-memory sessions expire after
  `RISKI_SESSION_TTL` (default 2 h); the store is capped at
  `RISKI_SESSION_MAX` (default 1000, oldest evicted). Unknown/expired
  session ids → 404 — clients should re-run the search.
- **Single worker is the supported deployment**: sessions are in-memory, so
  multiple uvicorn workers behind a round-robin proxy break `/geo`,
  `/summarize` and `/sessions` (404s). Scale-out paths when ever needed:
  sticky sessions at the proxy, or stateless session tokens.
- Capacity model: the three limits are the anyio worker threadpool (40
  threads), the DB pool (24 connections), and the LLM endpoint throughput.

## Security controls (api-security-hardening)

The API is anonymous and inference-expensive; the controls bound what one
client can inflict:

- **Rate limiting (sliding window, per client)**: `/ask` and `/summarize`
  share the tight `llm` budget (`RISKI_RATE_LIMIT_LLM`, default 10/min);
  `/search?summarize=true` enforces the same budget *before* any database
  or LLM work; plain search/expand/facets/geo share the looser `search`
  budget (`RISKI_RATE_LIMIT_SEARCH`, default 60/min). `/health` is never
  limited. Exceeding a budget → **429 + `Retry-After`**.
- **Client identity**: socket address, or the last `X-Forwarded-For` hop
  when the peer is a trusted proxy (`RISKI_TRUSTED_PROXIES`, default
  `127.0.0.1`). Spoofed headers from non-proxy peers are ignored. The
  limiter is in-process (single-worker deployment) and resets on restart.
- **Input bounds**: `query` ≤ 512 chars, `filters` ≤ 20 items,
  `exclude` ≤ 100 items — oversized input → 422 before any processing.
- **Sanitized errors**: client-facing failure bodies carry generic text
  plus a `correlation_id`; the full exception goes to the log only.
- **CORS**: dev origins by default; set `RISKI_CORS_ORIGINS`
  (comma-separated) for split deployments. Same-origin production behind
  apache needs no CORS.

## Current Setup

- **Host/Port**: `127.0.0.1:11384`
- **App**: `src.apiServer:app`
- **Working Directory**: `/home/okl/projects/riski`
- **Apache Config**: `/etc/apache2/sites-available/riski.conf` (proxies `/api/` → `http://localhost:11384/`)

## Starting/Restarting

### Quick script (recommended)

After making code changes, restart with:

```bash
./scripts/restart-api.sh
```

The script will:
1. Kill any existing uvicorn process for `src.apiServer:app` on port 11384
2. Start a new instance in the background with `setsid`
3. Log to `apiServer.log` in the repo root
4. Check health at `/health`

### Manual restart

```bash
pkill -f "uvicorn src.apiServer:app.*11384"
cd /home/okl/projects/riski
setsid /usr/bin/python3 -m uvicorn src.apiServer:app --host 127.0.0.1 --port 11384 </dev/null > apiServer.log 2>&1 &
sleep 2 && curl http://127.0.0.1:11384/health
```

### Development with auto-reload

For active development, use `--reload` to automatically restart on file changes:

```bash
pkill -f "uvicorn src.apiServer:app.*11384"
cd /home/okl/projects/riski
setsid /usr/bin/python3 -m uvicorn src.apiServer:app --host 127.0.0.1 --port 11384 --reload </dev/null > apiServer.log 2>&1 &
```

## Monitoring

- **Logs**: `tail -f /home/okl/projects/riski/apiServer.log`
- **Health check**: `curl http://127.0.0.1:11384/health`
- **Process**: `ps aux | grep "[u]vicorn.*11384"`

## Supervisor (optional, for system management)

A supervisor config is available at `riski-api.supervisor.conf`. If copied to `/etc/supervisor/conf.d/riski-api.conf` (requires sudo):

```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl restart riski-api
sudo supervisorctl status
```
