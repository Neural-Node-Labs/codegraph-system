import React, { useState, useEffect, useCallback, useRef } from "react";
import {
  FolderGit2, Plus, Trash2, Pencil, UploadCloud, RefreshCw, X, Check, CircleCheck,
} from "lucide-react";
import { api } from "./api.js";
import { useAuth } from "./AuthContext.jsx";

const STATUS_STYLE = {
  ready: { bg: "#123a1e", fg: "#43d17a", label: "ready" },
  indexing: { bg: "#3a2a12", fg: "#f2b84b", label: "indexing..." },
  empty: { bg: "#171c26", fg: "#7c8698", label: "no source yet" },
  error: { bg: "#2a1620", fg: "#ef5da8", label: "error" },
};

function StatusBadge({ status }) {
  const s = STATUS_STYLE[status] || STATUS_STYLE.empty;
  return (
    <span className="text-[10px] uppercase tracking-wide rounded px-2 py-0.5" style={{ background: s.bg, color: s.fg }}>
      {s.label}
    </span>
  );
}

export default function ProjectsPage({ selectedProjectId, onSelectProject, onProjectsChanged }) {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [busyId, setBusyId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const resp = await api.listProjects();
      setProjects(resp.results);
      onProjectsChanged && onProjectsChanged(resp.results);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [onProjectsChanged]);

  useEffect(() => {
    load();
  }, [load]);

  const withBusy = async (id, fn) => {
    setBusyId(id);
    setError("");
    try {
      await fn();
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusyId(null);
    }
  };

  const removeProject = (p) => {
    if (!confirm(`Delete project "${p.name}"? This removes its source files and graph. This cannot be undone.`)) return;
    withBusy(p.id, async () => {
      await api.deleteProject(p.id);
      if (selectedProjectId === p.id) onSelectProject(null);
    });
  };

  const indexProject = (p) => withBusy(p.id, () => api.indexProject(p.id));

  return (
    <div className="flex-1 overflow-y-auto p-6" style={{ color: "#e8ecf4" }}>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <FolderGit2 size={16} color="#eab04c" />
          <span className="text-sm font-semibold">Projects</span>
        </div>
        {isAdmin && (
          <button
            onClick={() => setShowCreate(true)}
            className="flex items-center gap-1.5 text-xs rounded-md px-2.5 py-1.5"
            style={{ background: "#eab04c", color: "#0a0d12" }}
          >
            <Plus size={13} /> New project
          </button>
        )}
      </div>

      {error && (
        <div className="text-xs mb-3 px-3 py-2 rounded-md" style={{ background: "#2a1620", color: "#ef5da8" }}>
          {error}
        </div>
      )}

      {loading && <div className="text-xs" style={{ color: "#4c5566" }}>Loading...</div>}

      {!loading && projects.length === 0 && (
        <div className="text-xs rounded-lg p-6 text-center" style={{ background: "#12161e", border: "1px dashed #262d3a", color: "#7c8698" }}>
          No projects yet.{isAdmin ? " Create one, then upload a zip of its source to index it." : " Ask an admin to create one."}
        </div>
      )}

      <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))" }}>
        {projects.map((p) => (
          <ProjectCard
            key={p.id}
            project={p}
            isAdmin={isAdmin}
            isSelected={selectedProjectId === p.id}
            busy={busyId === p.id}
            onSelect={() => onSelectProject(p.id)}
            onIndex={() => indexProject(p)}
            onDelete={() => removeProject(p)}
            onChanged={load}
            setError={setError}
          />
        ))}
      </div>

      {showCreate && (
        <CreateProjectModal
          onClose={() => setShowCreate(false)}
          onCreated={(p) => { setShowCreate(false); load(); onSelectProject(p.id); }}
        />
      )}
    </div>
  );
}

function ProjectCard({ project, isAdmin, isSelected, busy, onSelect, onIndex, onDelete, onChanged, setError }) {
  const [renaming, setRenaming] = useState(false);
  const [name, setName] = useState(project.name);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef(null);

  const saveRename = async () => {
    if (!name.trim() || name === project.name) {
      setRenaming(false);
      setName(project.name);
      return;
    }
    try {
      await api.updateProject(project.id, { name: name.trim() });
      setRenaming(false);
      onChanged();
    } catch (e) {
      setError(e.message);
    }
  };

  const doUpload = async (file) => {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".zip")) {
      setError("Only .zip files are supported for upload.");
      return;
    }
    setUploading(true);
    setError("");
    try {
      await api.uploadProjectZip(project.id, file, { replace: true });
      onChanged();
    } catch (e) {
      setError(e.message);
    } finally {
      setUploading(false);
    }
  };

  const stats = project.last_index_stats;

  return (
    <div
      className="rounded-lg p-3 flex flex-col gap-2"
      style={{
        background: "#12161e",
        border: isSelected ? "1px solid #eab04c" : "1px solid #262d3a",
      }}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          {renaming ? (
            <div className="flex items-center gap-1">
              <input
                autoFocus
                value={name}
                onChange={(e) => setName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && saveRename()}
                className="text-sm rounded px-1.5 py-0.5 w-full"
                style={{ background: "#0a0d12", border: "1px solid #262d3a", color: "#e8ecf4" }}
              />
              <button onClick={saveRename} style={{ color: "#43d17a" }}><Check size={14} /></button>
              <button onClick={() => { setRenaming(false); setName(project.name); }} style={{ color: "#7c8698" }}><X size={14} /></button>
            </div>
          ) : (
            <div className="flex items-center gap-1.5">
              <span className="text-sm font-medium truncate">{project.name}</span>
              {isSelected && <CircleCheck size={13} color="#eab04c" title="Active project" />}
            </div>
          )}
          <div className="text-[11px] mono truncate" style={{ color: "#4c5566" }}>{project.slug}</div>
        </div>
        <StatusBadge status={project.status} />
      </div>

      {project.description && (
        <div className="text-[11px] truncate" style={{ color: "#7c8698" }}>{project.description}</div>
      )}

      <div className="text-[11px] mono flex items-center gap-3" style={{ color: "#7c8698" }}>
        <span>{project.node_count} nodes</span>
        <span>{project.edge_count} edges</span>
        {project.last_indexed_at && <span>indexed {project.last_indexed_at.split(" ")[0]}</span>}
      </div>

      {project.status === "error" && project.last_error && (
        <div className="text-[11px]" style={{ color: "#ef5da8" }}>{project.last_error}</div>
      )}

      {isAdmin && (
        <div
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            doUpload(e.dataTransfer.files?.[0]);
          }}
          onClick={() => fileInputRef.current?.click()}
          className="text-[11px] rounded-md px-2 py-2 flex items-center justify-center gap-1.5 cursor-pointer"
          style={{
            border: `1px dashed ${dragOver ? "#eab04c" : "#333944"}`,
            color: dragOver ? "#eab04c" : "#7c8698",
            background: dragOver ? "#171c26" : "transparent",
          }}
        >
          <UploadCloud size={13} />
          {uploading ? "Uploading & unzipping..." : "Drop a .zip here or click to upload source (replaces existing files)"}
          <input
            ref={fileInputRef}
            type="file"
            accept=".zip"
            className="hidden"
            onChange={(e) => doUpload(e.target.files?.[0])}
          />
        </div>
      )}

      <div className="flex items-center gap-2 mt-1">
        <button
          onClick={onSelect}
          disabled={isSelected}
          className="flex-1 text-xs rounded-md py-1.5"
          style={{ background: isSelected ? "#171c26" : "#eab04c", color: isSelected ? "#7c8698" : "#0a0d12", opacity: isSelected ? 0.7 : 1 }}
        >
          {isSelected ? "Active" : "Select"}
        </button>
        <button
          onClick={onIndex}
          disabled={busy || project.status === "empty" || project.status === "indexing"}
          title="Re-index this project"
          className="flex items-center gap-1 text-xs rounded-md px-2 py-1.5"
          style={{ background: "#171c26", border: "1px solid #262d3a", color: "#e8ecf4", opacity: busy || project.status === "empty" ? 0.5 : 1 }}
        >
          <RefreshCw size={12} className={busy ? "animate-spin" : ""} /> Index
        </button>
        {isAdmin && (
          <>
            <button onClick={() => setRenaming(true)} title="Rename" style={{ color: "#7c8698" }}>
              <Pencil size={13} />
            </button>
            <button onClick={onDelete} title="Delete project" style={{ color: "#ef5da8" }}>
              <Trash2 size={13} />
            </button>
          </>
        )}
      </div>
    </div>
  );
}

function CreateProjectModal({ onClose, onCreated }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    setError("");
    try {
      const p = await api.createProject(name.trim(), description.trim() || undefined);
      onCreated(p);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 flex items-center justify-center z-50" style={{ background: "rgba(10,13,18,0.7)" }} onClick={onClose}>
      <div className="w-full max-w-sm rounded-lg p-4 flex flex-col gap-3" style={{ background: "#12161e", border: "1px solid #262d3a" }} onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <div className="text-sm font-semibold">New project</div>
          <button onClick={onClose} style={{ color: "#7c8698" }}><X size={16} /></button>
        </div>
        <input
          value={name} onChange={(e) => setName(e.target.value)} placeholder="project name"
          className="text-xs rounded-md px-2 py-1.5" style={{ background: "#0a0d12", border: "1px solid #262d3a", color: "#e8ecf4" }}
        />
        <input
          value={description} onChange={(e) => setDescription(e.target.value)} placeholder="description (optional)"
          className="text-xs rounded-md px-2 py-1.5" style={{ background: "#0a0d12", border: "1px solid #262d3a", color: "#e8ecf4" }}
        />
        {error && <div className="text-xs" style={{ color: "#ef5da8" }}>{error}</div>}
        <button
          onClick={submit} disabled={busy || !name.trim()}
          className="text-xs rounded-md px-3 py-2 font-medium"
          style={{ background: "#eab04c", color: "#0a0d12", opacity: busy || !name.trim() ? 0.5 : 1 }}
        >
          {busy ? "Creating..." : "Create project"}
        </button>
        <div className="text-[11px]" style={{ color: "#4c5566" }}>
          After creating, upload a .zip of the source — it's unzipped into the project automatically, then you can index it.
        </div>
      </div>
    </div>
  );
}
