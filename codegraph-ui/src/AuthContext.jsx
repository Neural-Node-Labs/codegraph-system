import React, { createContext, useContext, useState, useCallback } from "react";
import { api, setToken, getStoredUser, setStoredUser, getApiUrl, setApiUrl as persistApiUrl } from "./api.js";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(getStoredUser());
  const [apiUrl, setApiUrlState] = useState(getApiUrl());
  const [error, setError] = useState("");

  const login = useCallback(async (username, password) => {
    setError("");
    try {
      const resp = await api.login(username, password);
      setToken(resp.token);
      setStoredUser(resp.user);
      setUser(resp.user);
      return true;
    } catch (e) {
      setError(e.message || "Login failed");
      return false;
    }
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    setStoredUser(null);
    setUser(null);
  }, []);

  const updateApiUrl = useCallback((url) => {
    persistApiUrl(url);
    setApiUrlState(url.replace(/\/$/, ""));
  }, []);

  return (
    <AuthContext.Provider value={{ user, setUser, login, logout, error, apiUrl, updateApiUrl }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
