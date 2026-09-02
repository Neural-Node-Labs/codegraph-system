"""
Read-only query API over the dependency graph, plus auth, user administration,
project management (create/update/delete projects, upload+unzip source, and
trigger indexing), and graph query endpoints. Graph data is never generated
or inferred - it only returns structured facts already extracted by the
indexer. LLMs consume this via HTTP (or the companion MCP server) to explore
a codebase without needing the whole repo dumped into context.
"""
import os
import json
import shutil
import zipfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Depends, Header, UploadFile, File, Form
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.db import (
    get_conn, init_db, seed_admin_if_missing, create_user, get_user_by_username,
    get_user_by_api_key, get_user_by_id, list_users, update_user,
    regenerate_api_key, delete_user,
    create_project, get_project, list_projects, update_project, delete_project,
    set_project_status, project_graph_counts,
)
from app.auth import verify_password, create_token, verify_token
from app.indexer import index_repo

app = FastAPI(title="Codegraph API", version="1.2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).parent / "static"
PROJECTS_ROOT = Path(os.environ.get("PROJECTS_ROOT", "/data/projects"))
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", 200 * 1024 * 1024))  # 200MB default


@app.on_event("startup")
def on_startup():
    conn = init_db()
    seeded = seed_admin_if_missing(conn)
    conn.close()
    PROJECTS_ROOT.mkdir(parents=True, exist_ok=True)
    if seeded:
        print("=" * 60)
        print(" First boot: created default admin user")
        print(f"   username: {seeded['username']}")
        print(f"   password: {seeded['password']}")
        print(" Change this password after logging in.")
        print("=" * 60)


def node_to_dict(row):
    return dict(row) if row else None


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


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


# --------------------------- projects ---------------------------

def project_dir(slug: str) -> Path:
    return PROJECTS_ROOT / slug


def project_to_dict(p, conn):
    counts = project_graph_counts(conn, p["id"])
    d = p["last_index_stats"]
    return {
        "id": p["id"],
        "name": p["name"],
        "slug": p["slug"],
        "description": p["description"],
        "status": p["status"],
        "last_indexed_at": p["last_indexed_at"],
        "last_index_stats": json.loads(d) if d else None,
        "last_error": p["last_error"],
        "created_at": p["created_at"],
        "node_count": counts["nodes"],
        "edge_count": counts["edges"],
    }


def _get_project_or_404(conn, project_id):
    p = get_project(conn, project_id)
    if not p:
        conn.close()
        raise HTTPException(404, "project not found")
    return p


class CreateProjectRequest(BaseModel):
    name: str
    description: Optional[str] = None


class UpdateProjectRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


@app.get("/api/projects")
def api_list_projects(user=Depends(get_current_user)):
    conn = get_conn()
    projects = list_projects(conn)
    result = [project_to_dict(p, conn) for p in projects]
    conn.close()
    return {"results": result}


@app.post("/api/projects")
def api_create_project(body: CreateProjectRequest, admin=Depends(require_admin)):
    if not body.name.strip():
        raise HTTPException(400, "name is required")
    conn = get_conn()
    project_id = create_project(conn, body.name.strip(), body.description, created_by=admin["id"])
    p = get_project(conn, project_id)
    project_dir(p["slug"]).mkdir(parents=True, exist_ok=True)
    result = project_to_dict(p, conn)
    conn.close()
    return result


@app.get("/api/projects/{project_id}")
def api_get_project(project_id: int, user=Depends(get_current_user)):
    conn = get_conn()
    p = _get_project_or_404(conn, project_id)
    result = project_to_dict(p, conn)
    conn.close()
    return result


@app.patch("/api/projects/{project_id}")
def api_update_project(project_id: int, body: UpdateProjectRequest, admin=Depends(require_admin)):
    conn = get_conn()
    _get_project_or_404(conn, project_id)
    if body.name is not None and not body.name.strip():
        conn.close()
        raise HTTPException(400, "name cannot be empty")
    update_project(conn, project_id, name=(body.name.strip() if body.name is not None else None),
                    description=body.description)
    p = get_project(conn, project_id)
    result = project_to_dict(p, conn)
    conn.close()
    return result


@app.delete("/api/projects/{project_id}")
def api_delete_project(project_id: int, admin=Depends(require_admin)):
    conn = get_conn()
    p = _get_project_or_404(conn, project_id)
    slug = p["slug"]
    delete_project(conn, project_id)
    conn.close()
    d = project_dir(slug)
    if d.exists() and d.is_dir() and d.resolve().parent == PROJECTS_ROOT.resolve():
        shutil.rmtree(d, ignore_errors=True)
    return {"deleted": True, "id": project_id}


def _safe_extract_zip(zip_path: Path, dest_dir: Path):
    """Extract a zip file into dest_dir, guarding against zip-slip (entries
    that try to escape dest_dir via '..' or absolute paths) and zip bombs
    (total uncompressed size cap)."""
    dest_resolved = dest_dir.resolve()
    total_uncompressed = 0
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            total_uncompressed += info.file_size
            if total_uncompressed > MAX_UPLOAD_BYTES:
                raise HTTPException(400, "zip contents exceed the allowed uncompressed size limit")
            target = (dest_dir / info.filename).resolve()
            if target != dest_resolved and dest_resolved not in target.parents:
                raise HTTPException(400, f"unsafe path in zip: {info.filename}")
        # A common pattern: the zip wraps everything in one top-level folder
        # (e.g. "myrepo-main/"). If every entry shares that prefix, unwrap it
        # so the project directory holds the repo contents directly.
        names = [i.filename for i in zf.infolist() if not i.is_dir()]
        top_levels = {n.split("/", 1)[0] for n in names if "/" in n}
        unwrap_prefix = None
        if names and len(top_levels) == 1 and all(n.startswith(next(iter(top_levels)) + "/") for n in names):
            unwrap_prefix = next(iter(top_levels)) + "/"

        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename
            if unwrap_prefix and name.startswith(unwrap_prefix):
                name = name[len(unwrap_prefix):]
            if not name:
                continue
            target = (dest_dir / name).resolve()
            if target != dest_resolved and dest_resolved not in target.parents:
                raise HTTPException(400, f"unsafe path in zip: {info.filename}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)


@app.post("/api/projects/{project_id}/upload")
async def api_upload_project_zip(
    project_id: int,
    file: UploadFile = File(...),
    replace: bool = Form(True),
    admin=Depends(require_admin),
):
    """Upload a .zip of a codebase; it is extracted into the project's
    directory on disk. By default this replaces any existing contents for
    the project (set replace=false to merge/overwrite on top instead)."""
    if not file.filename.lower().endswith(".zip"):
        raise HTTPException(400, "only .zip files are accepted")

    conn = get_conn()
    p = _get_project_or_404(conn, project_id)
    slug = p["slug"]
    conn.close()

    dest = project_dir(slug)
    dest.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        tmp_path = Path(tmp.name)
        size = 0
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                tmp_path.unlink(missing_ok=True)
                raise HTTPException(400, f"upload exceeds max size of {MAX_UPLOAD_BYTES} bytes")
            tmp.write(chunk)

    try:
        if not zipfile.is_zipfile(tmp_path):
            raise HTTPException(400, "uploaded file is not a valid zip archive")
        if replace:
            for child in dest.iterdir():
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
                else:
                    child.unlink(missing_ok=True)
        _safe_extract_zip(tmp_path, dest)
    finally:
        tmp_path.unlink(missing_ok=True)

    file_count = sum(1 for _ in dest.rglob("*") if _.is_file())
    conn = get_conn()
    set_project_status(conn, project_id, status="ready" if file_count else "empty")
    p = get_project(conn, project_id)
    result = project_to_dict(p, conn)
    conn.close()
    return {"status": "ok", "extracted_files": file_count, "project": result}


@app.post("/api/projects/{project_id}/index")
def api_index_project(project_id: int, user=Depends(get_current_user)):
    """Re-run static analysis over this project's source directory and
    rebuild its slice of the graph. Blocking call - returns once the new
    graph is written."""
    conn = get_conn()
    p = _get_project_or_404(conn, project_id)
    slug = p["slug"]
    conn.close()

    src = project_dir(slug)
    if not src.exists() or not any(src.iterdir()):
        raise HTTPException(400, "project has no source yet - upload a zip first")

    conn = get_conn()
    set_project_status(conn, project_id, status="indexing")
    conn.close()

    try:
        stats = index_repo(project_id, str(src), reset=True)
    except Exception as e:
        conn = get_conn()
        set_project_status(conn, project_id, status="error", error=str(e))
        conn.close()
        raise HTTPException(500, f"indexing failed: {e}")

    conn = get_conn()
    set_project_status(conn, project_id, status="ready", last_indexed_at=now_iso(), stats_json=json.dumps(stats))
    p = get_project(conn, project_id)
    result = project_to_dict(p, conn)
    conn.close()
    return {"status": "ok", "triggered_by": user["username"], "project": result, **stats}


def _require_project_id(project_id: Optional[int], conn):
    if project_id is None:
        raise HTTPException(400, "project_id is required")
    if not get_project(conn, project_id):
        raise HTTPException(404, "project not found")
    return project_id


# --------------------------- graph query endpoints (auth required) ---------------------------

@app.get("/api/search")
def search(project_id: int = Query(...), q: str = Query(..., min_length=1), limit: int = 25, user=Depends(get_current_user)):
    conn = get_conn()
    _require_project_id(project_id, conn)
    rows = conn.execute(
        """SELECT nodes.* FROM nodes_fts
           JOIN nodes ON nodes.id = nodes_fts.rowid
           WHERE nodes_fts MATCH ? AND nodes.project_id = ?
           LIMIT ?""",
        (q + "*", project_id, limit),
    ).fetchall()
    conn.close()
    return {"query": q, "results": [node_to_dict(r) for r in rows]}


@app.get("/api/nodes/{node_id}")
def get_node(node_id: int, project_id: int = Query(...), user=Depends(get_current_user)):
    conn = get_conn()
    _require_project_id(project_id, conn)
    row = conn.execute("SELECT * FROM nodes WHERE id=? AND project_id=?", (node_id, project_id)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "node not found")
    return node_to_dict(row)


@app.get("/api/nodes")
def list_nodes(project_id: int = Query(...), type: Optional[str] = None, file_path: Optional[str] = None,
               limit: int = 100, user=Depends(get_current_user)):
    conn = get_conn()
    _require_project_id(project_id, conn)
    q = "SELECT * FROM nodes WHERE project_id=?"
    params = [project_id]
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
    project_id: int = Query(...),
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
    _require_project_id(project_id, conn)
    sql = """
        SELECT edges.id, edges.type, edges.resolved, edges.raw_expression,
               src.id as source_id, src.name as source_name, src.type as source_type, src.file_path as source_file,
               tgt.id as target_id, tgt.name as target_name, tgt.type as target_type, tgt.file_path as target_file
        FROM edges
        LEFT JOIN nodes src ON src.id = edges.source_id
        LEFT JOIN nodes tgt ON tgt.id = edges.target_id
        WHERE edges.project_id = ?
    """
    params = [project_id]
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


def _traverse(conn, project_id, node_id, direction, depth, seen=None):
    """direction: 'out' (dependencies) or 'in' (dependents)"""
    if seen is None:
        seen = set()
    if node_id in seen or depth < 0:
        return {}
    seen.add(node_id)
    if direction == "out":
        rows = conn.execute(
            "SELECT * FROM edges WHERE project_id=? AND source_id=? AND resolved=1", (project_id, node_id)
        ).fetchall()
        key_field = "target_id"
    else:
        rows = conn.execute(
            "SELECT * FROM edges WHERE project_id=? AND target_id=? AND resolved=1", (project_id, node_id)
        ).fetchall()
        key_field = "source_id"

    children = []
    for r in rows:
        other_id = r[key_field]
        if other_id is None:
            continue
        node = conn.execute("SELECT * FROM nodes WHERE id=? AND project_id=?", (other_id, project_id)).fetchone()
        entry = {"edge_type": r["type"], "node": node_to_dict(node)}
        if depth > 0:
            entry["children"] = _traverse(conn, project_id, other_id, direction, depth - 1, seen)
        children.append(entry)
    return children


@app.get("/api/nodes/{node_id}/dependencies")
def get_dependencies(node_id: int, project_id: int = Query(...), depth: int = 1, user=Depends(get_current_user)):
    conn = get_conn()
    _require_project_id(project_id, conn)
    if not conn.execute("SELECT 1 FROM nodes WHERE id=? AND project_id=?", (node_id, project_id)).fetchone():
        conn.close()
        raise HTTPException(404, "node not found")
    result = _traverse(conn, project_id, node_id, "out", depth)
    conn.close()
    return {"node_id": node_id, "depth": depth, "dependencies": result}


@app.get("/api/nodes/{node_id}/dependents")
def get_dependents(node_id: int, project_id: int = Query(...), depth: int = 1, user=Depends(get_current_user)):
    conn = get_conn()
    _require_project_id(project_id, conn)
    if not conn.execute("SELECT 1 FROM nodes WHERE id=? AND project_id=?", (node_id, project_id)).fetchone():
        conn.close()
        raise HTTPException(404, "node not found")
    result = _traverse(conn, project_id, node_id, "in", depth)
    conn.close()
    return {"node_id": node_id, "depth": depth, "dependents": result}


@app.get("/api/nodes/{node_id}/impact")
def impact_of_change(node_id: int, project_id: int = Query(...), depth: int = 2, user=Depends(get_current_user)):
    """Everything that could be affected by changing this node: dependents,
    plus any routes/config reachable through them."""
    conn = get_conn()
    _require_project_id(project_id, conn)
    if not conn.execute("SELECT 1 FROM nodes WHERE id=? AND project_id=?", (node_id, project_id)).fetchone():
        conn.close()
        raise HTTPException(404, "node not found")
    dependents = _traverse(conn, project_id, node_id, "in", depth)
    conn.close()
    return {"node_id": node_id, "depth": depth, "impacted_by": dependents}


@app.get("/api/path")
def find_path(project_id: int = Query(...), source: int = Query(...), target: int = Query(...),
              max_depth: int = 6, user=Depends(get_current_user)):
    conn = get_conn()
    _require_project_id(project_id, conn)
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
                "SELECT target_id FROM edges WHERE project_id=? AND source_id=? AND resolved=1 AND target_id IS NOT NULL",
                (project_id, node_id),
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
def list_unresolved(project_id: int = Query(...), limit: int = 100, user=Depends(get_current_user)):
    conn = get_conn()
    _require_project_id(project_id, conn)
    rows = conn.execute(
        "SELECT * FROM edges WHERE project_id=? AND resolved=0 LIMIT ?", (project_id, limit)
    ).fetchall()
    conn.close()
    return {"count": len(rows), "unresolved_edges": [dict(r) for r in rows]}


@app.get("/api/graph")
def full_graph(project_id: int = Query(...), type: Optional[str] = None, user=Depends(get_current_user)):
    """Full graph as {nodes, edges} for visualization."""
    conn = get_conn()
    _require_project_id(project_id, conn)
    if type:
        nodes = conn.execute("SELECT * FROM nodes WHERE project_id=? AND type=?", (project_id, type)).fetchall()
    else:
        nodes = conn.execute("SELECT * FROM nodes WHERE project_id=?", (project_id,)).fetchall()
    edges = conn.execute("SELECT * FROM edges WHERE project_id=? AND resolved=1", (project_id,)).fetchall()
    conn.close()
    node_ids = {n["id"] for n in nodes}
    return {
        "nodes": [node_to_dict(n) for n in nodes],
        "edges": [dict(e) for e in edges if e["source_id"] in node_ids and e["target_id"] in node_ids],
    }


@app.get("/api/stats")
def stats(project_id: int = Query(...), user=Depends(get_current_user)):
    conn = get_conn()
    _require_project_id(project_id, conn)
    node_counts = conn.execute("SELECT type, COUNT(*) c FROM nodes WHERE project_id=? GROUP BY type", (project_id,)).fetchall()
    edge_counts = conn.execute("SELECT type, COUNT(*) c FROM edges WHERE project_id=? GROUP BY type", (project_id,)).fetchall()
    unresolved = conn.execute("SELECT COUNT(*) c FROM edges WHERE project_id=? AND resolved=0", (project_id,)).fetchone()["c"]
    conn.close()
    return {
        "nodes_by_type": {r["type"]: r["c"] for r in node_counts},
        "edges_by_type": {r["type"]: r["c"] for r in edge_counts},
        "unresolved_edges": unresolved,
    }
