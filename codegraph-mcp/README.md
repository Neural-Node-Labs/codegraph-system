# Codegraph MCP Server

Exposes the codegraph dependency graph to any MCP-compatible agent (Claude
Code, Claude Desktop, a custom agent loop) as a set of tools. The server is
a thin, stateless HTTP adapter — it does no static analysis itself, and adds
no facts of its own. Every response is data the `codegraph` backend already
extracted from source.

## 1. Prerequisites

- The `codegraph` backend running and reachable (see its own README) —
  typically `http://localhost:8000`.
- A codegraph user account with an API key. Every user gets one
  automatically; an admin can view/regenerate keys from the Admin page, or
  via `GET /api/admin/users`.

## 2. Running the MCP server

### Option A: Docker (recommended)

```bash
cd codegraph-mcp
docker build -t codegraph-mcp .
docker run -i --rm \
  -e CODEGRAPH_API_URL=http://host.docker.internal:8000 \
  -e CODEGRAPH_API_KEY=cg_your_key_here \
  codegraph-mcp
```

`host.docker.internal` lets the MCP container reach a codegraph backend
running on your host machine. If both run in the same Docker network
instead, use the backend's service name (e.g. `http://codegraph-api:8000`).

### Option B: Python directly

```bash
cd codegraph-mcp
pip install -r requirements.txt
export CODEGRAPH_API_URL=http://localhost:8000
export CODEGRAPH_API_KEY=cg_your_key_here
python3 server.py
```

The server speaks MCP over **stdio** — it's meant to be launched by an MCP
client (an agent), not called directly like a normal HTTP service.

## 3. Configuring an agent to use it

### Claude Code

```bash
claude mcp add codegraph \
  --env CODEGRAPH_API_URL=http://localhost:8000 \
  --env CODEGRAPH_API_KEY=cg_your_key_here \
  -- python3 /absolute/path/to/codegraph-mcp/server.py
```

Or, using the Docker image:

```bash
claude mcp add codegraph \
  --env CODEGRAPH_API_URL=http://host.docker.internal:8000 \
  --env CODEGRAPH_API_KEY=cg_your_key_here \
  -- docker run -i --rm -e CODEGRAPH_API_URL -e CODEGRAPH_API_KEY codegraph-mcp
```

Verify it's registered with `claude mcp list`, and check tool availability
with `/mcp` inside a Claude Code session.

### Claude Desktop

Edit your MCP config file:
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "codegraph": {
      "command": "python3",
      "args": ["/absolute/path/to/codegraph-mcp/server.py"],
      "env": {
        "CODEGRAPH_API_URL": "http://localhost:8000",
        "CODEGRAPH_API_KEY": "cg_your_key_here"
      }
    }
  }
}
```

Restart Claude Desktop after editing. The codegraph tools will appear in
the tool picker (hammer icon) in a new conversation.

### Any other MCP client

Point it at the same `command`/`args`/`env` shape shown above — the server
implements the standard MCP stdio transport, so any spec-compliant client
works the same way.

## 4. Projects

Codegraph indexes multiple codebases side by side. Every graph-query tool
below takes an optional `project_id: int` — call `list_projects` first to
discover ids, or set the `CODEGRAPH_PROJECT_ID` env var so it's filled in
automatically and you can omit it on every call.

```bash
export CODEGRAPH_PROJECT_ID=2   # optional: default project for this agent
```

## 5. Tool reference

| Tool | Arguments | Purpose |
|---|---|---|
| `list_projects` | — | List every project with id, name, status, node/edge counts. Call this first. |
| `index_project` | `project_id?: int` | Re-run static analysis for a project and rebuild its graph. Call after its source changes. |
| `search_code` | `query: str, project_id?: int, limit: int=25` | Full-text search over node names/signatures/docstrings. Start here to find a node id. |
| `get_node` | `node_id: int, project_id?: int` | Full details for one node (file, line, signature, docstring). |
| `list_nodes` | `project_id?: int, type?: str, file_path?: str, limit: int=100` | List/filter nodes by type or exact file. |
| `list_relations` | `project_id?: int, type?: str, resolved?: bool, query?: str, limit: int=200` | Flat list of edges with source/target names joined in — inspect every relation directly. |
| `get_dependencies` | `node_id: int, project_id?: int, depth: int=1` | What this node depends on, outward N hops. |
| `get_dependents` | `node_id: int, project_id?: int, depth: int=1` | What depends on this node, inward N hops. |
| `impact_of_change` | `node_id: int, project_id?: int, depth: int=2` | Blast radius if this node changes — use before editing shared code. |
| `find_path` | `source_id: int, target_id: int, project_id?: int, max_depth: int=6` | Shortest dependency path between two nodes. |
| `list_unresolved` | `project_id?: int, limit: int=100` | Edges static analysis couldn't resolve (dynamic imports, external packages, template routes). |
| `get_stats` | `project_id?: int` | Node/edge counts by type; quick sanity check on graph coverage. |

`project_id?` arguments fall back to `CODEGRAPH_PROJECT_ID` if set; if
neither is provided the tool call fails with a clear error asking you to
call `list_projects` first.

Verified against a real MCP stdio session: tool discovery and calls to
`list_projects`, `get_stats`, and `search_code` all round-trip correctly
against a live codegraph backend.

### Example agent flow

```
1. list_projects()
   -> {"results": [{"id": 2, "name": "payments-service", "status": "ready", ...}]}
2. search_code("payment", project_id=2)
   -> finds candidate nodes, e.g. node_id 142 (PaymentService.charge)
3. get_dependencies(142, project_id=2, depth=2)
   -> see what it imports/reads/calls
4. impact_of_change(142, project_id=2, depth=3)
   -> see what would break if it's modified
5. list_unresolved(project_id=2)
   -> check whether anything relevant was dynamically imported and
      might be missing from the picture above
```

## 6. Auth model

- Every codegraph user has a personal `api_key`. The MCP server sends it as
  `X-API-Key` on every request — same permission model as that user has in
  the web UI (member vs. admin). `index_project` is available to any
  authenticated user, not just admins, since re-indexing only reads a
  project's already-uploaded source and never mutates it. Creating projects
  and uploading new source remain admin-only and aren't exposed as MCP
  tools — do those from the web UI or directly against the API.
- Rotate a compromised key from the Admin page ("Regenerate key") — this
  immediately invalidates the old one.
- The MCP server itself holds no credentials of its own; it is only ever as
  privileged as the API key it's configured with.

## 7. Notes

- `index_project` is a **blocking** call — for large repositories it may
  take a while; the agent will simply wait for the tool result.
- All tool outputs are raw structured JSON extracted by static analysis —
  never a paraphrase or summary. This is intentional: the agent should
  reason over verified facts, not trust a lossy natural-language rendering
  of them.
- Built against `mcp` Python SDK 2.x, whose server class is
  `mcp.server.mcpserver.MCPServer` (renamed from the 1.x `FastMCP`). If your
  installed SDK is older, either upgrade (`pip install -U mcp`) or swap the
  import for `from mcp.server.fastmcp import FastMCP as MCPServer`.
