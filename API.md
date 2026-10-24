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
