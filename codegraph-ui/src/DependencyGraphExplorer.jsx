import React, { useState, useEffect, useRef, useMemo, useCallback } from "react";
import * as d3 from "d3";
import {
  Search, ZoomIn, ZoomOut, Maximize2, X, Upload,
  FileCode2, CircleDot, Box, KeySquare, Waypoints, Component as ComponentIcon,
  ArrowLeftRight, ChevronRight, ChevronDown, RotateCcw, Info
} from "lucide-react";

/* ---------------------------------------------------------------------
   Token system
   bg-base #0a0d12 · bg-panel #12161e · bg-raised #171c26 · hairline #262d3a
   text-primary #e8ecf4 · text-muted #7c8698 · text-faint #4c5566
   accent/trace-signal #eab04c
   Node-type palette:
     File #5b9dff  Function #43d17a  Class #f2b84b  ConfigKey #ef5da8
     Route #a67bfa  Component #38c6c2  ApiCall #f2864a
--------------------------------------------------------------------- */

const TYPE_COLOR = {
  File: "#5b9dff",
  Function: "#43d17a",
  Class: "#f2b84b",
  ConfigKey: "#ef5da8",
  Route: "#a67bfa",
  Component: "#38c6c2",
  ApiCall: "#f2864a",
};
const TYPE_ICON = {
  File: FileCode2,
  Function: CircleDot,
  Class: Box,
  ConfigKey: KeySquare,
  Route: Waypoints,
  Component: ComponentIcon,
  ApiCall: ArrowLeftRight,
};
const FALLBACK_COLOR = "#7c8698";
const NODE_TYPES = ["File", "Function", "Class", "ConfigKey", "Route", "Component", "ApiCall"];

const SAMPLE_DATA = {
  nodes: [
    { id: 1, type: "File", name: "config/settings.yaml", file_path: "config/settings.yaml", language: "yaml" },
    { id: 2, type: "ConfigKey", name: "app.name", file_path: "config/settings.yaml", signature: "sample-app" },
    { id: 3, type: "ConfigKey", name: "app.port", file_path: "config/settings.yaml", signature: "8080" },
    { id: 4, type: "ConfigKey", name: "database.pool_size", file_path: "config/settings.yaml", signature: "5" },
    { id: 6, type: "File", name: "config/.env", file_path: "config/.env", language: "env" },
    { id: 7, type: "ConfigKey", name: "DATABASE_URL", file_path: "config/.env", line_start: 1, signature: "postgres://localhost:5432/app" },
    { id: 8, type: "ConfigKey", name: "SECRET_KEY", file_path: "config/.env", line_start: 2, signature: "change-me-in-prod" },
    { id: 9, type: "ConfigKey", name: "DEBUG", file_path: "config/.env", line_start: 3, signature: "true" },
    { id: 10, type: "File", name: "frontend/UserProfile.jsx", file_path: "frontend/UserProfile.jsx", language: "jsx" },
    { id: 11, type: "Function", name: "UserProfile", file_path: "frontend/UserProfile.jsx", line_start: 3, signature: "UserProfile({ userId })", language: "javascript" },
    { id: 12, type: "Function", name: "loadUser", file_path: "frontend/UserProfile.jsx", line_start: 6, signature: "loadUser()", language: "javascript" },
    { id: 13, type: "File", name: "frontend/utils.js", file_path: "frontend/utils.js", language: "js" },
    { id: 14, type: "Function", name: "formatUser", file_path: "frontend/utils.js", line_start: 1, signature: "formatUser(data)", language: "javascript" },
    { id: 15, type: "Function", name: "createUser", file_path: "frontend/utils.js", line_start: 4, signature: "createUser(name)", language: "javascript" },
    { id: 16, type: "File", name: "backend/config.py", file_path: "backend/config.py", language: "py" },
    { id: 17, type: "Function", name: "get_db_url", file_path: "backend/config.py", line_start: 4, signature: "get_db_url()", language: "python" },
    { id: 18, type: "Function", name: "get_secret_key", file_path: "backend/config.py", line_start: 8, signature: "get_secret_key()", language: "python" },
    { id: 20, type: "File", name: "backend/app.py", file_path: "backend/app.py", language: "py" },
    { id: 21, type: "Function", name: "get_user", file_path: "backend/app.py", line_start: 10, signature: "get_user(user_id)", docstring: "Return a single user by id.", language: "python" },
    { id: 22, type: "Route", name: "GET /api/users/<user_id>", file_path: "backend/app.py", line_start: 10, signature: "GET /api/users/<user_id>" },
    { id: 23, type: "Function", name: "create_user", file_path: "backend/app.py", line_start: 16, signature: "create_user()", docstring: "Create a new user.", language: "python" },
    { id: 24, type: "Route", name: "POST /api/users", file_path: "backend/app.py", line_start: 16, signature: "POST /api/users" },
    { id: 25, type: "Function", name: "health", file_path: "backend/app.py", line_start: 22, signature: "health()", docstring: "Health check endpoint.", language: "python" },
    { id: 26, type: "Route", name: "GET /api/health", file_path: "backend/app.py", line_start: 22, signature: "GET /api/health" },
    { id: 28, type: "File", name: "backend/services/user_service.py", file_path: "backend/services/user_service.py", language: "py" },
    { id: 29, type: "Function", name: "get_user", file_path: "backend/services/user_service.py", line_start: 7, signature: "get_user(self, user_id)", docstring: "Fetch a user by id.", language: "python" },
    { id: 30, type: "Function", name: "create_user", file_path: "backend/services/user_service.py", line_start: 12, signature: "create_user(self, name)", docstring: "Create a new user record.", language: "python" },
    { id: 31, type: "Class", name: "UserService", file_path: "backend/services/user_service.py", line_start: 4, docstring: "Handles user lookups and creation.", language: "python" },
    { id: 32, type: "ApiCall", name: "GET /api/users/${userId}", file_path: "frontend/UserProfile.jsx", line_start: 8, signature: "GET /api/users/${userId}" },
    { id: 33, type: "ApiCall", name: "POST /api/users", file_path: "frontend/utils.js", line_start: 6, signature: "POST /api/users" },
  ],
  edges: [
    { id: 101, source_id: 1, target_id: 2, type: "depends_on" },
    { id: 102, source_id: 1, target_id: 3, type: "depends_on" },
    { id: 103, source_id: 1, target_id: 4, type: "depends_on" },
    { id: 104, source_id: 6, target_id: 7, type: "depends_on" },
    { id: 105, source_id: 6, target_id: 8, type: "depends_on" },
    { id: 106, source_id: 6, target_id: 9, type: "depends_on" },
    { id: 107, source_id: 10, target_id: 11, type: "depends_on" },
    { id: 108, source_id: 10, target_id: 12, type: "depends_on" },
    { id: 109, source_id: 13, target_id: 14, type: "depends_on" },
    { id: 110, source_id: 13, target_id: 15, type: "depends_on" },
    { id: 111, source_id: 16, target_id: 17, type: "depends_on" },
    { id: 112, source_id: 16, target_id: 18, type: "depends_on" },
    { id: 113, source_id: 20, target_id: 21, type: "depends_on" },
    { id: 114, source_id: 20, target_id: 23, type: "depends_on" },
    { id: 115, source_id: 20, target_id: 25, type: "depends_on" },
    { id: 116, source_id: 21, target_id: 22, type: "routes_to" },
    { id: 117, source_id: 23, target_id: 24, type: "routes_to" },
    { id: 118, source_id: 25, target_id: 26, type: "routes_to" },
    { id: 119, source_id: 28, target_id: 29, type: "depends_on" },
    { id: 120, source_id: 28, target_id: 30, type: "depends_on" },
    { id: 121, source_id: 28, target_id: 31, type: "depends_on" },
    { id: 122, source_id: 10, target_id: 13, type: "imports" },
    { id: 123, source_id: 20, target_id: 28, type: "imports" },
    { id: 124, source_id: 20, target_id: 16, type: "imports" },
    { id: 125, source_id: 28, target_id: 16, type: "imports" },
    { id: 126, source_id: 16, target_id: 7, type: "reads_config" },
    { id: 127, source_id: 16, target_id: 8, type: "reads_config" },
    { id: 128, source_id: 10, target_id: 32, type: "depends_on" },
    { id: 129, source_id: 13, target_id: 33, type: "depends_on" },
    { id: 130, source_id: 32, target_id: 22, type: "calls_api" },
    { id: 131, source_id: 33, target_id: 24, type: "calls_api" },
  ],
};

const CANVAS_W = 1200;
const CANVAS_H = 820;

function shortLabel(name, type) {
  if (type === "Route" || type === "ApiCall") return name;
  const parts = name.split(/[./]/);
  return parts[parts.length - 1];
}

export default function DependencyGraphExplorer({ externalData, onRefresh, refreshing, focusNodeId, onFocusHandled }) {
  const [data, setData] = useState(externalData || SAMPLE_DATA);
  const [positions, setPositions] = useState({});
  const [transform, setTransform] = useState({ x: 0, y: 0, k: 1 });
  const [selectedId, setSelectedId] = useState(null);
  const [hoveredId, setHoveredId] = useState(null);
  const [query, setQuery] = useState("");
  const [activeTypes, setActiveTypes] = useState(new Set(NODE_TYPES));
  const [depth, setDepth] = useState(2);
  const [importOpen, setImportOpen] = useState(false);
  const [importText, setImportText] = useState("");
  const [importError, setImportError] = useState("");
  const [apiUrl, setApiUrl] = useState("http://localhost:8000");
  const [apiLoading, setApiLoading] = useState(false);
  const [filtersCollapsed, setFiltersCollapsed] = useState(false);

  const svgRef = useRef(null);
  const gRef = useRef(null);
  const zoomBehavior = useRef(null);
  const dragState = useRef(null);

  /* sync with externally-supplied data (authenticated app shell fetches this) */
  useEffect(() => {
    if (externalData) setData(externalData);
  }, [externalData]);

  /* ---------------- layout: force simulation, computed once per dataset --------------- */
  useEffect(() => {
    const nodes = data.nodes.map((n) => ({ ...n }));
    const links = data.edges
      .filter((e) => data.nodes.some((n) => n.id === e.source_id) && data.nodes.some((n) => n.id === e.target_id))
      .map((e) => ({ source: e.source_id, target: e.target_id }));

    const sim = d3
      .forceSimulation(nodes)
      .force("link", d3.forceLink(links).id((d) => d.id).distance(90).strength(0.5))
      .force("charge", d3.forceManyBody().strength(-260))
      .force("center", d3.forceCenter(CANVAS_W / 2, CANVAS_H / 2))
      .force("collide", d3.forceCollide(34))
      .stop();

    for (let i = 0; i < 350; i++) sim.tick();

    const pos = {};
    nodes.forEach((n) => {
      pos[n.id] = { x: n.x, y: n.y };
    });
    setPositions(pos);
    setSelectedId(null);
  }, [data]);

  /* jump to a node requested from outside (e.g. the Relations table) */
  useEffect(() => {
    if (focusNodeId != null && positions[focusNodeId]) {
      setSelectedId(focusNodeId);
      onFocusHandled && onFocusHandled();
    }
  }, [focusNodeId, positions]); // eslint-disable-line react-hooks/exhaustive-deps

  /* ---------------- zoom/pan behavior --------------- */
  useEffect(() => {
    const svg = d3.select(svgRef.current);
    const zoom = d3
      .zoom()
      .scaleExtent([0.25, 3])
      .on("zoom", (event) => {
        setTransform({ x: event.transform.x, y: event.transform.y, k: event.transform.k });
      });
    zoomBehavior.current = zoom;
    svg.call(zoom);
    return () => svg.on(".zoom", null);
  }, []);

  const applyProgrammaticTransform = useCallback((t) => {
    const svg = d3.select(svgRef.current);
    svg.call(zoomBehavior.current.transform, d3.zoomIdentity.translate(t.x, t.y).scale(t.k));
  }, []);

  const zoomBy = (factor) => {
    const next = { ...transform, k: Math.max(0.25, Math.min(3, transform.k * factor)) };
    applyProgrammaticTransform(next);
  };

  const fitToView = useCallback(() => {
    const ids = Object.keys(positions);
    if (!ids.length) return;
    const xs = ids.map((id) => positions[id].x);
    const ys = ids.map((id) => positions[id].y);
    const minX = Math.min(...xs) - 60, maxX = Math.max(...xs) + 60;
    const minY = Math.min(...ys) - 60, maxY = Math.max(...ys) + 60;
    const w = maxX - minX, h = maxY - minY;
    const k = Math.max(0.25, Math.min(3, Math.min(CANVAS_W / w, CANVAS_H / h)));
    const x = CANVAS_W / 2 - k * (minX + w / 2);
    const y = CANVAS_H / 2 - k * (minY + h / 2);
    applyProgrammaticTransform({ x, y, k });
  }, [positions, applyProgrammaticTransform]);

  useEffect(() => {
    if (Object.keys(positions).length) fitToView();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [positions]);

  /* ---------------- adjacency for dependency / dependent lookups --------------- */
  const { outMap, inMap, nodeById } = useMemo(() => {
    const outMap = new Map();
    const inMap = new Map();
    const nodeById = new Map();
    data.nodes.forEach((n) => nodeById.set(n.id, n));
    data.edges.forEach((e) => {
      if (!nodeById.has(e.source_id) || !nodeById.has(e.target_id)) return;
      if (!outMap.has(e.source_id)) outMap.set(e.source_id, []);
      outMap.get(e.source_id).push(e);
      if (!inMap.has(e.target_id)) inMap.set(e.target_id, []);
      inMap.get(e.target_id).push(e);
    });
    return { outMap, inMap, nodeById };
  }, [data]);

  /* ---------------- BFS trace highlight from selected node --------------- */
  const highlight = useMemo(() => {
    if (selectedId == null) return null;
    const maxDepth = depth === "all" ? Infinity : depth;
    const nodeIds = new Set([selectedId]);
    const edgeIds = new Set();
    let frontier = [selectedId];
    let d = 0;
    while (frontier.length && d < maxDepth) {
      const next = [];
      frontier.forEach((id) => {
        [...(outMap.get(id) || []), ...(inMap.get(id) || [])].forEach((e) => {
          edgeIds.add(e.id);
          const other = e.source_id === id ? e.target_id : e.source_id;
          if (!nodeIds.has(other)) {
            nodeIds.add(other);
            next.push(other);
          }
        });
      });
      frontier = next;
      d++;
    }
    return { nodeIds, edgeIds };
  }, [selectedId, depth, outMap, inMap]);

  /* ---------------- search filter --------------- */
  const matchedIds = useMemo(() => {
    if (!query.trim()) return null;
    const q = query.toLowerCase();
    return new Set(
      data.nodes.filter((n) => n.name.toLowerCase().includes(q) || (n.file_path || "").toLowerCase().includes(q)).map((n) => n.id)
    );
  }, [query, data]);

  const visibleNodes = useMemo(() => data.nodes.filter((n) => activeTypes.has(n.type) || !TYPE_COLOR[n.type]), [data, activeTypes]);
  const visibleIds = useMemo(() => new Set(visibleNodes.map((n) => n.id)), [visibleNodes]);
  const visibleEdges = useMemo(
    () => data.edges.filter((e) => visibleIds.has(e.source_id) && visibleIds.has(e.target_id)),
    [data, visibleIds]
  );

  const typeCounts = useMemo(() => {
    const c = {};
    data.nodes.forEach((n) => (c[n.type] = (c[n.type] || 0) + 1));
    return c;
  }, [data]);

  /* ---------------- node dragging (screen -> svg -> graph space) --------------- */
  const screenToGraph = useCallback(
    (clientX, clientY) => {
      const pt = svgRef.current.createSVGPoint();
      pt.x = clientX;
      pt.y = clientY;
      const ctm = svgRef.current.getScreenCTM();
      const svgP = pt.matrixTransform(ctm.inverse());
      return { x: (svgP.x - transform.x) / transform.k, y: (svgP.y - transform.y) / transform.k };
    },
    [transform]
  );

  const onNodeMouseDown = (e, id) => {
    e.stopPropagation();
    const graphPt = screenToGraph(e.clientX, e.clientY);
    const nodePos = positions[id];
    dragState.current = { id, dx: graphPt.x - nodePos.x, dy: graphPt.y - nodePos.y };
    window.addEventListener("mousemove", onWindowMouseMove);
    window.addEventListener("mouseup", onWindowMouseUp);
  };

  const onWindowMouseMove = (e) => {
    if (!dragState.current) return;
    const { id, dx, dy } = dragState.current;
    const graphPt = screenToGraph(e.clientX, e.clientY);
    setPositions((prev) => ({ ...prev, [id]: { x: graphPt.x - dx, y: graphPt.y - dy } }));
  };

  const onWindowMouseUp = () => {
    dragState.current = null;
    window.removeEventListener("mousemove", onWindowMouseMove);
    window.removeEventListener("mouseup", onWindowMouseUp);
  };

  /* ---------------- import graph JSON --------------- */
  const applyGraphPayload = (parsed) => {
    if (!Array.isArray(parsed.nodes) || !Array.isArray(parsed.edges)) {
      throw new Error("Expected an object with `nodes` and `edges` arrays.");
    }
    setData({ nodes: parsed.nodes, edges: parsed.edges });
  };

  const handleImport = () => {
    try {
      applyGraphPayload(JSON.parse(importText));
      setImportError("");
      setImportOpen(false);
      setImportText("");
    } catch (err) {
      setImportError(err.message || "Could not parse JSON.");
    }
  };

  const handleFetchFromApi = async () => {
    setApiLoading(true);
    setImportError("");
    try {
      const res = await fetch(`${apiUrl.replace(/\/$/, "")}/api/graph`);
      if (!res.ok) throw new Error(`Request failed with status ${res.status}`);
      const json = await res.json();
      applyGraphPayload(json);
      setImportOpen(false);
    } catch (err) {
      setImportError(
        `Could not reach ${apiUrl}. Make sure the codegraph API is running and reachable from your browser (${err.message}).`
      );
    } finally {
      setApiLoading(false);
    }
  };

  const selectedNode = selectedId != null ? nodeById.get(selectedId) : null;
  const dependencies = selectedId != null ? (outMap.get(selectedId) || []) : [];
  const dependents = selectedId != null ? (inMap.get(selectedId) || []) : [];

  const toggleType = (t) => {
    setActiveTypes((prev) => {
      const next = new Set(prev);
      if (next.has(t)) next.delete(t);
      else next.add(t);
      return next;
    });
  };

  return (
    <div
      className="w-full h-full flex flex-col overflow-hidden"
      style={{
        background: "#0a0d12",
        color: "#e8ecf4",
        fontFamily: '-apple-system, "Segoe UI", Helvetica, Arial, sans-serif',
        minHeight: 640,
      }}
    >
      <style>{`
        @keyframes trace-flow {
          to { stroke-dashoffset: -24; }
        }
        .trace-active {
          animation: trace-flow 0.9s linear infinite;
        }
        @media (prefers-reduced-motion: reduce) {
          .trace-active { animation: none; }
        }
        .mono { font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace; }
        .depviz-scroll::-webkit-scrollbar { width: 8px; height: 8px; }
        .depviz-scroll::-webkit-scrollbar-thumb { background: #262d3a; border-radius: 4px; }
        .depviz-btn:focus-visible, .depviz-input:focus-visible, .depviz-node:focus-visible {
          outline: 2px solid #eab04c; outline-offset: 2px;
        }
      `}</style>

      {/* ---------------- top bar ---------------- */}
      <div
        className="flex items-center gap-3 px-4 shrink-0"
        style={{ height: 56, borderBottom: "1px solid #262d3a", background: "#12161e" }}
      >
        <div className="flex items-center gap-2 pr-3" style={{ borderRight: "1px solid #262d3a" }}>
          <Waypoints size={18} color="#eab04c" />
          <span className="text-sm font-semibold tracking-tight">Codegraph</span>
        </div>

        <div className="relative flex-1 max-w-md">
          <Search size={14} color="#4c5566" className="absolute left-2.5 top-1/2 -translate-y-1/2" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search nodes by name or path..."
            className="depviz-input w-full text-xs mono rounded-md pl-7 pr-2 py-1.5"
            style={{ background: "#0a0d12", border: "1px solid #262d3a", color: "#e8ecf4" }}
          />
        </div>

        <div className="flex items-center gap-3 text-[11px] mono uppercase tracking-wide" style={{ color: "#7c8698" }}>
          <span>Nodes <b style={{ color: "#e8ecf4" }}>{data.nodes.length}</b></span>
          <span>Edges <b style={{ color: "#e8ecf4" }}>{data.edges.length}</b></span>
        </div>

        <button
          onClick={() => setImportOpen(true)}
          className="depviz-btn flex items-center gap-1.5 text-xs rounded-md px-2.5 py-1.5 ml-1"
          style={{ background: "#171c26", border: "1px solid #262d3a", color: "#e8ecf4" }}
        >
          <Upload size={13} /> Import JSON
        </button>

        {onRefresh && (
          <button
            onClick={onRefresh}
            disabled={refreshing}
            className="depviz-btn flex items-center gap-1.5 text-xs rounded-md px-2.5 py-1.5"
            style={{ background: "#171c26", border: "1px solid #262d3a", color: "#eab04c", opacity: refreshing ? 0.6 : 1 }}
          >
            <RotateCcw size={13} className={refreshing ? "trace-active" : undefined} />
            {refreshing ? "Refreshing..." : "Refresh mapping"}
          </button>
        )}
      </div>

      <div className="flex flex-1 min-h-0">
        {/* ---------------- left filter rail ---------------- */}
        <div
          className="shrink-0 flex flex-col depviz-scroll overflow-y-auto"
          style={{
            width: filtersCollapsed ? 44 : 220,
            borderRight: "1px solid #262d3a",
            background: "#12161e",
            transition: "width 150ms ease",
          }}
        >
          <button
            onClick={() => setFiltersCollapsed((v) => !v)}
            className="depviz-btn flex items-center gap-1.5 text-[10px] uppercase tracking-wider px-3 py-3"
            style={{ color: "#7c8698" }}
          >
            {filtersCollapsed ? <ChevronRight size={12} /> : <ChevronDown size={12} />}
            {!filtersCollapsed && "Node types"}
          </button>

          {!filtersCollapsed && (
            <div className="px-2 pb-3 flex flex-col gap-1">
              {NODE_TYPES.map((t) => {
                const Icon = TYPE_ICON[t];
                const active = activeTypes.has(t);
                return (
                  <button
                    key={t}
                    onClick={() => toggleType(t)}
                    className="depviz-btn flex items-center gap-2 text-xs rounded-md px-2 py-1.5 text-left"
                    style={{
                      background: active ? "#171c26" : "transparent",
                      opacity: active ? 1 : 0.4,
                      color: "#e8ecf4",
                    }}
                  >
                    <span
                      style={{
                        width: 8, height: 8, borderRadius: t === "File" ? 2 : 8,
                        background: TYPE_COLOR[t], flexShrink: 0,
                      }}
                    />
                    <Icon size={12} color={TYPE_COLOR[t]} />
                    <span className="flex-1">{t}</span>
                    <span className="mono" style={{ color: "#4c5566" }}>{typeCounts[t] || 0}</span>
                  </button>
                );
              })}

              <div className="mt-3 pt-3" style={{ borderTop: "1px solid #262d3a" }}>
                <div className="text-[10px] uppercase tracking-wider px-2 mb-2" style={{ color: "#7c8698" }}>
                  Trace depth
                </div>
                <div className="flex gap-1 px-2">
                  {[1, 2, 3, "all"].map((d) => (
                    <button
                      key={d}
                      onClick={() => setDepth(d)}
                      className="depviz-btn text-[11px] mono rounded px-2 py-1 flex-1"
                      style={{
                        background: depth === d ? "#eab04c" : "#171c26",
                        color: depth === d ? "#0a0d12" : "#7c8698",
                        border: "1px solid #262d3a",
                      }}
                    >
                      {d}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* ---------------- graph canvas ---------------- */}
        <div className="relative flex-1 min-w-0" style={{ background: "#0a0d12" }}>
          <svg
            ref={svgRef}
            viewBox={`0 0 ${CANVAS_W} ${CANVAS_H}`}
            className="w-full h-full"
            style={{ cursor: "grab" }}
          >
            <defs>
              <pattern id="grid" width="28" height="28" patternUnits="userSpaceOnUse">
                <circle cx="1" cy="1" r="1" fill="#171c26" />
              </pattern>
            </defs>
            <rect x="-4000" y="-4000" width="8000" height="8000" fill="url(#grid)" />

            <g ref={gRef} transform={`translate(${transform.x},${transform.y}) scale(${transform.k})`}>
              {/* edges */}
              {visibleEdges.map((e) => {
                const s = positions[e.source_id];
                const t = positions[e.target_id];
                if (!s || !t) return null;
                const isActive = highlight && highlight.edgeIds.has(e.id);
                const dimmed = highlight && !isActive;
                const searchDim = matchedIds && !(matchedIds.has(e.source_id) && matchedIds.has(e.target_id)) && !isActive;
                const mx = (s.x + t.x) / 2 + (t.y - s.y) * 0.06;
                const my = (s.y + t.y) / 2 - (t.x - s.x) * 0.06;
                return (
                  <path
                    key={e.id}
                    d={`M ${s.x} ${s.y} Q ${mx} ${my} ${t.x} ${t.y}`}
                    fill="none"
                    stroke={isActive ? "#eab04c" : "#2a3140"}
                    strokeWidth={isActive ? 1.8 : 1}
                    opacity={dimmed || searchDim ? 0.15 : isActive ? 0.95 : 0.5}
                    strokeDasharray={isActive ? "5 4" : undefined}
                    className={isActive ? "trace-active" : undefined}
                  />
                );
              })}

              {/* nodes */}
              {visibleNodes.map((n) => {
                const pos = positions[n.id];
                if (!pos) return null;
                const color = TYPE_COLOR[n.type] || FALLBACK_COLOR;
                const isSelected = selectedId === n.id;
                const isHovered = hoveredId === n.id;
                const inHighlight = !highlight || highlight.nodeIds.has(n.id);
                const inSearch = !matchedIds || matchedIds.has(n.id);
                const dim = !inHighlight || !inSearch;
                const label = shortLabel(n.name, n.type);
                const isSquare = n.type === "File";
                const size = isSelected ? 9 : 6.5;

                return (
                  <g
                    key={n.id}
                    transform={`translate(${pos.x},${pos.y})`}
                    opacity={dim ? 0.2 : 1}
                    style={{ cursor: "pointer" }}
                    tabIndex={0}
                    className="depviz-node"
                    onMouseDown={(e) => onNodeMouseDown(e, n.id)}
                    onMouseEnter={() => setHoveredId(n.id)}
                    onMouseLeave={() => setHoveredId(null)}
                    onClick={() => setSelectedId(n.id === selectedId ? null : n.id)}
                    onKeyDown={(e) => e.key === "Enter" && setSelectedId(n.id === selectedId ? null : n.id)}
                  >
                    {isSquare ? (
                      <rect
                        x={-size} y={-size} width={size * 2} height={size * 2} rx={2}
                        fill="#0a0d12" stroke={color} strokeWidth={isSelected ? 2.5 : 1.6}
                      />
                    ) : (
                      <circle r={size} fill="#0a0d12" stroke={color} strokeWidth={isSelected ? 2.5 : 1.6} />
                    )}
                    <circle r={2} fill={color} />
                    {(isHovered || isSelected || transform.k > 0.9) && (
                      <text
                        x={size + 6}
                        y={4}
                        className="mono"
                        fontSize={10}
                        fill={isSelected ? "#e8ecf4" : "#a7b0c0"}
                        style={{ paintOrder: "stroke", stroke: "#0a0d12", strokeWidth: 3 }}
                      >
                        {label}
                      </text>
                    )}
                  </g>
                );
              })}
            </g>
          </svg>

          {/* zoom controls */}
          <div className="absolute bottom-4 right-4 flex flex-col gap-1">
            <button onClick={() => zoomBy(1.3)} className="depviz-btn p-2 rounded-md" style={{ background: "#171c26", border: "1px solid #262d3a" }}>
              <ZoomIn size={14} />
            </button>
            <button onClick={() => zoomBy(1 / 1.3)} className="depviz-btn p-2 rounded-md" style={{ background: "#171c26", border: "1px solid #262d3a" }}>
              <ZoomOut size={14} />
            </button>
            <button onClick={fitToView} className="depviz-btn p-2 rounded-md" style={{ background: "#171c26", border: "1px solid #262d3a" }}>
              <Maximize2 size={14} />
            </button>
          </div>

          {selectedId != null && (
            <div className="absolute bottom-4 left-4 flex items-center gap-2 text-[11px] mono px-2.5 py-1.5 rounded-md" style={{ background: "#171c26", border: "1px solid #262d3a", color: "#7c8698" }}>
              <Info size={12} />
              Tracing depth {depth} from <span style={{ color: "#e8ecf4" }}>{shortLabel(selectedNode?.name || "", selectedNode?.type)}</span>
              <button onClick={() => setSelectedId(null)} className="depviz-btn ml-1" style={{ color: "#7c8698" }}>
                <X size={12} />
              </button>
            </div>
          )}
        </div>

        {/* ---------------- inspector drawer ---------------- */}
        {selectedNode && (
          <div
            className="shrink-0 flex flex-col depviz-scroll overflow-y-auto"
            style={{ width: 300, borderLeft: "1px solid #262d3a", background: "#12161e" }}
          >
            <div className="flex items-start justify-between px-4 pt-4 pb-3" style={{ borderBottom: "1px solid #262d3a" }}>
              <div>
                <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider mb-1" style={{ color: TYPE_COLOR[selectedNode.type] || FALLBACK_COLOR }}>
                  {React.createElement(TYPE_ICON[selectedNode.type] || CircleDot, { size: 11 })}
                  {selectedNode.type}
                </div>
                <div className="text-sm mono break-all" style={{ color: "#e8ecf4" }}>{selectedNode.name}</div>
              </div>
              <button onClick={() => setSelectedId(null)} className="depviz-btn" style={{ color: "#7c8698" }}>
                <X size={16} />
              </button>
            </div>

            <div className="px-4 py-3 text-xs flex flex-col gap-2" style={{ borderBottom: "1px solid #262d3a" }}>
              {selectedNode.file_path && (
                <Row label="File" value={selectedNode.file_path + (selectedNode.line_start ? `:${selectedNode.line_start}` : "")} />
              )}
              {selectedNode.language && <Row label="Language" value={selectedNode.language} />}
              {selectedNode.signature && <Row label="Signature" value={selectedNode.signature} />}
              {selectedNode.docstring && <Row label="Doc" value={selectedNode.docstring} />}
            </div>

            <Section title={`Depends on (${dependencies.length})`}>
              {dependencies.length === 0 && <Empty text="No outgoing dependencies." />}
              {dependencies.map((e) => (
                <EdgeRow key={e.id} edge={e} node={nodeById.get(e.target_id)} onClick={() => setSelectedId(e.target_id)} />
              ))}
            </Section>

            <Section title={`Depended on by (${dependents.length})`}>
              {dependents.length === 0 && <Empty text="Nothing depends on this yet." />}
              {dependents.map((e) => (
                <EdgeRow key={e.id} edge={e} node={nodeById.get(e.source_id)} onClick={() => setSelectedId(e.source_id)} />
              ))}
            </Section>
          </div>
        )}
      </div>

      {/* ---------------- import modal ---------------- */}
      {importOpen && (
        <div
          className="fixed inset-0 flex items-center justify-center z-50"
          style={{ background: "rgba(10,13,18,0.7)" }}
          onClick={() => setImportOpen(false)}
        >
          <div
            className="w-full max-w-lg rounded-lg p-4 flex flex-col gap-3"
            style={{ background: "#12161e", border: "1px solid #262d3a" }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between">
              <div className="text-sm font-semibold">Import graph JSON</div>
              <button onClick={() => setImportOpen(false)} className="depviz-btn" style={{ color: "#7c8698" }}>
                <X size={16} />
              </button>
            </div>

            <div className="text-xs" style={{ color: "#7c8698" }}>
              Connect to a running codegraph API, or paste a{" "}
              <span className="mono">/api/graph</span> response shaped as{" "}
              <span className="mono">{`{ nodes: [...], edges: [...] }`}</span>.
            </div>

            <div>
              <div className="text-[10px] uppercase tracking-wider mb-1" style={{ color: "#4c5566" }}>
                API base URL
              </div>
              <div className="flex gap-2">
                <input
                  value={apiUrl}
                  onChange={(e) => setApiUrl(e.target.value)}
                  placeholder="http://localhost:8000"
                  className="depviz-input flex-1 text-xs mono rounded-md px-2 py-1.5"
                  style={{ background: "#0a0d12", border: "1px solid #262d3a", color: "#e8ecf4" }}
                />
                <button
                  onClick={handleFetchFromApi}
                  disabled={apiLoading}
                  className="depviz-btn text-xs rounded-md px-3 py-1.5 font-medium shrink-0"
                  style={{ background: "#eab04c", color: "#0a0d12", opacity: apiLoading ? 0.6 : 1 }}
                >
                  {apiLoading ? "Loading..." : "Fetch"}
                </button>
              </div>
            </div>

            <div className="flex items-center gap-2" style={{ color: "#4c5566" }}>
              <div className="flex-1 h-px" style={{ background: "#262d3a" }} />
              <span className="text-[10px] uppercase tracking-wider">or paste JSON</span>
              <div className="flex-1 h-px" style={{ background: "#262d3a" }} />
            </div>

            <textarea
              value={importText}
              onChange={(e) => setImportText(e.target.value)}
              rows={10}
              className="depviz-input mono text-xs rounded-md p-2 w-full"
              style={{ background: "#0a0d12", border: "1px solid #262d3a", color: "#e8ecf4", resize: "vertical" }}
              placeholder='{"nodes": [...], "edges": [...]}'
            />
            {importError && <div className="text-xs" style={{ color: "#ef5da8" }}>{importError}</div>}
            <div className="flex items-center justify-between">
              <button
                onClick={() => { setData(SAMPLE_DATA); setImportOpen(false); setImportError(""); }}
                className="depviz-btn flex items-center gap-1.5 text-xs rounded-md px-2.5 py-1.5"
                style={{ background: "#171c26", border: "1px solid #262d3a", color: "#7c8698" }}
              >
                <RotateCcw size={12} /> Reset to sample
              </button>
              <button
                onClick={handleImport}
                className="depviz-btn text-xs rounded-md px-3 py-1.5 font-medium"
                style={{ background: "#eab04c", color: "#0a0d12" }}
              >
                Load graph
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Row({ label, value }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider mb-0.5" style={{ color: "#4c5566" }}>{label}</div>
      <div className="mono break-all" style={{ color: "#c3cad6" }}>{value}</div>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div className="px-4 py-3" style={{ borderBottom: "1px solid #262d3a" }}>
      <div className="text-[10px] uppercase tracking-wider mb-2" style={{ color: "#7c8698" }}>{title}</div>
      <div className="flex flex-col gap-1">{children}</div>
    </div>
  );
}

function Empty({ text }) {
  return <div className="text-xs" style={{ color: "#4c5566" }}>{text}</div>;
}

function EdgeRow({ edge, node, onClick }) {
  if (!node) return null;
  const color = TYPE_COLOR[node.type] || FALLBACK_COLOR;
  const Icon = TYPE_ICON[node.type] || CircleDot;
  return (
    <button
      onClick={onClick}
      className="depviz-btn flex items-center gap-2 text-xs rounded-md px-2 py-1.5 text-left"
      style={{ background: "#171c26" }}
    >
      <Icon size={12} color={color} />
      <span className="mono flex-1 truncate" style={{ color: "#e8ecf4" }}>{shortLabel(node.name, node.type)}</span>
      <span className="text-[10px] mono" style={{ color: "#4c5566" }}>{edge.type}</span>
    </button>
  );
}
