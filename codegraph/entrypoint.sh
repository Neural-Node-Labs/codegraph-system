#!/bin/sh
set -e

PROJECTS_ROOT="${PROJECTS_ROOT:-/data/projects}"
mkdir -p "$PROJECTS_ROOT"

# Legacy single-repo bootstrap: if REPO_PATH points at a non-empty directory
# and no project has been created yet, seed a "default" project from it so
# existing single-repo setups keep working after upgrading. New setups
# should create/upload projects from the UI or API instead.
if [ -n "$REPO_PATH" ] && [ -d "$REPO_PATH" ] && [ "$(ls -A "$REPO_PATH" 2>/dev/null)" ]; then
  echo "[codegraph] REPO_PATH is set - bootstrapping a default project from it if none exist yet ..."
  python -m app.bootstrap_default_project "$REPO_PATH" || true
fi

echo "[codegraph] Starting API server on :8000 ..."
exec uvicorn app.api:app --host 0.0.0.0 --port 8000
