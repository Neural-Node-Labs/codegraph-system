# Codegraph Backend

A dependency-graph mapper for code, config, and pages/routes — with auth,
per-user API keys, user administration, multi-project management, and a
read-only query API meant to be consumed by an LLM (via the companion MCP
server) or the codegraph-ui frontend for codebase exploration.

**All extraction is 100% deterministic static analysis** — Python's `ast`
module for Python, structural regex for JS/TS/config/routes. No LLM is
involved in building the graph. An LLM only *reads* the finished graph
through the API or MCP tools.

## Projects

Codegraph indexes multiple codebases side by side. Each **project** is:
- a row in the `projects` table (name, slug, status, last index stats), and
- a source directory on disk at `PROJECTS_ROOT/<slug>` (default
  `/data/projects/<slug>`, persisted in the `codegraph_data` volume).

Every node/edge is tagged with `project_id`, so all graph-query endpoints
take `project_id` as a required query param — nothing leaks across
projects.

Typical flow: `POST /api/projects` to create one → `POST
/api/projects/{id}/upload` with a `.zip` (auto-extracted server-side, zip-
slip guarded) → `POST /api/projects/{id}/index` to run the indexer → query
away with `?project_id=...`.

## What it extracts

| Node type   | Source                                            |
|-------------|----------------------------------------------------|
| `File`      | every source/config file in the repo               |
| `Function`  | Python `def`, JS function decls / arrow functions  |
| `Class`     | Python classes                                     |
| `ConfigKey` | flattened YAML/JSON keys, `.env` variables         |
| `Route`     | Flask/FastAPI decorators, Express `app.get(...)`   |
| `Component` | JSX component usage (`<Foo />`)                    |
| `ApiCall`   | `fetch(...)`, `axios.get/post/...`                 |

| Edge type      | Meaning                                              |
|----------------|-------------------------------------------------------|
| `imports`      | file A imports file B                                 |
| `depends_on`   | file contains function/class/config key                |
| `reads_config` | function reads a specific config key                  |
| `routes_to`    | function is registered as a route handler             |
| `calls_api`    | frontend fetch/axios call, resolved to a backend route |

Anything that can't be resolved statically (external packages, dynamic
imports, template-built URLs) is kept as an **unresolved edge** with the raw
expression attached — never silently dropped or guessed at.

## Quick start (Docker)

From the repo root (one level up):
```bash
docker compose up --build
```

This starts the API at **http://localhost:8000** (and the UI at
http://localhost:5173) with no projects yet — create one from the UI's
Projects tab or the API (see below).

To run just this service standalone:
```bash
cd codegraph
docker compose up --build
```

## Adding a project's source

From the UI: **Projects** tab → **New project** → drag a `.zip` onto the
card → **Index**.

From the API:
```bash
curl -X POST http://localhost:8000/api/projects \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"name": "my-service", "description": "optional"}'
# -> {"id": 2, "slug": "my-service", "status": "empty", ...}

curl -X POST http://localhost:8000/api/projects/2/upload \
  -H "X-API-Key: $KEY" -F "file=@my-service.zip" -F "replace=true"
# extracts the zip into PROJECTS_ROOT/my-service, unwrapping a single
# top-level folder inside the zip if present

curl -X POST http://localhost:8000/api/projects/2/index -H "X-API-Key: $KEY"
# runs the indexer over that project's source and rebuilds its graph
```

`replace=true` (the default) clears the project's existing source directory
before extracting; pass `replace=false` to extract on top of what's there.

### Legacy single-repo bootstrap

If `REPO_PATH` is set (see `docker-compose.yml`) and points at a non-empty
directory, the container copies it into a `default` project and indexes it
automatically — but only once, on first boot, and only if no projects exist
yet. This exists purely so upgrades from the old single-repo setup don't
need manual steps; new projects should be created via the UI/API.

## Auth

All `/api/*` endpoints (except `/api/auth/login`) require credentials:
- Browser/UI: `Authorization: Bearer <token>` from `POST /api/auth/login`
- Agents/scripts: `X-API-Key: <key>` — every user has one, visible/rotatable
  from the Admin UI or `GET /api/admin/users`

A default `admin` user is created on first boot (password from
`ADMIN_PASSWORD` env, default `admin123`) — check container logs for the
one-time confirmation message:
```bash
docker compose logs codegraph-api | grep -A3 "First boot"
```

## User administration (admin role only)

| Endpoint | Purpose |
|---|---|
| `GET /api/admin/users` | list all users |
| `POST /api/admin/users` | create a user `{username, password, role}` |
| `PATCH /api/admin/users/{id}` | update role / is_active / password |
| `POST /api/admin/users/{id}/regenerate-key` | rotate a user's API key |
| `DELETE /api/admin/users/{id}` | delete a user |

## Project management

| Endpoint | Auth | Purpose |
|---|---|---|
| `GET /api/projects` | any user | list all projects with status + node/edge counts |
| `POST /api/projects` | admin | create a project `{name, description?}` |
| `GET /api/projects/{id}` | any user | get one project |
| `PATCH /api/projects/{id}` | admin | rename / update description |
| `DELETE /api/projects/{id}` | admin | delete a project, its graph rows, and its source directory |
| `POST /api/projects/{id}/upload` | admin | multipart `.zip` upload (`file`, optional `replace=true\|false`), auto-extracted into the project's directory |
| `POST /api/projects/{id}/index` | any user | re-run the indexer for this project, rebuild its slice of the graph |

Indexing is available to any authenticated user (it only reads the
project's already-uploaded source and never mutates it); creating,
renaming, deleting projects, and uploading new source are admin-only since
they change what's on disk.

## API (for LLM / programmatic exploration)

Every endpoint below requires `project_id` as a query param.

| Endpoint                                  | Purpose                                      |
|--------------------------------------------|-----------------------------------------------|
| `GET /api/search?project_id=&q=...`        | full-text search over node names/signatures  |
| `GET /api/nodes/{id}?project_id=`          | get one node                                 |
| `GET /api/nodes?project_id=&type=Route`    | list/filter nodes                            |
| `GET /api/edges?project_id=&type=&resolved=&q=&limit=&offset=` | flat, filterable, joined listing of every relation — for a table-style "inspect every relation" view |
| `GET /api/nodes/{id}/dependencies?project_id=&depth=N` | what this node depends on        |
| `GET /api/nodes/{id}/dependents?project_id=&depth=N`   | what depends on this node        |
| `GET /api/nodes/{id}/impact?project_id=&depth=N`       | blast radius of changing this node |
| `GET /api/path?project_id=&source=ID&target=ID`        | shortest dependency path between two nodes |
| `GET /api/unresolved?project_id=`          | edges static analysis couldn't resolve       |
| `GET /api/graph?project_id=&type=...`      | full graph as `{nodes, edges}` JSON          |
| `GET /api/stats?project_id=`               | node/edge counts by type                     |

All responses are raw structured JSON — facts extracted from source, never a
model-generated summary. This is deliberate: the LLM consuming this API does
its own reasoning over verified facts instead of trusting a paraphrase.

### Wiring into an LLM / agent

See `../codegraph-mcp/README.md` for the full MCP server that wraps this API
as agent tools, with exact setup for Claude Code and Claude Desktop. The
short version: give the agent an API key (from the Admin UI) and point the
MCP server's `CODEGRAPH_API_URL` at this service; it discovers projects via
the `list_projects` tool.

## Running without Docker

```bash
pip install -r requirements.txt
export CODEGRAPH_DB=./graph.db
export PROJECTS_ROOT=./projects
PYTHONPATH=. uvicorn app.api:app --reload
```
Then create a project and upload/index it through the API as shown above
(or point `python -m app.indexer <project_id> <path>` at a source directory
once you have a project id).

## Extending

- **New language**: add a parser module under `app/parsers/`, following the
  pattern in `python_parser.py` (AST-based) or `js_parser.py` (regex-based),
  then wire it into `indexer.py`'s file-extension dispatch.
- **New route framework** (Django, NestJS, Rails): add a decorator/pattern
  matcher similar to `route_parser.py`.
- **Incremental re-indexing**: currently the indexer does a full rebuild
  (`clear_graph` + re-parse) per project on each run. For large repos, add a
  file-hash cache table and only re-parse changed files.
- **Swap SQLite for Neo4j**: the `db.py` interface (`upsert_node`,
  `add_edge`) is small enough to reimplement against a Cypher driver for
  large monorepos needing indexed multi-hop traversal — `project_id` maps
  naturally to a graph label or partition key.

## Known limitations (by design, not silently hidden)

- JS/TS parsing is regex-based, not a full parser — it handles common
  patterns (named/default imports, `require`, top-level functions, arrow
  functions, `fetch`/`axios` calls) but will miss deeply dynamic code.
- Structured config (YAML/JSON) line numbers are not tracked — only `.env`
  gets exact line numbers, since dict flattening loses source position
  without a source-mapping parser.
- Route-to-call matching is path-shape based (`:id`, `<id>`, `{id}`
  placeholders); template literals like `` `/api/users/${id}` `` are
  captured as unresolved rather than guessed at.
- `POST /api/projects/{id}/index` is blocking — for very large repos,
  expect the request to take a while; there's no background-job/polling
  variant yet.
- Zip uploads are capped at `MAX_UPLOAD_BYTES` (env var, default 200MB) for
  both the compressed upload and the extracted contents.
