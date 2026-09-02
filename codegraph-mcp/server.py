"""
Codegraph MCP server.

Wraps the codegraph HTTP API as MCP tools so any MCP-compatible agent
(Claude Code, Claude Desktop, a custom agent loop) can explore a codebase's
dependency graph and trigger re-indexing, without ever loading the whole
repo into context.

This process does no static analysis itself - it is a thin, stateless
adapter. All graph facts come from the codegraph backend over HTTP,
authenticated with a per-user API key (see README.md in this folder).

Codegraph is multi-project: every graph-query tool takes a `project_id`.
Call list_projects() first to discover ids (and to see which one is
CODEGRAPH_PROJECT_ID's default, if that env var is set).

Environment variables:
  CODEGRAPH_API_URL     Base URL of the codegraph API (default: http://localhost:8000)
  CODEGRAPH_API_KEY     API key for a codegraph user (required)
  CODEGRAPH_PROJECT_ID  Optional default project id, used when a tool call
                         omits project_id.
"""
import os
import sys
import httpx
from mcp.server.mcpserver import MCPServer

API_URL = os.environ.get("CODEGRAPH_API_URL", "http://localhost:8000").rstrip("/")
API_KEY = os.environ.get("CODEGRAPH_API_KEY")
DEFAULT_PROJECT_ID = os.environ.get("CODEGRAPH_PROJECT_ID")
DEFAULT_PROJECT_ID = int(DEFAULT_PROJECT_ID) if DEFAULT_PROJECT_ID else None

if not API_KEY:
    print(
        "[codegraph-mcp] WARNING: CODEGRAPH_API_KEY is not set. "
        "All tool calls will fail with 401 until it is configured.",
        file=sys.stderr,
    )

mcp = MCPServer(
    name="codegraph",
    version="1.1.0",
    instructions=(
        "Tools for exploring a codebase's dependency graph: files, functions, "
        "classes, config keys, routes, and API calls, plus the edges between "
        "them (imports, calls, reads_config, routes_to, calls_api). "
        "Codegraph tracks multiple projects (codebases) side by side - call "
        "list_projects first to see what's available and get each one's id, "
        "then pass project_id to every other tool. Use search_code to find a "
        "starting node, then get_dependencies / get_dependents / "
        "impact_of_change to explore outward from it. Every fact returned "
        "was extracted by static analysis (AST/regex), never generated - "
        "trust it as ground truth about the code as of the last "
        "index_project call for that project."
    ),
)


def _client():
    headers = {"X-API-Key": API_KEY} if API_KEY else {}
    return httpx.Client(base_url=API_URL, headers=headers, timeout=60.0)


def _get(path, **params):
    with _client() as c:
        r = c.get(path, params=params)
        r.raise_for_status()
        return r.json()


def _post(path, **params):
    with _client() as c:
        r = c.post(path, params=params)
        r.raise_for_status()
        return r.json()


def _resolve_project_id(project_id: int | None) -> int:
    pid = project_id if project_id is not None else DEFAULT_PROJECT_ID
    if pid is None:
        raise ValueError(
            "project_id is required (no CODEGRAPH_PROJECT_ID default is configured). "
            "Call list_projects() to find one."
        )
    return pid


@mcp.tool()
def list_projects() -> dict:
    """List every project (codebase) codegraph knows about, with id, name,
    status (empty/indexing/ready/error), and node/edge counts. Call this
    first to get the project_id to pass to every other tool."""
    return _get("/api/projects")


@mcp.tool()
def index_project(project_id: int | None = None) -> dict:
    """Re-run static analysis over a project's uploaded source and rebuild
    its dependency graph from scratch. Call this after the project's source
    has changed (e.g. a new zip was uploaded) and before relying on the
    graph for up-to-date answers. This is a blocking call - it returns once
    re-indexing finishes."""
    pid = _resolve_project_id(project_id)
    return _post(f"/api/projects/{pid}/index")


@mcp.tool()
def search_code(query: str, project_id: int | None = None, limit: int = 25) -> dict:
    """Full-text search over node names, signatures, and docstrings within
    one project. Use this first to find the node id(s) for a symbol, file,
    route, or config key you're interested in before calling the other
    tools."""
    pid = _resolve_project_id(project_id)
    return _get("/api/search", project_id=pid, q=query, limit=limit)


@mcp.tool()
def get_node(node_id: int, project_id: int | None = None) -> dict:
    """Get full details (type, file, line, language, signature, docstring)
    for a single node by id, within one project."""
    pid = _resolve_project_id(project_id)
    return _get(f"/api/nodes/{node_id}", project_id=pid)


@mcp.tool()
def list_nodes(project_id: int | None = None, type: str | None = None, file_path: str | None = None, limit: int = 100) -> dict:
    """List nodes in a project, optionally filtered by type (File, Function,
    Class, ConfigKey, Route, Component, ApiCall) and/or exact file_path."""
    pid = _resolve_project_id(project_id)
    params = {"project_id": pid, "limit": limit}
    if type:
        params["type"] = type
    if file_path:
        params["file_path"] = file_path
    return _get("/api/nodes", **params)


@mcp.tool()
def list_relations(
    project_id: int | None = None,
    type: str | None = None,
    resolved: bool | None = None,
    query: str | None = None,
    limit: int = 200,
) -> dict:
    """List edges (relations) between nodes in a project, with source/target
    names joined in. Filter by edge type (imports, depends_on, reads_config,
    routes_to, calls_api), by whether the edge resolved to a real target,
    or by a text search across source/target names. Use resolved=false to
    find things static analysis couldn't follow (dynamic imports, external
    packages, template-built routes)."""
    pid = _resolve_project_id(project_id)
    params = {"project_id": pid, "limit": limit}
    if type:
        params["type"] = type
    if resolved is not None:
        params["resolved"] = resolved
    if query:
        params["q"] = query
    return _get("/api/edges", **params)


@mcp.tool()
def get_dependencies(node_id: int, project_id: int | None = None, depth: int = 1) -> dict:
    """What this node depends on: imports, config it reads, functions it
    contains, routes it registers. `depth` controls how many hops to
    follow outward (default 1 = direct dependencies only)."""
    pid = _resolve_project_id(project_id)
    return _get(f"/api/nodes/{node_id}/dependencies", project_id=pid, depth=depth)


@mcp.tool()
def get_dependents(node_id: int, project_id: int | None = None, depth: int = 1) -> dict:
    """What depends on this node - i.e. what would be affected if it
    changed. `depth` controls how many hops to follow inward."""
    pid = _resolve_project_id(project_id)
    return _get(f"/api/nodes/{node_id}/dependents", project_id=pid, depth=depth)


@mcp.tool()
def impact_of_change(node_id: int, project_id: int | None = None, depth: int = 2) -> dict:
    """Blast-radius view for a proposed change: everything that depends on
    this node, transitively, up to `depth` hops. Use before modifying a
    shared function, config key, or route handler."""
    pid = _resolve_project_id(project_id)
    return _get(f"/api/nodes/{node_id}/impact", project_id=pid, depth=depth)


@mcp.tool()
def find_path(source_id: int, target_id: int, project_id: int | None = None, max_depth: int = 6) -> dict:
    """Find the shortest dependency path between two nodes in a project, if
    one exists. Useful for answering 'how does A end up depending on B?'."""
    pid = _resolve_project_id(project_id)
    return _get("/api/path", project_id=pid, source=source_id, target=target_id, max_depth=max_depth)


@mcp.tool()
def list_unresolved(project_id: int | None = None, limit: int = 100) -> dict:
    """List edges static analysis could not resolve to a concrete target
    (external packages, dynamic imports, template-built URLs) within a
    project. Surfaces what the graph is silent about, so it isn't mistaken
    for completeness."""
    pid = _resolve_project_id(project_id)
    return _get("/api/unresolved", project_id=pid, limit=limit)


@mcp.tool()
def get_stats(project_id: int | None = None) -> dict:
    """Node and edge counts by type, plus the count of unresolved edges, for
    one project - a quick overview of what its current mapping covers."""
    pid = _resolve_project_id(project_id)
    return _get("/api/stats", project_id=pid)


if __name__ == "__main__":
    mcp.run(transport="stdio")
