"""
Codegraph MCP server.

Wraps the codegraph HTTP API as MCP tools so any MCP-compatible agent
(Claude Code, Claude Desktop, a custom agent loop) can explore a codebase's
dependency graph and trigger re-indexing, without ever loading the whole
repo into context.

This process does no static analysis itself - it is a thin, stateless
adapter. All graph facts come from the codegraph backend over HTTP,
authenticated with a per-user API key (see README.md in this folder).

Environment variables:
  CODEGRAPH_API_URL   Base URL of the codegraph API (default: http://localhost:8000)
  CODEGRAPH_API_KEY   API key for a codegraph user (required)
"""
import os
import sys
import httpx
from mcp.server.mcpserver import MCPServer

API_URL = os.environ.get("CODEGRAPH_API_URL", "http://localhost:8000").rstrip("/")
API_KEY = os.environ.get("CODEGRAPH_API_KEY")

if not API_KEY:
    print(
        "[codegraph-mcp] WARNING: CODEGRAPH_API_KEY is not set. "
        "All tool calls will fail with 401 until it is configured.",
        file=sys.stderr,
    )

mcp = MCPServer(
    name="codegraph",
    version="1.0.0",
    instructions=(
        "Tools for exploring a codebase's dependency graph: files, functions, "
        "classes, config keys, routes, and API calls, plus the edges between "
        "them (imports, calls, reads_config, routes_to, calls_api). "
        "Use search_code to find a starting node, then get_dependencies / "
        "get_dependents / impact_of_change to explore outward from it. "
        "Every fact returned was extracted by static analysis (AST/regex), "
        "never generated - trust it as ground truth about the code as of "
        "the last refresh_mapping call."
    ),
)


def _client():
    headers = {"X-API-Key": API_KEY} if API_KEY else {}
    return httpx.Client(base_url=API_URL, headers=headers, timeout=30.0)


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


@mcp.tool()
def search_code(query: str, limit: int = 25) -> dict:
    """Full-text search over node names, signatures, and docstrings.
    Use this first to find the node id(s) for a symbol, file, route, or
    config key you're interested in before calling the other tools."""
    return _get("/api/search", q=query, limit=limit)


@mcp.tool()
def get_node(node_id: int) -> dict:
    """Get full details (type, file, line, language, signature, docstring)
    for a single node by id."""
    return _get(f"/api/nodes/{node_id}")


@mcp.tool()
def list_nodes(type: str | None = None, file_path: str | None = None, limit: int = 100) -> dict:
    """List nodes, optionally filtered by type (File, Function, Class,
    ConfigKey, Route, Component, ApiCall) and/or exact file_path."""
    params = {"limit": limit}
    if type:
        params["type"] = type
    if file_path:
        params["file_path"] = file_path
    return _get("/api/nodes", **params)


@mcp.tool()
def list_relations(
    type: str | None = None,
    resolved: bool | None = None,
    query: str | None = None,
    limit: int = 200,
) -> dict:
    """List edges (relations) between nodes, with source/target names
    joined in. Filter by edge type (imports, depends_on, reads_config,
    routes_to, calls_api), by whether the edge resolved to a real target,
    or by a text search across source/target names. Use resolved=false to
    find things static analysis couldn't follow (dynamic imports, external
    packages, template-built routes)."""
    params = {"limit": limit}
    if type:
        params["type"] = type
    if resolved is not None:
        params["resolved"] = resolved
    if query:
        params["q"] = query
    return _get("/api/edges", **params)


@mcp.tool()
def get_dependencies(node_id: int, depth: int = 1) -> dict:
    """What this node depends on: imports, config it reads, functions it
    contains, routes it registers. `depth` controls how many hops to
    follow outward (default 1 = direct dependencies only)."""
    return _get(f"/api/nodes/{node_id}/dependencies", depth=depth)


@mcp.tool()
def get_dependents(node_id: int, depth: int = 1) -> dict:
    """What depends on this node - i.e. what would be affected if it
    changed. `depth` controls how many hops to follow inward."""
    return _get(f"/api/nodes/{node_id}/dependents", depth=depth)


@mcp.tool()
def impact_of_change(node_id: int, depth: int = 2) -> dict:
    """Blast-radius view for a proposed change: everything that depends on
    this node, transitively, up to `depth` hops. Use before modifying a
    shared function, config key, or route handler."""
    return _get(f"/api/nodes/{node_id}/impact", depth=depth)


@mcp.tool()
def find_path(source_id: int, target_id: int, max_depth: int = 6) -> dict:
    """Find the shortest dependency path between two nodes, if one exists.
    Useful for answering 'how does A end up depending on B?'."""
    return _get("/api/path", source=source_id, target=target_id, max_depth=max_depth)


@mcp.tool()
def list_unresolved(limit: int = 100) -> dict:
    """List edges static analysis could not resolve to a concrete target
    (external packages, dynamic imports, template-built URLs). Surfaces
    what the graph is silent about, so it isn't mistaken for completeness."""
    return _get("/api/unresolved", limit=limit)


@mcp.tool()
def get_stats() -> dict:
    """Node and edge counts by type, plus the count of unresolved edges -
    a quick overview of what the current mapping covers."""
    return _get("/api/stats")


@mcp.tool()
def refresh_mapping() -> dict:
    """Re-run static analysis over the indexed repository and rebuild the
    dependency graph from scratch. Call this after the codebase has changed
    and before relying on the graph for up-to-date answers. This is a
    blocking call - it returns once re-indexing finishes."""
    return _post("/api/refresh")


if __name__ == "__main__":
    mcp.run(transport="stdio")
