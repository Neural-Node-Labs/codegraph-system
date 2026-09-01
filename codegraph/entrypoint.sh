#!/bin/sh
set -e

REPO_PATH="${REPO_PATH:-/repo}"
REINDEX="${REINDEX:-true}"

if [ "$REINDEX" = "true" ]; then
  echo "[codegraph] Indexing repo at $REPO_PATH ..."
  python -m app.indexer "$REPO_PATH"
else
  echo "[codegraph] Skipping re-index (REINDEX=false), using existing DB."
fi

echo "[codegraph] Starting API server on :8000 ..."
exec uvicorn app.api:app --host 0.0.0.0 --port 8000
