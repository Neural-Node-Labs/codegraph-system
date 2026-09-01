# Codegraph UI (Vite + React + Docker)

Interactive circuit-board-style visualization of a codebase dependency graph
— files, functions, classes, config keys, routes, and API calls — with
login, a relations inspector table, and user administration. Built to
consume the `codegraph` backend directly.

## Project layout

```
.
├── src/
│   ├── api.js                        # authenticated fetch wrapper + endpoint helpers
│   ├── AuthContext.jsx               # login state, token persistence
│   ├── LoginPage.jsx
│   ├── AdminPage.jsx                 # user management (admin role only)
│   ├── RelationsPage.jsx             # searchable/filterable table of every edge
│   ├── DependencyGraphExplorer.jsx   # the graph UI (d3-force layout, zoom/pan, trace highlighting)
│   ├── App.jsx                       # tab navigation + auth gate
│   ├── main.jsx
│   └── index.css
├── index.html
├── vite.config.js
├── tailwind.config.js / postcss.config.js
├── Dockerfile                        # production build → served by nginx
├── Dockerfile.dev                    # hot-reload dev server
├── docker-compose.dev.yml            # dev override (hot reload)
└── nginx.conf
```

(The top-level `docker-compose.yml`, one directory up, runs this alongside
the backend.)

## Run with Docker (production build)

From the repo root:
```bash
docker compose up --build
```
Opens at **http://localhost:5173**.

Standalone (backend running separately):
```bash
cd codegraph-ui
docker build -t codegraph-ui .
docker run -p 5173:80 codegraph-ui
```

## Run with Docker (hot reload, for development)

```bash
cd codegraph-ui
docker compose -f docker-compose.dev.yml up --build
```

## Run without Docker

```bash
npm install
npm run dev       # http://localhost:5173, hot reload
# or
npm run build && npm run preview
```

## Using the app

1. Log in (default `admin` / `ADMIN_PASSWORD` from the backend's env, or
   whatever you've since changed it to). If the API isn't at
   `http://localhost:8000`, expand **API server settings** on the login
   screen and point it at the right URL.
2. **Graph** tab — the interactive dependency visualization. Data loads
   automatically from the backend; **Refresh mapping** re-runs the indexer
   and reloads. The **Import JSON** button is still available for pasting a
   `/api/graph` payload manually (useful for demos without a live backend).
3. **Relations** tab — every edge in the graph as a filterable table
   (by relation type, resolved/unresolved, free text search). Click a
   node name to jump to it in the Graph tab, selected and trace-highlighted.
4. **Admin** tab (admin role only) — create/disable/delete users, promote
   to admin, rotate API keys (needed for MCP/agent access — see
   `../codegraph-mcp/README.md`).

## Notes on the build

- Tailwind is configured via PostCSS since the components use Tailwind
  utility classes for layout; colors and the circuit-board visual language
  are custom, set directly in the components.
- `d3` (force simulation, zoom/pan) and `lucide-react` (icons) are the only
  runtime dependencies beyond React itself.
- Auth token and API base URL persist in `localStorage` (this is a real
  deployed app, not a sandboxed artifact, so browser storage is fine here).
- The production Dockerfile is a two-stage build: `node:20-alpine` compiles
  the static bundle, then `nginx:1.27-alpine` serves it — the final image
  ships no Node.js or source, just static assets.
