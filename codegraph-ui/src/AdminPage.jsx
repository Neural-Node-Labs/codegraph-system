import React, { useState, useEffect, useCallback } from "react";
import { Shield, Plus, RotateCcw, Trash2, X, Copy, Check } from "lucide-react";
import { api } from "./api.js";
import { useAuth } from "./AuthContext.jsx";

export default function AdminPage() {
  const { user: me } = useAuth();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [copiedId, setCopiedId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const resp = await api.adminListUsers();
      setUsers(resp.results);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const toggleActive = async (u) => {
    await api.adminUpdateUser(u.id, { is_active: !u.is_active });
    load();
  };

  const toggleRole = async (u) => {
    await api.adminUpdateUser(u.id, { role: u.role === "admin" ? "member" : "admin" });
    load();
  };

  const regenerateKey = async (u) => {
    await api.adminRegenerateKey(u.id);
    load();
  };

  const removeUser = async (u) => {
    if (!confirm(`Delete user "${u.username}"? This cannot be undone.`)) return;
    try {
      await api.adminDeleteUser(u.id);
      load();
    } catch (e) {
      setError(e.message);
    }
  };

  const copyKey = (u) => {
    navigator.clipboard?.writeText(u.api_key);
    setCopiedId(u.id);
    setTimeout(() => setCopiedId(null), 1500);
  };

  return (
    <div className="flex-1 overflow-y-auto p-6" style={{ color: "#e8ecf4" }}>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Shield size={16} color="#eab04c" />
          <span className="text-sm font-semibold">User administration</span>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-1.5 text-xs rounded-md px-2.5 py-1.5"
          style={{ background: "#eab04c", color: "#0a0d12" }}
        >
          <Plus size={13} /> New user
        </button>
      </div>

      {error && (
        <div className="text-xs mb-3 px-3 py-2 rounded-md" style={{ background: "#2a1620", color: "#ef5da8" }}>
          {error}
        </div>
      )}

      <div className="rounded-lg overflow-hidden" style={{ border: "1px solid #262d3a" }}>
        <table className="w-full text-xs">
          <thead>
            <tr style={{ background: "#171c26", color: "#7c8698" }}>
              <th className="text-left px-3 py-2 font-medium">Username</th>
              <th className="text-left px-3 py-2 font-medium">Role</th>
              <th className="text-left px-3 py-2 font-medium">Status</th>
              <th className="text-left px-3 py-2 font-medium">API key</th>
              <th className="text-left px-3 py-2 font-medium">Created</th>
              <th className="text-right px-3 py-2 font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={6} className="px-3 py-4 text-center" style={{ color: "#4c5566" }}>Loading...</td></tr>
            )}
            {!loading && users.map((u) => (
              <tr key={u.id} style={{ borderTop: "1px solid #262d3a" }}>
                <td className="px-3 py-2 mono">{u.username}{u.id === me?.id && <span style={{ color: "#4c5566" }}> (you)</span>}</td>
                <td className="px-3 py-2">
                  <button
                    onClick={() => toggleRole(u)}
                    disabled={u.id === me?.id}
                    className="text-[10px] uppercase tracking-wide rounded px-2 py-0.5"
                    style={{
                      background: u.role === "admin" ? "#3a2a12" : "#171c26",
                      color: u.role === "admin" ? "#f2b84b" : "#7c8698",
                      opacity: u.id === me?.id ? 0.5 : 1,
                    }}
                  >
                    {u.role}
                  </button>
                </td>
                <td className="px-3 py-2">
                  <button
                    onClick={() => toggleActive(u)}
                    disabled={u.id === me?.id}
                    className="text-[10px] uppercase tracking-wide rounded px-2 py-0.5"
                    style={{
                      background: u.is_active ? "#123a1e" : "#2a1620",
                      color: u.is_active ? "#43d17a" : "#ef5da8",
                      opacity: u.id === me?.id ? 0.5 : 1,
                    }}
                  >
                    {u.is_active ? "active" : "disabled"}
                  </button>
                </td>
                <td className="px-3 py-2">
                  <div className="flex items-center gap-1.5">
                    <span className="mono truncate max-w-[140px]" style={{ color: "#4c5566" }}>{u.api_key}</span>
                    <button onClick={() => copyKey(u)} title="Copy" style={{ color: "#7c8698" }}>
                      {copiedId === u.id ? <Check size={12} color="#43d17a" /> : <Copy size={12} />}
                    </button>
                  </div>
                </td>
                <td className="px-3 py-2 mono" style={{ color: "#4c5566" }}>{u.created_at?.split(" ")[0]}</td>
                <td className="px-3 py-2">
                  <div className="flex items-center gap-2 justify-end">
                    <button onClick={() => regenerateKey(u)} title="Regenerate API key" style={{ color: "#7c8698" }}>
                      <RotateCcw size={13} />
                    </button>
                    <button
                      onClick={() => removeUser(u)}
                      disabled={u.id === me?.id}
                      title="Delete user"
                      style={{ color: u.id === me?.id ? "#333944" : "#ef5da8" }}
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showCreate && (
        <CreateUserModal
          onClose={() => setShowCreate(false)}
          onCreated={() => { setShowCreate(false); load(); }}
        />
      )}
    </div>
  );
}

function CreateUserModal({ onClose, onCreated }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("member");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    setError("");
    try {
      await api.adminCreateUser(username, password, role);
      onCreated();
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
          <div className="text-sm font-semibold">New user</div>
          <button onClick={onClose} style={{ color: "#7c8698" }}><X size={16} /></button>
        </div>
        <input
          value={username} onChange={(e) => setUsername(e.target.value)} placeholder="username"
          className="text-xs rounded-md px-2 py-1.5" style={{ background: "#0a0d12", border: "1px solid #262d3a", color: "#e8ecf4" }}
        />
        <input
          value={password} onChange={(e) => setPassword(e.target.value)} placeholder="password" type="password"
          className="text-xs rounded-md px-2 py-1.5" style={{ background: "#0a0d12", border: "1px solid #262d3a", color: "#e8ecf4" }}
        />
        <div className="flex gap-2">
          {["member", "admin"].map((r) => (
            <button
              key={r} onClick={() => setRole(r)}
              className="flex-1 text-xs rounded-md py-1.5"
              style={{ background: role === r ? "#eab04c" : "#171c26", color: role === r ? "#0a0d12" : "#7c8698" }}
            >
              {r}
            </button>
          ))}
        </div>
        {error && <div className="text-xs" style={{ color: "#ef5da8" }}>{error}</div>}
        <button
          onClick={submit} disabled={busy || !username || !password}
          className="text-xs rounded-md px-3 py-2 font-medium"
          style={{ background: "#eab04c", color: "#0a0d12", opacity: busy || !username || !password ? 0.5 : 1 }}
        >
          {busy ? "Creating..." : "Create user"}
        </button>
      </div>
    </div>
  );
}
