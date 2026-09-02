import React, { useState, useEffect, useCallback } from "react";
import { Search, ChevronLeft, ChevronRight, AlertCircle } from "lucide-react";
import { api } from "./api.js";

const EDGE_TYPES = ["imports", "depends_on", "reads_config", "routes_to", "calls_api"];
const TYPE_COLOR = {
  File: "#5b9dff", Function: "#43d17a", Class: "#f2b84b", ConfigKey: "#ef5da8",
  Route: "#a67bfa", Component: "#38c6c2", ApiCall: "#f2864a",
};

const PAGE_SIZE = 50;

export default function RelationsPage({ projectId, onInspectNode }) {
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [typeFilter, setTypeFilter] = useState("");
  const [resolvedFilter, setResolvedFilter] = useState("");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!projectId) {
      setRows([]);
      setTotal(0);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const resp = await api.edges(projectId, {
        type: typeFilter || undefined,
        resolved: resolvedFilter === "" ? undefined : resolvedFilter === "true",
        q: query || undefined,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      });
      setRows(resp.results);
      setTotal(resp.total);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [projectId, typeFilter, resolvedFilter, query, page]);

  useEffect(() => {
    setPage(0);
  }, [typeFilter, resolvedFilter, query]);

  useEffect(() => {
    load();
  }, [load]);

  if (!projectId) {
    return (
      <div className="flex-1 flex items-center justify-center text-xs" style={{ color: "#4c5566" }}>
        Select a project to view its relations.
      </div>
    );
  }

  const NodeCell = ({ id, name, type, file }) => {
    if (id == null) {
      return <span className="text-[11px] mono flex items-center gap-1" style={{ color: "#4c5566" }}><AlertCircle size={11} /> unresolved</span>;
    }
    return (
      <button
        onClick={() => onInspectNode && onInspectNode(id)}
        className="text-left"
        title={file || ""}
      >
        <span className="mono text-[11px]" style={{ color: TYPE_COLOR[type] || "#e8ecf4" }}>{name}</span>
      </button>
    );
  };

  return (
    <div className="flex-1 overflow-y-auto p-6" style={{ color: "#e8ecf4" }}>
      <div className="flex items-center gap-2 mb-4 flex-wrap">
        <div className="relative">
          <Search size={13} color="#4c5566" className="absolute left-2.5 top-1/2 -translate-y-1/2" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="search source/target/expression..."
            className="text-xs mono rounded-md pl-7 pr-2 py-1.5 w-64"
            style={{ background: "#12161e", border: "1px solid #262d3a", color: "#e8ecf4" }}
          />
        </div>

        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="text-xs rounded-md px-2 py-1.5"
          style={{ background: "#12161e", border: "1px solid #262d3a", color: "#e8ecf4" }}
        >
          <option value="">All relation types</option>
          {EDGE_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>

        <select
          value={resolvedFilter}
          onChange={(e) => setResolvedFilter(e.target.value)}
          className="text-xs rounded-md px-2 py-1.5"
          style={{ background: "#12161e", border: "1px solid #262d3a", color: "#e8ecf4" }}
        >
          <option value="">Resolved + unresolved</option>
          <option value="true">Resolved only</option>
          <option value="false">Unresolved only</option>
        </select>

        <span className="text-[11px] mono ml-auto" style={{ color: "#7c8698" }}>{total} relations</span>
      </div>

      {error && (
        <div className="text-xs mb-3 px-3 py-2 rounded-md" style={{ background: "#2a1620", color: "#ef5da8" }}>{error}</div>
      )}

      <div className="rounded-lg overflow-hidden" style={{ border: "1px solid #262d3a" }}>
        <table className="w-full text-xs">
          <thead>
            <tr style={{ background: "#171c26", color: "#7c8698" }}>
              <th className="text-left px-3 py-2 font-medium">Source</th>
              <th className="text-left px-3 py-2 font-medium">Relation</th>
              <th className="text-left px-3 py-2 font-medium">Target</th>
              <th className="text-left px-3 py-2 font-medium">Detail</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={4} className="px-3 py-6 text-center" style={{ color: "#4c5566" }}>Loading...</td></tr>
            )}
            {!loading && rows.length === 0 && (
              <tr><td colSpan={4} className="px-3 py-6 text-center" style={{ color: "#4c5566" }}>No relations match these filters.</td></tr>
            )}
            {!loading && rows.map((r) => (
              <tr key={r.id} style={{ borderTop: "1px solid #262d3a" }}>
                <td className="px-3 py-2">
                  <NodeCell id={r.source_id} name={r.source_name} type={r.source_type} file={r.source_file} />
                </td>
                <td className="px-3 py-2">
                  <span
                    className="text-[10px] uppercase tracking-wide rounded px-1.5 py-0.5"
                    style={{ background: r.resolved ? "#171c26" : "#2a1620", color: r.resolved ? "#7c8698" : "#ef5da8" }}
                  >
                    {r.type}
                  </span>
                </td>
                <td className="px-3 py-2">
                  <NodeCell id={r.target_id} name={r.target_name} type={r.target_type} file={r.target_file} />
                </td>
                <td className="px-3 py-2 mono truncate max-w-[220px]" style={{ color: "#4c5566" }} title={r.raw_expression || ""}>
                  {r.raw_expression || "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between mt-3">
        <button
          onClick={() => setPage((p) => Math.max(0, p - 1))}
          disabled={page === 0}
          className="flex items-center gap-1 text-xs rounded-md px-2 py-1"
          style={{ background: "#171c26", border: "1px solid #262d3a", color: "#e8ecf4", opacity: page === 0 ? 0.4 : 1 }}
        >
          <ChevronLeft size={13} /> Prev
        </button>
        <span className="text-[11px] mono" style={{ color: "#4c5566" }}>
          Page {page + 1} of {Math.max(1, Math.ceil(total / PAGE_SIZE))}
        </span>
        <button
          onClick={() => setPage((p) => ((p + 1) * PAGE_SIZE < total ? p + 1 : p))}
          disabled={(page + 1) * PAGE_SIZE >= total}
          className="flex items-center gap-1 text-xs rounded-md px-2 py-1"
          style={{ background: "#171c26", border: "1px solid #262d3a", color: "#e8ecf4", opacity: (page + 1) * PAGE_SIZE >= total ? 0.4 : 1 }}
        >
          Next <ChevronRight size={13} />
        </button>
      </div>
    </div>
  );
}
