import React, { useState, useEffect, useCallback } from "react";
import { Waypoints, Network, Share2, Shield, LogOut } from "lucide-react";
import { AuthProvider, useAuth } from "./AuthContext.jsx";
import LoginPage from "./LoginPage.jsx";
import AdminPage from "./AdminPage.jsx";
import RelationsPage from "./RelationsPage.jsx";
import DependencyGraphExplorer from "./DependencyGraphExplorer.jsx";
import { api } from "./api.js";

function Shell() {
  const { user, logout } = useAuth();
  const [tab, setTab] = useState("graph");
  const [graphData, setGraphData] = useState(null);
  const [graphError, setGraphError] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [focusNodeId, setFocusNodeId] = useState(null);

  const loadGraph = useCallback(async () => {
    setGraphError("");
    try {
      const data = await api.graph();
      setGraphData(data);
    } catch (e) {
      setGraphError(e.message);
    }
  }, []);

  useEffect(() => {
    loadGraph();
  }, [loadGraph]);

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await api.refresh();
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
    ...(user?.role === "admin" ? [{ id: "admin", label: "Admin", icon: Shield }] : []),
  ];

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
          <DependencyGraphExplorer
            externalData={graphData || undefined}
            onRefresh={handleRefresh}
            refreshing={refreshing}
            focusNodeId={focusNodeId}
            onFocusHandled={() => setFocusNodeId(null)}
          />
        )}
        {tab === "relations" && <RelationsPage onInspectNode={jumpToNode} />}
        {tab === "admin" && user?.role === "admin" && <AdminPage />}
      </div>
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
