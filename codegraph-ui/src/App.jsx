import React, { useState, useEffect, useCallback } from "react";
import { Waypoints, Network, Share2, Shield, LogOut, FolderGit2, ChevronDown } from "lucide-react";
import { AuthProvider, useAuth } from "./AuthContext.jsx";
import LoginPage from "./LoginPage.jsx";
import AdminPage from "./AdminPage.jsx";
import ProjectsPage from "./ProjectsPage.jsx";
import RelationsPage from "./RelationsPage.jsx";
import DependencyGraphExplorer from "./DependencyGraphExplorer.jsx";
import { api, getSelectedProjectId, setSelectedProjectId } from "./api.js";

function ProjectSwitcher({ projects, selectedProjectId, onSelect, onManage }) {
  const [open, setOpen] = useState(false);
  const current = projects.find((p) => p.id === selectedProjectId);

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1.5 text-xs rounded-md px-2.5 py-1.5"
        style={{ background: "#171c26", border: "1px solid #262d3a", color: "#e8ecf4", maxWidth: 220 }}
      >
        <FolderGit2 size={13} color="#eab04c" />
        <span className="truncate">{current ? current.name : "No project selected"}</span>
        <ChevronDown size={12} color="#7c8698" />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div
            className="absolute right-0 mt-1 z-50 rounded-md overflow-hidden"
            style={{ background: "#12161e", border: "1px solid #262d3a", minWidth: 220, maxHeight: 320, overflowY: "auto" }}
          >
            {projects.length === 0 && (
              <div className="text-xs px-3 py-2" style={{ color: "#4c5566" }}>No projects yet</div>
            )}
            {projects.map((p) => (
              <button
                key={p.id}
                onClick={() => { onSelect(p.id); setOpen(false); }}
                className="w-full text-left text-xs px-3 py-2 flex items-center justify-between gap-2"
                style={{ background: p.id === selectedProjectId ? "#171c26" : "transparent", color: "#e8ecf4" }}
              >
                <span className="truncate">{p.name}</span>
                <span className="text-[10px] mono" style={{ color: "#4c5566" }}>{p.status}</span>
              </button>
            ))}
            <button
              onClick={() => { onManage(); setOpen(false); }}
              className="w-full text-left text-xs px-3 py-2"
              style={{ borderTop: "1px solid #262d3a", color: "#eab04c" }}
            >
              Manage projects...
            </button>
          </div>
        </>
      )}
    </div>
  );
}

function Shell() {
  const { user, logout } = useAuth();
  const [tab, setTab] = useState("graph");
  const [projects, setProjects] = useState([]);
  const [selectedProjectId, setSelectedProjectIdState] = useState(getSelectedProjectId());
  const [graphData, setGraphData] = useState(null);
  const [graphError, setGraphError] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [focusNodeId, setFocusNodeId] = useState(null);

  const selectProject = useCallback((id) => {
    setSelectedProjectId(id);
    setSelectedProjectIdState(id);
  }, []);

  const handleProjectsChanged = useCallback((list) => {
    setProjects(list);
    // If nothing (valid) is selected yet, default to the first ready project.
    setSelectedProjectIdState((current) => {
      if (current && list.some((p) => p.id === current)) return current;
      const firstReady = list.find((p) => p.status === "ready") || list[0];
      if (firstReady) {
        setSelectedProjectId(firstReady.id);
        return firstReady.id;
      }
      return current;
    });
  }, []);

  // Keep the project list fresh even when we're not on the Projects tab,
  // so the switcher and graph view reflect newly created/indexed projects.
  useEffect(() => {
    api.listProjects().then((resp) => handleProjectsChanged(resp.results)).catch(() => {});
  }, [handleProjectsChanged]);

  const loadGraph = useCallback(async () => {
    if (!selectedProjectId) {
      setGraphData(null);
      return;
    }
    setGraphError("");
    try {
      const data = await api.graph(selectedProjectId);
      setGraphData(data);
    } catch (e) {
      setGraphError(e.message);
    }
  }, [selectedProjectId]);

  useEffect(() => {
    loadGraph();
  }, [loadGraph]);

  const handleRefresh = async () => {
    if (!selectedProjectId) return;
    setRefreshing(true);
    try {
      await api.indexProject(selectedProjectId);
      await loadGraph();
    } catch (e) {
      setGraphError(e.message);
    } finally {
      setRefreshing(false);
    }
  };

  const jumpToNode = (nodeId) => {
    setFocusNodeId(nodeId);
    setTab("graph");
  };

  const tabs = [
    { id: "graph", label: "Graph", icon: Network },
    { id: "relations", label: "Relations", icon: Share2 },
    { id: "projects", label: "Projects", icon: FolderGit2 },
    ...(user?.role === "admin" ? [{ id: "admin", label: "Admin", icon: Shield }] : []),
  ];

  const currentProject = projects.find((p) => p.id === selectedProjectId);
  const needsProject = !selectedProjectId || !currentProject;

  return (
    <div className="w-full h-full flex flex-col" style={{ background: "#0a0d12", color: "#e8ecf4", fontFamily: '-apple-system, "Segoe UI", sans-serif', minHeight: "100vh" }}>
      <div className="flex items-center gap-1 px-4 shrink-0" style={{ height: 48, borderBottom: "1px solid #262d3a", background: "#12161e" }}>
        <div className="flex items-center gap-2 pr-4 mr-2" style={{ borderRight: "1px solid #262d3a" }}>
          <Waypoints size={16} color="#eab04c" />
          <span className="text-sm font-semibold">Codegraph</span>
        </div>

        {tabs.map((t) => {
          const Icon = t.icon;
          const active = tab === t.id;
          return (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className="flex items-center gap-1.5 text-xs rounded-md px-3 py-1.5"
              style={{ background: active ? "#171c26" : "transparent", color: active ? "#e8ecf4" : "#7c8698" }}
            >
              <Icon size={13} /> {t.label}
            </button>
          );
        })}

        <div className="ml-auto flex items-center gap-3">
          <ProjectSwitcher
            projects={projects}
            selectedProjectId={selectedProjectId}
            onSelect={selectProject}
            onManage={() => setTab("projects")}
          />
          <span className="text-[11px] mono" style={{ color: "#7c8698" }}>
            {user?.username} <span style={{ color: "#4c5566" }}>({user?.role})</span>
          </span>
          <button onClick={logout} className="flex items-center gap-1.5 text-xs" style={{ color: "#7c8698" }}>
            <LogOut size={13} /> Sign out
          </button>
        </div>
      </div>

      {graphError && (
        <div className="text-xs px-4 py-2" style={{ background: "#2a1620", color: "#ef5da8" }}>{graphError}</div>
      )}

      <div className="flex-1 min-h-0 flex flex-col">
        {tab === "graph" && (
          needsProject ? (
            <EmptyProjectState onManage={() => setTab("projects")} />
          ) : (
            <DependencyGraphExplorer
              externalData={graphData || undefined}
              onRefresh={handleRefresh}
              refreshing={refreshing}
              focusNodeId={focusNodeId}
              onFocusHandled={() => setFocusNodeId(null)}
            />
          )
        )}
        {tab === "relations" && <RelationsPage projectId={selectedProjectId} onInspectNode={jumpToNode} />}
        {tab === "projects" && (
          <ProjectsPage
            selectedProjectId={selectedProjectId}
            onSelectProject={selectProject}
            onProjectsChanged={handleProjectsChanged}
          />
        )}
        {tab === "admin" && user?.role === "admin" && <AdminPage />}
      </div>
    </div>
  );
}

function EmptyProjectState({ onManage }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-3 text-center px-6">
      <FolderGit2 size={28} color="#4c5566" />
      <div className="text-sm" style={{ color: "#e8ecf4" }}>No project selected</div>
      <div className="text-xs max-w-sm" style={{ color: "#7c8698" }}>
        Create a project, upload a .zip of its source, and index it to see its dependency graph here.
      </div>
      <button
        onClick={onManage}
        className="text-xs rounded-md px-3 py-1.5 mt-1"
        style={{ background: "#eab04c", color: "#0a0d12" }}
      >
        Go to Projects
      </button>
    </div>
  );
}

function Gate() {
  const { user } = useAuth();
  return user ? <Shell /> : <LoginPage />;
}

export default function App() {
  return (
    <AuthProvider>
      <Gate />
    </AuthProvider>
  );
}
