# Codegraph — full system

A dependency-graph mapper for code, config, routes, and API calls, with:

1. **`codegraph/`** — the backend: static-analysis indexer + FastAPI, with
   auth, per-user API keys, user administration, and multi-project
   management (create/rename/delete projects, upload+auto-unzip source,
   index each one independently).
2. **`codegraph-ui/`** — the frontend: a project switcher, graph
   visualization, a relations inspector table, a Projects page (upload zips,
   trigger indexing), and an admin page for managing users.
3. **`codegraph-mcp/`** — an MCP server so LLM agents (Claude Code, Claude
   Desktop, custom agents) can list projects and query/re-index their graphs
   as tools.

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

Then go to the **Projects** tab: create a project, drag a `.zip` of its
source onto it (auto-extracted server-side), and click **Index**. Pick it
from the project switcher in the top bar to explore its graph.

## What each piece does

### 1. `codegraph/` — backend

- Multi-project: each project is a row in `projects` plus a source
  directory on disk under `PROJECTS_ROOT/<slug>`. Every node/edge in the
  graph is tagged with `project_id`, so several codebases live side by side
  in one SQLite file without colliding.
- Indexes a project's source into its slice of the graph (`nodes`, `edges`)
  via AST/regex, no LLM.
- FastAPI query layer: search, dependencies/dependents, impact analysis,
  path-finding, full graph export, and a flat filterable `/api/edges` table
  for inspecting every relation directly — every one of these takes a
  `project_id` query param.
- Auth: session tokens for the browser UI, per-user API keys for
  agents/scripts. Roles: `admin` (manages users and projects) and `member`
  (can browse/select projects and trigger re-indexing).
- Project endpoints: `GET/POST /api/projects`, `GET/PATCH/DELETE
  /api/projects/{id}`, `POST /api/projects/{id}/upload` (multipart `.zip`,
  auto-extracted into the project's directory, guarded against zip-slip and
  oversized archives), `POST /api/projects/{id}/index` (re-runs the indexer
  for just that project).
- See `codegraph/README.md` for the full endpoint reference.

### 2. `codegraph-ui/` — frontend (Vite + React)

Four tabs after logging in, plus a project switcher in the top bar:
- **Graph** — the interactive circuit-board-style dependency visualization
  for the selected project, with a **Refresh mapping** button that
  re-indexes it.
- **Relations** — a searchable, filterable table of every edge in the
  selected project's graph (by relation type, resolved/unresolved, free
  text) — click any node name to jump to it in the Graph tab.
- **Projects** — create, rename, and delete projects (admin only); upload a
  `.zip` of a project's source by drag-and-drop or file picker (it's
  unzipped into the project automatically); trigger indexing; see
  status/node/edge counts per project; select the active project.
- **Admin** (admin role only) — create/disable/delete users, promote to
  admin, rotate API keys.

See `codegraph-ui/README.md` for dev/build details.

### 3. `codegraph-mcp/` — MCP server for agents

Wraps the backend as MCP tools: `list_projects`, `index_project`,
`search_code`, `list_relations`, `get_dependencies`, `get_dependents`,
`impact_of_change`, `find_path`, `list_unresolved`, and `get_stats`. Every
graph-query tool takes a `project_id` (call `list_projects` first, or set
`CODEGRAPH_PROJECT_ID` to default one in). Full setup instructions —
including exact config snippets for **Claude Code** and **Claude
Desktop** — are in `codegraph-mcp/README.md`.

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

Both resolve to the same user + role. Indexing (`POST
/api/projects/{id}/index`) and browsing are available to any authenticated
user; creating, renaming, deleting, and uploading source into a project are
admin-only.

## Adding your own codebase

From the UI: **Projects** tab → **New project** → drag a `.zip` of the repo
onto the project card → **Index**. That's it — no container rebuild or
volume remount needed.

From the API/CLI:
```bash
curl -X POST http://localhost:8000/api/projects \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"name": "my-service"}'
# -> {"id": 2, "slug": "my-service", ...}

zip -r my-service.zip my-service/
curl -X POST http://localhost:8000/api/projects/2/upload \
  -H "X-API-Key: $KEY" -F "file=@my-service.zip"

curl -X POST http://localhost:8000/api/projects/2/index -H "X-API-Key: $KEY"
```

Existing single-repo setups: if `REPO_PATH` is set in `docker-compose.yml`
and points at a non-empty directory, the container seeds a `default`
project from it on first boot (once, only if no projects exist yet) so
upgrades keep working without manual steps.

## Verified working end to end

Every piece of this system was exercised against a live, running stack
before packaging:
- Indexer → SQLite graph, scoped per project (33 nodes / 28 edges indexing
  the bundled sample repo as a project).
- Auth: login, `Authorization: Bearer` and `X-API-Key` paths, role
  enforcement (member correctly blocked from admin and project-management
  routes).
- Project lifecycle: create → upload `.zip` (auto-extracted, zip-slip
  guarded) → index → query graph/stats/search, all round-tripped through a
  live `TestClient` run, plus delete (confirmed it removes both the DB rows
  and the on-disk source directory, and never touches `users`).
- Admin CRUD: create/list/update/regenerate-key/delete users, all
  round-tripped.
- `/api/edges`: filtered and joined queries verified, project-scoped.
- Frontend: production build compiles cleanly with the new Projects page
  and project switcher.
