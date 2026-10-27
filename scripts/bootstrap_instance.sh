#!/usr/bin/env bash
# Bootstrap a second RISKI instance end-to-end (change:
# instance-agnostic-config).
#
# Reads the instance configuration (RISKI_INSTANCE_CONFIG, default
# config/instance.yaml) plus the database settings from the environment
# (DB_NAME/DB_USER/DB_PWD/DB_HOST or POSTGRES_URL — env always wins over
# src/private.py). Every step is idempotent; re-running continues where
# the last run stopped.
#
# NOTE: a second instance MUST use its own database name and its own
# download folders (paths.* in the instance config) — never share either
# with another instance. Example for a Dresden test instance:
#   export RISKI_INSTANCE_CONFIG=/path/to/dresden-instance.yaml
#   export DB_NAME=riski_dresden DB_USER=riski DB_PWD=...
#   export RISKI_OPARL__SYSTEM_URL=https://oparl.dresden.de/system
#
# Usage: scripts/bootstrap_instance.sh [--dry-run]

set -euo pipefail

DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

run() {
  echo "+ $*"
  if [[ "$DRY_RUN" == "1" ]]; then return 0; fi
  "$@"
}

# --- settings (instance config + env; the loader resolves precedence) -----
read_config() {
  python3 - "$1" <<'EOF'
import sys
from src.instanceConfig import get_instance_config

cfg = get_instance_config()
section, key = sys.argv[1].split(".", 1)
value = cfg.get(section, {}).get(key)
print("" if value is None else value)
EOF
}

SYSTEM_URL=$(read_config oparl.system_url)
JSON_DIR=$(read_config paths.json_dir)
PDF_DIR=$(read_config paths.pdf_dir)
EXTRACTED_DIR=$(read_config paths.extracted_dir)
SUMS_DIR=$(read_config paths.sums_dir)
DB_NAME="${DB_NAME:-$(python3 -c 'import src.db; print(src.db.DB_NAME)')}"

echo "== RISKI instance bootstrap"
echo "   config file : ${RISKI_INSTANCE_CONFIG:-config/instance.yaml (default)}"
echo "   OParl system: $SYSTEM_URL"
echo "   database    : $DB_NAME"
echo "   json dir    : $JSON_DIR"

# --- 1) database + schema --------------------------------------------------
if [[ "$DRY_RUN" != "1" ]]; then
  echo "== [1/6] database $DB_NAME (created only if missing; needs a role with CREATEDB or superuser once)"
  PGPASSWORD="${DB_PWD:-}" psql -h "${DB_HOST:-localhost}" -U "${DB_USER:-riski}" -d postgres \
    -tc "SELECT 1 FROM pg_database WHERE datname = '$DB_NAME'" | grep -q 1 || \
    PGPASSWORD="${DB_PWD:-}" psql -h "${DB_HOST:-localhost}" -U "${DB_USER:-riski}" -d postgres \
    -c "CREATE DATABASE \"$DB_NAME\";" || true
  # connectivity check with the exact credentials the app will use; a
  # failure here is almost always the server's pg_hba.conf (host-based
  # auth) not covering the new database name — server-admin task, one
  # rule per database (or one rule for the role: "host all <role> ...")
  if ! PGPASSWORD="${DB_PWD:-}" psql -h "${DB_HOST:-localhost}" -U "${DB_USER:-riski}" -d "$DB_NAME" \
       -tc "SELECT 1" >/dev/null 2>&1; then
    echo "ERROR: cannot connect to database '$DB_NAME' as '${DB_USER:-riski}'." >&2
    echo "The PostgreSQL server's pg_hba.conf does not accept this (role, database) pair" >&2
    echo "over TCP — add a host rule for the new database (or widen the existing rule to" >&2
    echo "'host all ${DB_USER:-riski} ...') and reload the server, then re-run this script." >&2
    exit 1
  fi
fi

# --- 2) crawl + import ------------------------------------------------------
echo "== [2/6] crawl + import (syncIncremental; env/CLI overrides apply)"
run python3 src/syncIncremental.py

# --- 3) OCR + chunked embeddings -------------------------------------------
echo "== [3/6] OCR + chunks (pgOcr writes $EXTRACTED_DIR; pgChunks embeds oversized docs)"
run python3 src/pgOcr.py --pdf-dir "$PDF_DIR" --out-dir "$EXTRACTED_DIR"
run python3 src/pgChunks.py -d "$EXTRACTED_DIR"

# --- 4) summaries + file contents + embeddings ------------------------------
echo "== [4/6] summaries + contents + embeddings"
run python3 src/pgSummarize.py --src-dir "$EXTRACTED_DIR" --dst-dir "$SUMS_DIR"
run python3 src/pgAddSummaries.py -s "$SUMS_DIR" -f "$EXTRACTED_DIR" --embed-missing

# --- 5) geo: streets/districts from the configured sources + references -----
echo "== [5/6] geo enrichment (sources from the instance config)"
STREETS_FILE=$(read_config geo.streets_file)
DISTRICTS_FILE=$(read_config geo.districts_file)
run python3 src/pgAddStreets.py -i "$STREETS_FILE"
run python3 src/pgAddDistricts.py -i "$DISTRICTS_FILE"
run python3 src/pgAddStreetRefs.py
run python3 src/pgAddDistrictRefs.py
run python3 src/pgAddFileGeoRefs.py
run python3 src/pgGeoGateCleanup.py

# --- 6) tags, coverage, serve ------------------------------------------------
echo "== [6/6] tags + coverage + API"
run python3 src/pgCategorise.py all
run python3 src/pgTeasers.py
run python3 src/pgCoverage.py

echo "== done. Start the API with:"
echo "   DB_NAME=$DB_NAME uvicorn src.apiServer:app --port 8000"
