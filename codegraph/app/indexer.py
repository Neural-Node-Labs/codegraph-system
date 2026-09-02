"""
Indexer: walks a repository, runs deterministic static-analysis parsers on
each file, and writes a fact-based dependency graph to SQLite.

No LLM calls occur anywhere in this file. Every node/edge is derived by
mechanical rule from source text (AST or regex) and traceable to file+line.
Every fact is scoped to a project_id so several codebases can be indexed
side by side in the same database.
"""
import sys
import os
from pathlib import Path

from app.db import init_db, clear_graph, upsert_node, add_edge
from app.parsers.python_parser import parse_python_file
from app.parsers.js_parser import parse_js_file
from app.parsers.config_parser import parse_env_file, parse_structured_config
from app.parsers.route_parser import parse_express_routes

IGNORE_DIRS = {".git", "node_modules", "__pycache__", "venv", ".venv", "dist", "build", ".next"}

PY_EXT = {".py"}
JS_EXT = {".js", ".jsx", ".ts", ".tsx"}
ENV_EXT = {".env"}
STRUCTURED_CONFIG_EXT = {".json", ".yaml", ".yml"}


def walk_repo(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS and not d.startswith(".")]
        for fn in filenames:
            yield Path(dirpath) / fn


def module_path_to_file(module_name, repo_root, exts=(".py",)):
    """Resolve a dotted python module name to a file path within the repo, if present."""
    candidate = Path(repo_root) / (module_name.replace(".", "/"))
    for ext in exts:
        p = Path(str(candidate) + ext)
        if p.exists():
            return str(p.relative_to(repo_root))
    init_p = candidate / "__init__.py"
    if init_p.exists():
        return str(init_p.relative_to(repo_root))
    return None


def resolve_js_import(from_file_rel, import_spec, repo_root):
    """Resolve a relative JS import ('./foo', '../bar') to a file in the repo."""
    if not import_spec.startswith("."):
        return None  # external package - not part of this repo's graph
    base = (Path(repo_root) / from_file_rel).parent / import_spec
    candidates = [base]
    for ext in (".js", ".jsx", ".ts", ".tsx"):
        candidates.append(Path(str(base) + ext))
    for ext in (".js", ".jsx", ".ts", ".tsx"):
        candidates.append(base / f"index{ext}")
    for c in candidates:
        try:
            if c.exists() and c.is_file():
                return str(c.resolve().relative_to(Path(repo_root).resolve()))
        except Exception:
            continue
    return None


def path_matches_route(call_path, route_path):
    """Match a literal API-call path against a route pattern with :param / {param} placeholders."""
    def normalize(p):
        segs = [s for s in p.strip("/").split("/") if s != ""]
        return segs

    call_segs = normalize(call_path.split("?")[0])
    route_segs = normalize(route_path)
    if len(call_segs) != len(route_segs):
        return False
    for c, r in zip(call_segs, route_segs):
        if r.startswith(":") or (r.startswith("{") and r.endswith("}")) or (r.startswith("<") and r.endswith(">")):
            continue
        if c != r:
            return False
    return True


def index_repo(project_id: int, repo_root: str, reset: bool = True):
    conn = init_db()
    if reset:
        clear_graph(conn, project_id)
    repo_root = str(Path(repo_root).resolve())

    file_node_ids = {}
    py_results = {}
    js_results = {}
    route_nodes = []  # (node_id, method, path)
    stats = {"files": 0, "nodes": 0, "edges": 0, "unresolved": 0}

    # Pass 1: parse every file, create File + inner nodes
    for path in walk_repo(repo_root):
        ext = path.suffix if path.suffix else (path.name if path.name.startswith(".env") else "")
        rel = str(path.relative_to(repo_root))
        if ext in PY_EXT or ext in JS_EXT or ext in ENV_EXT or ext in STRUCTURED_CONFIG_EXT:
            file_id = upsert_node(conn, project_id, "File", rel, file_path=rel, language=ext.lstrip("."))
            file_node_ids[rel] = file_id
            stats["files"] += 1
        else:
            continue

        if ext in PY_EXT:
            res = parse_python_file(str(path), repo_root)
            if res is None:
                continue
            py_results[rel] = res

            for name, ln, end_ln, sig, doc in res.functions:
                fid = upsert_node(conn, project_id, "Function", f"{res.module_name}.{name}", file_path=rel,
                                   line_start=ln, line_end=end_ln, language="python",
                                   signature=sig, docstring=doc)
                add_edge(conn, project_id, file_id, fid, "depends_on", True)
                for _fname, method, mpath, mline in [r for r in res.routes if r[0] == name]:
                    rid = upsert_node(conn, project_id, "Route", f"{method} {mpath}", file_path=rel,
                                       line_start=mline, language="python", signature=f"{method} {mpath}")
                    add_edge(conn, project_id, fid, rid, "routes_to", True)
                    route_nodes.append((rid, method, mpath))

            for name, ln, end_ln, doc in res.classes:
                upsert_node(conn, project_id, "Class", f"{res.module_name}.{name}", file_path=rel,
                            line_start=ln, line_end=end_ln, language="python", docstring=doc)

        elif ext in JS_EXT:
            res = parse_js_file(str(path), repo_root)
            js_results[rel] = res
            for name, ln, sig in res.functions:
                upsert_node(conn, project_id, "Function", f"{rel}::{name}", file_path=rel, line_start=ln,
                            language="javascript", signature=sig)
            for comp, ln in res.renders:
                upsert_node(conn, project_id, "Component", comp, language="javascript")

            _, routes = parse_express_routes(str(path), repo_root)
            for method, rpath, ln in routes:
                rid = upsert_node(conn, project_id, "Route", f"{method} {rpath}", file_path=rel,
                                   line_start=ln, language="javascript", signature=f"{method} {rpath}")
                add_edge(conn, project_id, file_id, rid, "routes_to", True)
                route_nodes.append((rid, method, rpath))

        elif ext in ENV_EXT:
            _, keys = parse_env_file(str(path), repo_root)
            for key, ln, val in keys:
                kid = upsert_node(conn, project_id, "ConfigKey", key, file_path=rel, line_start=ln,
                                   language="env", signature=val)
                add_edge(conn, project_id, file_id, kid, "depends_on", True)

        elif ext in STRUCTURED_CONFIG_EXT:
            _, keys = parse_structured_config(str(path), repo_root)
            for key, ln, val in keys:
                kid = upsert_node(conn, project_id, "ConfigKey", key, file_path=rel, line_start=ln,
                                   language=ext.lstrip("."), signature=val)
                add_edge(conn, project_id, file_id, kid, "depends_on", True)

    conn.commit()

    # Pass 2: resolve cross-references now that all files are known
    for rel, res in py_results.items():
        file_id = file_node_ids[rel]
        for mod, alias, ln, fallback_mod in res.imports:
            target_rel = module_path_to_file(mod, repo_root)
            if not target_rel and fallback_mod:
                target_rel = module_path_to_file(fallback_mod, repo_root)
            if target_rel and target_rel in file_node_ids:
                add_edge(conn, project_id, file_id, file_node_ids[target_rel], "imports", True, raw_expression=mod)
            elif fallback_mod is None and mod.split(".")[0] not in sys.stdlib_module_names:
                add_edge(conn, project_id, file_id, None, "imports", False, raw_expression=mod)
                stats["unresolved"] += 1
            elif fallback_mod is not None:
                add_edge(conn, project_id, file_id, None, "imports", False, raw_expression=mod)
                stats["unresolved"] += 1

        for scope, key, ln in res.config_reads:
            cur = conn.execute("SELECT id FROM nodes WHERE project_id=? AND type='ConfigKey' AND name=?", (project_id, key))
            row = cur.fetchone()
            if row:
                add_edge(conn, project_id, file_id, row["id"], "reads_config", True, raw_expression=key)
            else:
                add_edge(conn, project_id, file_id, None, "reads_config", False, raw_expression=key)
                stats["unresolved"] += 1

    for rel, res in js_results.items():
        file_id = file_node_ids[rel]
        for mod, ln in res.imports:
            target_rel = resolve_js_import(rel, mod, repo_root)
            if target_rel and target_rel in file_node_ids:
                add_edge(conn, project_id, file_id, file_node_ids[target_rel], "imports", True, raw_expression=mod)
            elif mod.startswith("."):
                add_edge(conn, project_id, file_id, None, "imports", False, raw_expression=mod)
                stats["unresolved"] += 1

        for method, api_path, ln in res.api_calls:
            call_id = upsert_node(conn, project_id, "ApiCall", f"{method} {api_path}", file_path=rel,
                                   line_start=ln, language="javascript", signature=f"{method} {api_path}")
            add_edge(conn, project_id, file_id, call_id, "calls_api", False, raw_expression=api_path)
            matched = False
            for rid, rmethod, rpath in route_nodes:
                if rmethod == method and path_matches_route(api_path, rpath):
                    add_edge(conn, project_id, call_id, rid, "calls_api", True)
                    matched = True
            if not matched:
                stats["unresolved"] += 1

    conn.commit()

    stats["nodes"] = conn.execute("SELECT COUNT(*) c FROM nodes WHERE project_id=?", (project_id,)).fetchone()["c"]
    stats["edges"] = conn.execute("SELECT COUNT(*) c FROM edges WHERE project_id=?", (project_id,)).fetchone()["c"]
    conn.close()
    return stats


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else "/repo"
    pid = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    stats = index_repo(pid, root, reset=True)
    print(f"Indexed repo at {root} (project_id={pid})")
    print(stats)
