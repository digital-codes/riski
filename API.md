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

### Debug trace (request flow) — change: api-debug-logging

Opt-in end-to-end tracing of the API request flow: every incoming query,
intent route decision (with reasons), recall, kg enrichment and the
response sent to the frontend, correlated by request id. Off by default
(no file, no overhead, no behavior change).

- **Activate**: set `RISKI_API_TRACE=1` when starting the service:

  ```bash
  RISKI_API_TRACE=1 /usr/bin/python3 -m uvicorn src.apiServer:app --host 127.0.0.1 --port 11384
  ```

- **Log file**: `log/api_debug.log` at the repo root (gitignored; grows
  only while the flag is set — archive/truncate manually as needed).
- **Entry format**: one JSON object per line —

  ```json
  {"ts": "2026-11-21T10:04:05.123+01:00", "src": "src.pgIntentRouter",
   "req": "ab12cd34ef56", "event": "intent_route", "intent": "ask_decision_date", ...}
  ```

  `ts` = ISO-8601 timestamp, `src` = source module, `req` = request id
  shared by all entries of one HTTP request.
- **Key events**: `http_request` / `http_response` (every request),
  `api_query` (incoming query + params), `intent_route` (intent,
  confidence, top scores, slots), `intent_fallback` (ladder step +
  reason), `thread_turn` (followup-vs-break + reasons),
  `clarification_mode`, `recall` / `recall_done` (query through recall),
  `summarizer`, `kg_related` / `kg_topic_focus` / `kg_followups` /
  `kg_thread` (token prefix only), `api_response` (mode + payload
  counters — never the raw body).
- **Follow one request**: `grep '"req": "<id>"' log/api_debug.log` (the id
  is printed in each line; find one via `grep '"event": "api_query"'`).

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

**Query sanitation** (change: sanitize-queries-and-initial-response):
`/search` and `/ask` accept letters (German umlauts included), digits,
whitespace and common punctuation only, max 250 characters, non-empty.
Violations respond **400** with a German message and run no pipeline
stage — e.g. `"<script>"` → `"Die Suchanfrage enthält unzulässige
Zeichen…"`, a 251-char query → `"…zu lang (maximal 250 Zeichen)…"`,
whitespace-only → `"Die Suchanfrage ist leer."`.

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
`answer_mode` for meeting-centric answers). Location-scoped answers
(`intent: "ask_location"`) additionally carry `location` — the resolved
place(s) `{type, id, name, score}`, `alternates`, and the resolution note
(also mirrored in `fallback_notes` when a location could not be resolved and
the query was answered as an unscoped search). Same staged contract: no
`timeline`/`graph` in the response.

### `POST /timeline` — stage 2 (per session)

Request: `{ "session_id": "hex-session-id" }`
Response: `{ "sessionId": "...", "query": "...", "timeline": [ { "start_date": "...", "end_date": "...", "events": [] } ] }`

### `POST /graph` — stage 3 (per session)

Request: `{ "session_id": "hex-session-id", "scope": "documents" }`

Response: `{ "sessionId": "...", "query": "...", "scope": "documents", "graph": { "nodes": [], "edges": [] }, "geo_available": true, "expandable_types": ["File", "AgendaItem", "Paper", "Meeting", "Consultation"] }`

`scope` (change: disable-organisation-expansion) selects the view:
**`documents`** (default — the traversal seeded by the top_k answer
documents only) or **`full`** (the complete result-list traversal
including agenda-item seed blocks). Both scopes are computed once per
stage-2 run; switching serves the stored graph without re-traversal.
`expandable_types` is the backend-owned list the client derives the
"Nachbarn laden" button state from.

Out-of-order calls are safe: `/graph` computes stage 2 first if it has not
run yet, and a later `/timeline` call returns the already-computed result.

### Unchanged endpoints

- `POST /summarize { session_id, refine?, exclude? }` — LLM summary + per-file metadata (async fill-in). With `refine: true` the context per file is the query-matched chunk (chunk index from the search phase's match metadata; content/teaser fallback — change: fix-result-summarizer)
- `POST /expand { node_id }` — depth-1 graph neighborhood for client-side merge. Node types without adjacency or in the disabled registry (Organisation) respond gracefully with `{ "nodes": [], "edges": [], "expandable": false }` instead of an error
- `GET /geo/{session_id}` — map FeatureCollection (fetch after `/graph`; the map scope is the graph-connected answer set)
- `GET /facets`, `GET /health`, `GET /sessions/{id}` (debug dump)

Sessions are in-memory only: a server restart invalidates `session_id`s.
