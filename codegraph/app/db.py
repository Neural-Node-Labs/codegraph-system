import sqlite3
import os
from pathlib import Path

DB_PATH = os.environ.get("CODEGRAPH_DB", "/data/graph.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(reset: bool = False):
    """Ensure schema exists. `reset` is legacy/unused for destructive resets now -
    use clear_graph() to wipe only graph data while preserving users."""
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = get_conn()
    schema_path = Path(__file__).parent / "schema.sql"
    conn.executescript(schema_path.read_text())
    conn.commit()
    return conn


def clear_graph(conn):
    """Wipe only graph data (nodes/edges/FTS index) - never touches users."""
    conn.execute("DELETE FROM edges")
    conn.execute("DELETE FROM nodes")
    conn.commit()


def upsert_node(conn, type_, name, file_path=None, line_start=None, line_end=None,
                 language=None, signature=None, docstring=None):
    cur = conn.execute(
        """SELECT id FROM nodes WHERE type=? AND name=? AND
           file_path IS ? AND line_start IS ?""",
        (type_, name, file_path, line_start),
    )
    row = cur.fetchone()
    if row:
        return row["id"]
    cur = conn.execute(
        """INSERT INTO nodes (type, name, file_path, line_start, line_end, language, signature, docstring)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (type_, name, file_path, line_start, line_end, language, signature, docstring),
    )
    return cur.lastrowid


def add_edge(conn, source_id, target_id, type_, resolved, raw_expression=None):
    conn.execute(
        """INSERT INTO edges (source_id, target_id, type, resolved, raw_expression)
           VALUES (?, ?, ?, ?, ?)""",
        (source_id, target_id, type_, int(resolved), raw_expression),
    )


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
