import sqlite3
import os
import re
import secrets
from pathlib import Path

DB_PATH = os.environ.get("CODEGRAPH_DB", "/data/graph.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _needs_migration(conn):
    """True if an old, pre-projects schema (nodes without project_id) is present."""
    cols = conn.execute("PRAGMA table_info(nodes)").fetchall()
    if not cols:
        return False
    return "project_id" not in {c["name"] for c in cols}


def _migrate_legacy_graph_tables(conn):
    """Old installs indexed a single repo with no project scoping. Graph data
    is fully rebuildable from source (it's derived, not authored), so on
    upgrade we drop just the graph tables and let the schema below recreate
    them project-scoped. Users/API keys are left untouched."""
    conn.executescript(
        """
        DROP TABLE IF EXISTS nodes_fts;
        DROP TABLE IF EXISTS edges;
        DROP TABLE IF EXISTS nodes;
        """
    )
    conn.commit()


def init_db(reset: bool = False):
    """Ensure schema exists. `reset` is legacy/unused for destructive resets now -
    use clear_graph() to wipe only graph data while preserving users."""
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = get_conn()
    if _needs_migration(conn):
        _migrate_legacy_graph_tables(conn)
    schema_path = Path(__file__).parent / "schema.sql"
    conn.executescript(schema_path.read_text())
    conn.commit()
    return conn


def clear_graph(conn, project_id=None):
    """Wipe graph data (nodes/edges/FTS index) - never touches users or
    projects. If project_id is given, only that project's graph is cleared;
    otherwise every project's graph is cleared."""
    if project_id is None:
        conn.execute("DELETE FROM edges")
        conn.execute("DELETE FROM nodes")
    else:
        conn.execute("DELETE FROM edges WHERE project_id=?", (project_id,))
        conn.execute("DELETE FROM nodes WHERE project_id=?", (project_id,))
    conn.commit()


def upsert_node(conn, project_id, type_, name, file_path=None, line_start=None, line_end=None,
                 language=None, signature=None, docstring=None):
    cur = conn.execute(
        """SELECT id FROM nodes WHERE project_id=? AND type=? AND name=? AND
           file_path IS ? AND line_start IS ?""",
        (project_id, type_, name, file_path, line_start),
    )
    row = cur.fetchone()
    if row:
        return row["id"]
    cur = conn.execute(
        """INSERT INTO nodes (project_id, type, name, file_path, line_start, line_end, language, signature, docstring)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (project_id, type_, name, file_path, line_start, line_end, language, signature, docstring),
    )
    return cur.lastrowid


def add_edge(conn, project_id, source_id, target_id, type_, resolved, raw_expression=None):
    conn.execute(
        """INSERT INTO edges (project_id, source_id, target_id, type, resolved, raw_expression)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (project_id, source_id, target_id, type_, int(resolved), raw_expression),
    )


# --------------------------- projects ---------------------------

def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "project"


def _unique_slug(conn, base_slug):
    slug = base_slug
    n = 2
    while conn.execute("SELECT 1 FROM projects WHERE slug=?", (slug,)).fetchone():
        slug = f"{base_slug}-{n}"
        n += 1
    return slug


def create_project(conn, name, description=None, created_by=None):
    slug = _unique_slug(conn, slugify(name))
    cur = conn.execute(
        """INSERT INTO projects (name, slug, description, status, created_by)
           VALUES (?, ?, ?, 'empty', ?)""",
        (name, slug, description, created_by),
    )
    conn.commit()
    return cur.lastrowid


def get_project(conn, project_id):
    return conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()


def get_project_by_slug(conn, slug):
    return conn.execute("SELECT * FROM projects WHERE slug=?", (slug,)).fetchone()


def list_projects(conn):
    return conn.execute("SELECT * FROM projects ORDER BY created_at DESC, id DESC").fetchall()


def update_project(conn, project_id, name=None, description=None):
    if name is not None:
        conn.execute("UPDATE projects SET name=? WHERE id=?", (name, project_id))
    if description is not None:
        conn.execute("UPDATE projects SET description=? WHERE id=?", (description, project_id))
    conn.commit()


def set_project_status(conn, project_id, status, last_indexed_at=None, stats_json=None, error=None):
    conn.execute(
        """UPDATE projects SET status=?,
               last_indexed_at=COALESCE(?, last_indexed_at),
               last_index_stats=COALESCE(?, last_index_stats),
               last_error=?
           WHERE id=?""",
        (status, last_indexed_at, stats_json, error, project_id),
    )
    conn.commit()


def delete_project(conn, project_id):
    conn.execute("DELETE FROM edges WHERE project_id=?", (project_id,))
    conn.execute("DELETE FROM nodes WHERE project_id=?", (project_id,))
    conn.execute("DELETE FROM projects WHERE id=?", (project_id,))
    conn.commit()


def project_graph_counts(conn, project_id):
    nodes = conn.execute("SELECT COUNT(*) c FROM nodes WHERE project_id=?", (project_id,)).fetchone()["c"]
    edges = conn.execute("SELECT COUNT(*) c FROM edges WHERE project_id=?", (project_id,)).fetchone()["c"]
    return {"nodes": nodes, "edges": edges}


# --------------------------- users ---------------------------
from app.auth import hash_password, generate_api_key


def create_user(conn, username, password, role="member"):
    pw_hash, salt = hash_password(password)
    api_key = generate_api_key()
    cur = conn.execute(
        """INSERT INTO users (username, password_hash, salt, role, api_key)
           VALUES (?, ?, ?, ?, ?)""",
        (username, pw_hash, salt, role, api_key),
    )
    conn.commit()
    return cur.lastrowid


def get_user_by_username(conn, username):
    return conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()


def get_user_by_api_key(conn, api_key):
    return conn.execute("SELECT * FROM users WHERE api_key=? AND is_active=1", (api_key,)).fetchone()


def get_user_by_id(conn, user_id):
    return conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()


def list_users(conn):
    return conn.execute("SELECT * FROM users ORDER BY id").fetchall()


def update_user(conn, user_id, role=None, is_active=None, password=None):
    if role is not None:
        conn.execute("UPDATE users SET role=? WHERE id=?", (role, user_id))
    if is_active is not None:
        conn.execute("UPDATE users SET is_active=? WHERE id=?", (int(is_active), user_id))
    if password:
        pw_hash, salt = hash_password(password)
        conn.execute("UPDATE users SET password_hash=?, salt=? WHERE id=?", (pw_hash, salt, user_id))
    conn.commit()


def regenerate_api_key(conn, user_id):
    api_key = generate_api_key()
    conn.execute("UPDATE users SET api_key=? WHERE id=?", (api_key, user_id))
    conn.commit()
    return api_key


def delete_user(conn, user_id):
    conn.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()


def seed_admin_if_missing(conn):
    """Create a default admin user on first boot if no users exist yet."""
    count = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
    if count > 0:
        return None
    password = os.environ.get("ADMIN_PASSWORD", "admin123")
    user_id = create_user(conn, "admin", password, role="admin")
    return {"username": "admin", "password": password, "id": user_id}
