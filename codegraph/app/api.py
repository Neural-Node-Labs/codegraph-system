"""
Read-only query API over the dependency graph, plus auth, user administration,
and a mapping-refresh endpoint. Graph data is never generated or inferred -
it only returns structured facts already extracted by the indexer. LLMs
consume this via HTTP (or the companion MCP server) to explore a codebase
without needing the whole repo dumped into context.
"""
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Depends, Header
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.db import (
    get_conn, init_db, seed_admin_if_missing, create_user, get_user_by_username,
    get_user_by_api_key, get_user_by_id, list_users, update_user,
    regenerate_api_key, delete_user,
)
from app.auth import verify_password, create_token, verify_token
from app.indexer import index_repo

app = FastAPI(title="Codegraph API", version="1.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).parent / "static"
REPO_PATH = os.environ.get("REPO_PATH", "/repo")


@app.on_event("startup")
def on_startup():
    conn = init_db()
    seeded = seed_admin_if_missing(conn)
    conn.close()
    if seeded:
        print("=" * 60)
        print(" First boot: created default admin user")
        print(f"   username: {seeded['username']}")
        print(f"   password: {seeded['password']}")
        print(" Change this password after logging in.")
        print("=" * 60)


def node_to_dict(row):
    return dict(row) if row else None


# --------------------------- auth dependencies ---------------------------

def get_current_user(
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None),
):
    """Accepts either a Bearer JWT-alike token (browser UI) or an X-API-Key
    header (agents / MCP server / scripts)."""
    conn = get_conn()
    try:
        if x_api_key:
            user = get_user_by_api_key(conn, x_api_key)
            if not user:
                raise HTTPException(401, "invalid API key")
            return dict(user)
        if authorization and authorization.startswith("Bearer "):
            token = authorization.split(" ", 1)[1]
            payload = verify_token(token)
            if not payload:
                raise HTTPException(401, "invalid or expired token")
            user = get_user_by_id(conn, payload["uid"])
            if not user or not user["is_active"]:
                raise HTTPException(401, "user not found or inactive")
            return dict(user)
        raise HTTPException(401, "missing credentials")
    finally:
        conn.close()


def require_admin(user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "admin role required")
    return user


def public_user_dict(u):
    return {"id": u["id"], "username": u["username"], "role": u["role"],
            "is_active": bool(u["is_active"]), "created_at": u["created_at"],
            "api_key": u["api_key"]}


@app.get("/")
def root():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# --------------------------- auth endpoints ---------------------------

class LoginRequest(BaseModel):
    username: str
    password: str


@app.post("/api/auth/login")
def login(body: LoginRequest):
    conn = get_conn()
    user = get_user_by_username(conn, body.username)
    conn.close()
    if not user or not user["is_active"] or not verify_password(body.password, user["salt"], user["password_hash"]):
        raise HTTPException(401, "invalid username or password")
    token = create_token(user["id"], user["username"], user["role"])
    return {"token": token, "user": public_user_dict(user)}


@app.get("/api/auth/me")
def me(user=Depends(get_current_user)):
    return public_user_dict(user)


# --------------------------- admin: user management ---------------------------

class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str = "member"


class UpdateUserRequest(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None


@app.get("/api/admin/users")
def admin_list_users(admin=Depends(require_admin)):
    conn = get_conn()
    users = list_users(conn)
    conn.close()
    return {"results": [public_user_dict(u) for u in users]}


@app.post("/api/admin/users")
def admin_create_user(body: CreateUserRequest, admin=Depends(require_admin)):
    if body.role not in ("admin", "member"):
        raise HTTPException(400, "role must be 'admin' or 'member'")
    conn = get_conn()
    try:
        user_id = create_user(conn, body.username, body.password, body.role)
    except Exception:
        raise HTTPException(409, "username already exists")
    finally:
        conn.close()
    conn = get_conn()
    user = get_user_by_id(conn, user_id)
    conn.close()
    return public_user_dict(user)


@app.patch("/api/admin/users/{user_id}")
def admin_update_user(user_id: int, body: UpdateUserRequest, admin=Depends(require_admin)):
    conn = get_conn()
    if not get_user_by_id(conn, user_id):
        conn.close()
        raise HTTPException(404, "user not found")
    if body.role is not None and body.role not in ("admin", "member"):
        conn.close()
        raise HTTPException(400, "role must be 'admin' or 'member'")
    update_user(conn, user_id, role=body.role, is_active=body.is_active, password=body.password)
    user = get_user_by_id(conn, user_id)
    conn.close()
    return public_user_dict(user)


@app.post("/api/admin/users/{user_id}/regenerate-key")
def admin_regenerate_key(user_id: int, admin=Depends(require_admin)):
    conn = get_conn()
    if not get_user_by_id(conn, user_id):
        conn.close()
        raise HTTPException(404, "user not found")
    api_key = regenerate_api_key(conn, user_id)
    conn.close()
    return {"id": user_id, "api_key": api_key}


@app.delete("/api/admin/users/{user_id}")
def admin_delete_user(user_id: int, admin=Depends(require_admin)):
    if user_id == admin["id"]:
        raise HTTPException(400, "cannot delete your own account")
    conn = get_conn()
    if not get_user_by_id(conn, user_id):
        conn.close()
        raise HTTPException(404, "user not found")
    delete_user(conn, user_id)
    conn.close()
    return {"deleted": True, "id": user_id}


# --------------------------- refresh mapping ---------------------------

@app.post("/api/refresh")
def refresh_mapping(user=Depends(get_current_user)):
    """Re-run static analysis over REPO_PATH and rebuild the graph. Blocking
    call - returns once the new graph is written."""
    stats = index_repo(REPO_PATH, reset=True)
    return {"status": "ok", "triggered_by": user["username"], **stats}


# --------------------------- graph query endpoints (auth required) ---------------------------

@app.get("/api/search")
def search(q: str = Query(..., min_length=1), limit: int = 25, user=Depends(get_current_user)):
    conn = get_conn()
    rows = conn.execute(
        """SELECT nodes.* FROM nodes_fts
           JOIN nodes ON nodes.id = nodes_fts.rowid
           WHERE nodes_fts MATCH ?
           LIMIT ?""",
        (q + "*", limit),
    ).fetchall()
    conn.close()
    return {"query": q, "results": [node_to_dict(r) for r in rows]}


@app.get("/api/nodes/{node_id}")
def get_node(node_id: int, user=Depends(get_current_user)):
    conn = get_conn()
    row = conn.execute("SELECT * FROM nodes WHERE id=?", (node_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "node not found")
    return node_to_dict(row)


@app.get("/api/nodes")
def list_nodes(type: Optional[str] = None, file_path: Optional[str] = None, limit: int = 100, user=Depends(get_current_user)):
    conn = get_conn()
    q = "SELECT * FROM nodes WHERE 1=1"
    params = []
    if type:
        q += " AND type=?"
        params.append(type)
    if file_path:
        q += " AND file_path=?"
        params.append(file_path)
    q += " LIMIT ?"
    params.append(limit)
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return {"results": [node_to_dict(r) for r in rows]}


@app.get("/api/edges")
def list_edges(
    type: Optional[str] = None,
    resolved: Optional[bool] = None,
    q: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
    user=Depends(get_current_user),
):
    """Flat, filterable listing of every edge with source/target names joined
    in - built for a tabular 'inspect every relation' UI view."""
    conn = get_conn()
    sql = """
        SELECT edges.id, edges.type, edges.resolved, edges.raw_expression,
               src.id as source_id, src.name as source_name, src.type as source_type, src.file_path as source_file,
               tgt.id as target_id, tgt.name as target_name, tgt.type as target_type, tgt.file_path as target_file
        FROM edges
        LEFT JOIN nodes src ON src.id = edges.source_id
        LEFT JOIN nodes tgt ON tgt.id = edges.target_id
        WHERE 1=1
    """
    params = []
    if type:
        sql += " AND edges.type=?"
        params.append(type)
    if resolved is not None:
        sql += " AND edges.resolved=?"
        params.append(int(resolved))
    if q:
        sql += " AND (src.name LIKE ? OR tgt.name LIKE ? OR edges.raw_expression LIKE ?)"
        like = f"%{q}%"
        params.extend([like, like, like])
    count_sql = f"SELECT COUNT(*) c FROM ({sql})"
    total = conn.execute(count_sql, params).fetchone()["c"]
    sql += " ORDER BY edges.id LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return {"total": total, "results": [dict(r) for r in rows]}


def _traverse(conn, node_id, direction, depth, seen=None):
    """direction: 'out' (dependencies) or 'in' (dependents)"""
    if seen is None:
        seen = set()
    if node_id in seen or depth < 0:
        return {}
    seen.add(node_id)
    if direction == "out":
        rows = conn.execute(
            "SELECT * FROM edges WHERE source_id=? AND resolved=1", (node_id,)
        ).fetchall()
        key_field = "target_id"
    else:
        rows = conn.execute(
            "SELECT * FROM edges WHERE target_id=? AND resolved=1", (node_id,)
        ).fetchall()
        key_field = "source_id"

    children = []
    for r in rows:
        other_id = r[key_field]
        if other_id is None:
            continue
        node = conn.execute("SELECT * FROM nodes WHERE id=?", (other_id,)).fetchone()
        entry = {"edge_type": r["type"], "node": node_to_dict(node)}
        if depth > 0:
            entry["children"] = _traverse(conn, other_id, direction, depth - 1, seen)
        children.append(entry)
    return children


@app.get("/api/nodes/{node_id}/dependencies")
def get_dependencies(node_id: int, depth: int = 1, user=Depends(get_current_user)):
    conn = get_conn()
    if not conn.execute("SELECT 1 FROM nodes WHERE id=?", (node_id,)).fetchone():
        conn.close()
        raise HTTPException(404, "node not found")
    result = _traverse(conn, node_id, "out", depth)
    conn.close()
    return {"node_id": node_id, "depth": depth, "dependencies": result}


@app.get("/api/nodes/{node_id}/dependents")
def get_dependents(node_id: int, depth: int = 1, user=Depends(get_current_user)):
    conn = get_conn()
    if not conn.execute("SELECT 1 FROM nodes WHERE id=?", (node_id,)).fetchone():
        conn.close()
        raise HTTPException(404, "node not found")
    result = _traverse(conn, node_id, "in", depth)
    conn.close()
    return {"node_id": node_id, "depth": depth, "dependents": result}


@app.get("/api/nodes/{node_id}/impact")
def impact_of_change(node_id: int, depth: int = 2, user=Depends(get_current_user)):
    """Everything that could be affected by changing this node: dependents,
    plus any routes/config reachable through them."""
    conn = get_conn()
    if not conn.execute("SELECT 1 FROM nodes WHERE id=?", (node_id,)).fetchone():
        conn.close()
        raise HTTPException(404, "node not found")
    dependents = _traverse(conn, node_id, "in", depth)
    conn.close()
    return {"node_id": node_id, "depth": depth, "impacted_by": dependents}


@app.get("/api/path")
def find_path(source: int, target: int, max_depth: int = 6, user=Depends(get_current_user)):
    conn = get_conn()
    frontier = [(source, [source])]
    visited = {source}
    while frontier:
        next_frontier = []
        for node_id, path in frontier:
            if node_id == target:
                conn.close()
                return {"path_found": True, "path": path}
            if len(path) > max_depth:
                continue
            rows = conn.execute(
                "SELECT target_id FROM edges WHERE source_id=? AND resolved=1 AND target_id IS NOT NULL",
                (node_id,),
            ).fetchall()
            for r in rows:
                tid = r["target_id"]
                if tid not in visited:
                    visited.add(tid)
                    next_frontier.append((tid, path + [tid]))
        frontier = next_frontier
    conn.close()
    return {"path_found": False, "path": []}


@app.get("/api/unresolved")
def list_unresolved(limit: int = 100, user=Depends(get_current_user)):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM edges WHERE resolved=0 LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return {"count": len(rows), "unresolved_edges": [dict(r) for r in rows]}


@app.get("/api/graph")
def full_graph(type: Optional[str] = None, user=Depends(get_current_user)):
    """Full graph as {nodes, edges} for visualization."""
    conn = get_conn()
    if type:
        nodes = conn.execute("SELECT * FROM nodes WHERE type=?", (type,)).fetchall()
    else:
        nodes = conn.execute("SELECT * FROM nodes").fetchall()
    edges = conn.execute("SELECT * FROM edges WHERE resolved=1").fetchall()
    conn.close()
    node_ids = {n["id"] for n in nodes}
    return {
        "nodes": [node_to_dict(n) for n in nodes],
        "edges": [dict(e) for e in edges if e["source_id"] in node_ids and e["target_id"] in node_ids],
    }


@app.get("/api/stats")
def stats(user=Depends(get_current_user)):
    conn = get_conn()
    node_counts = conn.execute("SELECT type, COUNT(*) c FROM nodes GROUP BY type").fetchall()
    edge_counts = conn.execute("SELECT type, COUNT(*) c FROM edges GROUP BY type").fetchall()
    unresolved = conn.execute("SELECT COUNT(*) c FROM edges WHERE resolved=0").fetchone()["c"]
    conn.close()
    return {
        "nodes_by_type": {r["type"]: r["c"] for r in node_counts},
        "edges_by_type": {r["type"]: r["c"] for r in edge_counts},
        "unresolved_edges": unresolved,
    }
