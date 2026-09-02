-- Codegraph schema: pure fact base, no generated/inferred text.

-- Users: internal auth + API keys for agent/MCP access
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    salt          TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'member',  -- 'admin' | 'member'
    api_key       TEXT UNIQUE,
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Projects: one codebase each. Source lives on disk under
-- PROJECTS_ROOT/<slug>; the graph tables below are scoped to a project
-- via project_id so multiple codebases can be indexed side by side.
CREATE TABLE IF NOT EXISTS projects (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    slug            TEXT NOT NULL UNIQUE,   -- directory name under PROJECTS_ROOT
    description     TEXT,
    status          TEXT NOT NULL DEFAULT 'empty',  -- empty | ready | indexing | error
    last_indexed_at TEXT,
    last_index_stats TEXT,   -- JSON blob: {files, nodes, edges, unresolved}
    last_error      TEXT,
    created_by      INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS nodes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id   INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    type         TEXT NOT NULL,      -- File, Module, Function, Class, ConfigKey, Route, Component, ApiCall, DBTable
    name         TEXT NOT NULL,
    file_path    TEXT,
    line_start   INTEGER,
    line_end     INTEGER,
    language     TEXT,
    signature    TEXT,
    docstring    TEXT,
    UNIQUE(project_id, type, name, file_path, line_start)
);

CREATE TABLE IF NOT EXISTS edges (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id     INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    source_id      INTEGER NOT NULL,
    target_id      INTEGER,               -- NULL if unresolved
    type           TEXT NOT NULL,         -- imports, calls, reads_config, writes_config, renders, routes_to, calls_api, depends_on, queries_table
    resolved       INTEGER NOT NULL DEFAULT 0,
    raw_expression TEXT,
    FOREIGN KEY(source_id) REFERENCES nodes(id),
    FOREIGN KEY(target_id) REFERENCES nodes(id)
);

CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id);
CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);
CREATE INDEX IF NOT EXISTS idx_edges_project ON edges(project_id);
CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(type);
CREATE INDEX IF NOT EXISTS idx_nodes_path ON nodes(file_path);
CREATE INDEX IF NOT EXISTS idx_nodes_project ON nodes(project_id);

-- Full text search over node identity/signature/docstring (verbatim text, not generated)
CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5(
    name, signature, docstring, content='nodes', content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS nodes_ai AFTER INSERT ON nodes BEGIN
    INSERT INTO nodes_fts(rowid, name, signature, docstring)
    VALUES (new.id, new.name, coalesce(new.signature,''), coalesce(new.docstring,''));
END;

CREATE TRIGGER IF NOT EXISTS nodes_ad AFTER DELETE ON nodes BEGIN
    INSERT INTO nodes_fts(nodes_fts, rowid, name, signature, docstring)
    VALUES ('delete', old.id, old.name, coalesce(old.signature,''), coalesce(old.docstring,''));
END;
