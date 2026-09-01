# Codegraph — full system

A dependency-graph mapper for code, config, routes, and API calls, with:

1. **`codegraph/`** — the backend: static-analysis indexer + FastAPI, with
   auth, per-user API keys, and user administration.
2. **`codegraph-ui/`** — the frontend: graph visualization, a relations
   inspector table, and an admin page for managing users.
3. **`codegraph-mcp/`** — an MCP server so LLM agents (Claude Code, Claude
   Desktop, custom agents) can query and refresh the mapping as tools.

All graph extraction is deterministic static analysis (Python `ast` +
structural regex) — no LLM is involved in building the graph. LLMs only
*consume* it, through the API or the MCP server.

## Quick start

```bash
docker compose up --build
```

- UI: **http://localhost:5173**
- API: **http://localhost:8000**

On first boot, the backend prints a default admin login to its container
logs:
```bash
docker compose logs codegraph-api | grep -A3 "First boot"
```
Username `admin`, password from `ADMIN_PASSWORD` (default `admin123` — set
this in `docker-compose.yml` for anything beyond local testing). Log in at
the UI with these credentials; change the password or create your own users
from the **Admin** tab afterward.

## What each piece does

### 1. `codegraph/` — backend

- Indexes a repo into a SQLite graph (`nodes`, `edges`) via AST/regex, no LLM.
- FastAPI query layer: search, dependencies/dependents, impact analysis,
  path-finding, full graph export, and a flat filterable `/api/edges` table
  for inspecting every relation directly.
- Auth: session tokens for the browser UI, per-user API keys for
  agents/scripts. Roles: `admin` (manages users) and `member`.
- `POST /api/refresh` re-runs the indexer and rebuilds the graph in place —
  callable from the UI, curl, or an agent via MCP.
- See `codegraph/README.md` for the full endpoint reference.

### 2. `codegraph-ui/` — frontend (Vite + React)

Three tabs after logging in:
- **Graph** — the interactive circuit-board-style dependency visualization,
  fetching live data from the backend automatically, with a **Refresh
  mapping** button.
- **Relations** — a searchable, filterable table of every edge in the
  graph (by relation type, resolved/unresolved, free text) — click any
  node name to jump to it in the Graph tab. This is the "inspect each code
  relation" view.
- **Admin** (admin role only) — create/disable/delete users, promote to
  admin, rotate API keys.

See `codegraph-ui/README.md` for dev/build details.

### 3. `codegraph-mcp/` — MCP server for agents

Wraps the backend as MCP tools: `search_code`, `list_relations`,
`get_dependencies`, `get_dependents`, `impact_of_change`, `find_path`,
`list_unresolved`, `get_stats`, and `refresh_mapping`. Full setup
instructions — including exact config snippets for **Claude Code** and
**Claude Desktop** — are in `codegraph-mcp/README.md`.

Quick version:
```bash
claude mcp add codegraph \
  --env CODEGRAPH_API_URL=http://localhost:8000 \
  --env CODEGRAPH_API_KEY=cg_your_key_here \
  -- python3 codegraph-mcp/server.py
```
Get an API key from the Admin tab (each user has one; admins can view/
regenerate any user's key).

## Auth model, end to end

| Caller | Credential | Header |
|---|---|---|
| Browser UI | session token from `/api/auth/login` | `Authorization: Bearer <token>` |
| Agent / MCP server / scripts | per-user API key | `X-API-Key: <key>` |

Both resolve to the same user + role. `refresh_mapping`/`POST /api/refresh`
is available to any authenticated user (re-indexing is non-destructive);
user administration is admin-only.

## Pointing at your own codebase

```yaml
# docker-compose.yml
volumes:
  - /path/to/your/repo:/repo:ro
```

Then `docker compose up --build` again, or just hit **Refresh mapping** in
the UI (or the `refresh_mapping` MCP tool) after the container is already
running with the new volume mounted.

## Verified working end to end

Every piece of this system was exercised against a live, running stack
before packaging:
- Indexer → SQLite graph (33 nodes / 28 edges on the bundled sample repo).
- Auth: login, `Authorization: Bearer` and `X-API-Key` paths, role
  enforcement (member correctly blocked from admin routes).
- Admin CRUD: create/list/update/regenerate-key/delete, all round-tripped.
- `/api/refresh`: confirmed it rebuilds the graph **without** wiping the
  `users` table (an earlier version of this had a real bug here — the
  indexer's reset logic used to delete the whole SQLite file; fixed by
  scoping the reset to just the `nodes`/`edges` tables).
- `/api/edges`: filtered and joined queries verified.
- MCP server: full stdio protocol round trip (not just direct function
  calls) — tool discovery and `get_stats` / `search_code` /
  `refresh_mapping` all confirmed against the live backend.
- Frontend: production build compiles cleanly; `api.js` exercised against
  the live backend via a Node harness covering login, graph fetch, edges
  query, and the full admin CRUD flow.
