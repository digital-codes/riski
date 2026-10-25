# RISKI API

The backend API runs as a FastAPI app served by uvicorn. Apache proxies `/api/` to the backend on port 11384.

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

## Endpoints (staged search contract)

> change: progressive-frontend-rendering — `/search` and `/ask` return the
> **recall stage only** (no timeline, no graph). The timeline and graph are
> fetched per session via `POST /timeline` and `POST /graph`, so clients can
> render the file list immediately and fill panes in as stages complete.

### `POST /search` — stage 1 (recall)

Request:

```json
{ "query": "Digitalstrategie Karlsruhe", "top_k": 5, "filters": null, "signals": null, "summarize": false }
```

Response (recall only — no `timeline`, no `graph`):

```json
{
  "query": "Digitalstrategie Karlsruhe",
  "top_files": [{ "oparlKey": "635289", "name": "...", "fileName": "...", "downloadurl": "...", "distance": 0.12, "match": { }, "...": "..." }],
  "matched_entities": [],
  "facets": { "paperType": {} },
  "applied_filters": [],
  "sessionId": "hex-session-id"
}
```

With `summarize: true` the LLM summary runs inline (non-interactive
consumers); the web app leaves it `false` and calls `POST /summarize`.

### `POST /ask` — stage 1 with intent routing

Same request shape as `/search` plus optional `session_id`; the response adds
`intent`, `slots`, `applied_filters`, `fallback_notes` (and `topics` /
`answer_mode` for meeting-centric answers). Same staged contract: no
`timeline`/`graph` in the response.

### `POST /timeline` — stage 2 (per session)

Request: `{ "session_id": "hex-session-id" }`
Response: `{ "sessionId": "...", "query": "...", "timeline": [ { "start_date": "...", "end_date": "...", "events": [] } ] }`

### `POST /graph` — stage 3 (per session)

Request: `{ "session_id": "hex-session-id" }`
Response: `{ "sessionId": "...", "query": "...", "graph": { "nodes": [], "edges": [] }, "geo_available": true }`

Out-of-order calls are safe: `/graph` computes stage 2 first if it has not
run yet, and a later `/timeline` call returns the already-computed result.

### Unchanged endpoints

- `POST /summarize { session_id, refine?, exclude? }` — LLM summary + per-file metadata (async fill-in)
- `POST /expand { node_id }` — depth-1 graph neighborhood for client-side merge
- `GET /geo/{session_id}` — map FeatureCollection (fetch after `/graph`; the map scope is the graph-connected answer set)
- `GET /facets`, `GET /health`, `GET /sessions/{id}` (debug dump)

Sessions are in-memory only: a server restart invalidates `session_id`s.
