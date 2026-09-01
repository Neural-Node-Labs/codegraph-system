# Codegraph Backend

A dependency-graph mapper for code, config, and pages/routes — with auth,
per-user API keys, user administration, and a read-only query API meant to
be consumed by an LLM (via the companion MCP server) or the codegraph-ui
frontend for codebase exploration.

**All extraction is 100% deterministic static analysis** — Python's `ast`
module for Python, structural regex for JS/TS/config/routes. No LLM is
involved in building the graph. An LLM only *reads* the finished graph
through the API or MCP tools.

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

This indexes the bundled `sample_repo/` and starts the API at
**http://localhost:8000** (and the UI at http://localhost:5173).

To run just this service standalone:
```bash
cd codegraph
docker compose up --build
```

## Point it at your own repo

Edit `docker-compose.yml` and change the volume mount:

```yaml
volumes:
  - /path/to/your/repo:/repo:ro
```

Then `docker compose up --build` again, or just call `POST /api/refresh`
(or hit "Refresh mapping" in the UI) after the container is already running
with the new volume mounted.

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

## Refreshing the mapping

`POST /api/refresh` re-runs the indexer against `REPO_PATH` and rebuilds
`nodes`/`edges` in place — it does **not** touch the `users` table. Any
authenticated user can call it (not just admins), since re-indexing only
reads the repo and never mutates it.

## API (for LLM / programmatic exploration)

| Endpoint                                  | Purpose                                      |
|--------------------------------------------|-----------------------------------------------|
| `GET /api/search?q=...`                    | full-text search over node names/signatures  |
| `GET /api/nodes/{id}`                      | get one node                                 |
| `GET /api/nodes?type=Route`                | list/filter nodes                            |
| `GET /api/edges?type=&resolved=&q=&limit=&offset=` | flat, filterable, joined listing of every relation — for a table-style "inspect every relation" view |
| `GET /api/nodes/{id}/dependencies?depth=N` | what this node depends on                    |
| `GET /api/nodes/{id}/dependents?depth=N`   | what depends on this node                    |
| `GET /api/nodes/{id}/impact?depth=N`       | blast radius of changing this node           |
| `GET /api/path?source=ID&target=ID`        | shortest dependency path between two nodes   |
| `GET /api/unresolved`                      | edges static analysis couldn't resolve       |
| `GET /api/graph?type=...`                  | full graph as `{nodes, edges}` JSON          |
| `GET /api/stats`                           | node/edge counts by type                     |
| `POST /api/refresh`                        | re-run the indexer, rebuild the graph        |

All responses are raw structured JSON — facts extracted from source, never a
model-generated summary. This is deliberate: the LLM consuming this API does
its own reasoning over verified facts instead of trusting a paraphrase.

### Wiring into an LLM / agent

See `../codegraph-mcp/README.md` for the full MCP server that wraps this API
as agent tools, with exact setup for Claude Code and Claude Desktop. The
short version: give the agent an API key (from the Admin UI) and point the
MCP server's `CODEGRAPH_API_URL` at this service.

## Running without Docker

```bash
pip install -r requirements.txt
PYTHONPATH=. python -m app.indexer sample_repo   # or your repo path
PYTHONPATH=. uvicorn app.api:app --reload
```

## Extending

- **New language**: add a parser module under `app/parsers/`, following the
  pattern in `python_parser.py` (AST-based) or `js_parser.py` (regex-based),
  then wire it into `indexer.py`'s file-extension dispatch.
- **New route framework** (Django, NestJS, Rails): add a decorator/pattern
  matcher similar to `route_parser.py`.
- **Incremental re-indexing**: currently the indexer does a full rebuild
  (`clear_graph` + re-parse) each run. For large repos, add a file-hash
  cache table and only re-parse changed files.
- **Swap SQLite for Neo4j**: the `db.py` interface (`upsert_node`,
  `add_edge`) is small enough to reimplement against a Cypher driver for
  large monorepos needing indexed multi-hop traversal.

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
- `POST /api/refresh` is blocking — for very large repos, expect the request
  to take a while; there's no background-job/polling variant yet.
