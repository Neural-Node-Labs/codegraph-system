"""
Backward-compat bootstrap for pre-multi-project deployments.

Older versions of codegraph indexed a single repo pointed at by REPO_PATH.
On upgrade, if REPO_PATH is set and no project exists yet, this copies that
repo's contents into a "default" project directory and indexes it, so
existing docker-compose setups keep working without manual steps. New
projects should be created and populated via the UI/API instead.
"""
import shutil
import sys
from pathlib import Path

from app.db import get_conn, init_db, create_project, list_projects, set_project_status
from app.indexer import index_repo
from app.api import PROJECTS_ROOT, now_iso
import json


def main(repo_path: str):
    conn = init_db()
    if list_projects(conn):
        print("[codegraph] Projects already exist - skipping default-project bootstrap.")
        conn.close()
        return

    project_id = create_project(conn, "default", "Bootstrapped from REPO_PATH", created_by=None)
    from app.db import get_project
    p = get_project(conn, project_id)
    dest = PROJECTS_ROOT / p["slug"]
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copytree(repo_path, dest, dirs_exist_ok=True)

    stats = index_repo(project_id, str(dest), reset=True)
    set_project_status(conn, project_id, status="ready", last_indexed_at=now_iso(), stats_json=json.dumps(stats))
    conn.close()
    print(f"[codegraph] Bootstrapped default project from {repo_path}: {stats}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/repo")
