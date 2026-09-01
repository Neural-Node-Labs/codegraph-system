import React, { useState } from "react";
import { Waypoints, LogIn, Settings } from "lucide-react";
import { useAuth } from "./AuthContext.jsx";

export default function LoginPage() {
  const { login, error, apiUrl, updateApiUrl } = useAuth();
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [urlDraft, setUrlDraft] = useState(apiUrl);

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    await login(username, password);
    setLoading(false);
  };

  return (
    <div
      className="w-full h-full flex items-center justify-center"
      style={{ background: "#0a0d12", color: "#e8ecf4", fontFamily: '-apple-system, "Segoe UI", sans-serif', minHeight: "100vh" }}
    >
      <div className="w-full max-w-sm rounded-lg p-6" style={{ background: "#12161e", border: "1px solid #262d3a" }}>
        <div className="flex items-center gap-2 mb-6 justify-center">
          <Waypoints size={20} color="#eab04c" />
          <span className="text-base font-semibold">Codegraph</span>
        </div>

        <form onSubmit={submit} className="flex flex-col gap-3">
          <div>
            <div className="text-[10px] uppercase tracking-wider mb-1" style={{ color: "#7c8698" }}>Username</div>
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full text-sm rounded-md px-3 py-2"
              style={{ background: "#0a0d12", border: "1px solid #262d3a", color: "#e8ecf4" }}
              autoComplete="username"
            />
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-wider mb-1" style={{ color: "#7c8698" }}>Password</div>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full text-sm rounded-md px-3 py-2"
              style={{ background: "#0a0d12", border: "1px solid #262d3a", color: "#e8ecf4" }}
              autoComplete="current-password"
            />
          </div>

          {error && <div className="text-xs" style={{ color: "#ef5da8" }}>{error}</div>}

          <button
            type="submit"
            disabled={loading}
            className="flex items-center justify-center gap-2 text-sm rounded-md px-3 py-2 font-medium mt-1"
            style={{ background: "#eab04c", color: "#0a0d12", opacity: loading ? 0.6 : 1 }}
          >
            <LogIn size={14} /> {loading ? "Signing in..." : "Sign in"}
          </button>
        </form>

        <button
          onClick={() => setShowSettings((v) => !v)}
          className="flex items-center gap-1.5 text-[11px] mt-4 mx-auto"
          style={{ color: "#4c5566" }}
        >
          <Settings size={11} /> API server settings
        </button>

        {showSettings && (
          <div className="mt-3 flex gap-2">
            <input
              value={urlDraft}
              onChange={(e) => setUrlDraft(e.target.value)}
              placeholder="http://localhost:8000"
              className="flex-1 text-xs mono rounded-md px-2 py-1.5"
              style={{ background: "#0a0d12", border: "1px solid #262d3a", color: "#e8ecf4", fontFamily: "ui-monospace, monospace" }}
            />
            <button
              onClick={() => updateApiUrl(urlDraft)}
              className="text-xs rounded-md px-2.5 py-1.5"
              style={{ background: "#171c26", border: "1px solid #262d3a", color: "#e8ecf4" }}
            >
              Save
            </button>
          </div>
        )}

        <div className="text-[10px] mt-4 text-center" style={{ color: "#4c5566" }}>
          Default admin credentials are set via <span className="mono">ADMIN_PASSWORD</span> on first boot.
        </div>
      </div>
    </div>
  );
}
