const DEFAULT_API_URL = (typeof import.meta !== "undefined" && import.meta.env && import.meta.env.VITE_API_URL) || "http://localhost:8000";

export function getApiUrl() {
  return localStorage.getItem("codegraph_api_url") || DEFAULT_API_URL;
}

export function setApiUrl(url) {
  localStorage.setItem("codegraph_api_url", url.replace(/\/$/, ""));
}

export function getToken() {
  return localStorage.getItem("codegraph_token");
}

export function setToken(token) {
  if (token) localStorage.setItem("codegraph_token", token);
  else localStorage.removeItem("codegraph_token");
}

export function getStoredUser() {
  try {
    return JSON.parse(localStorage.getItem("codegraph_user") || "null");
  } catch {
    return null;
  }
}

export function setStoredUser(user) {
  if (user) localStorage.setItem("codegraph_user", JSON.stringify(user));
  else localStorage.removeItem("codegraph_user");
}

export function getSelectedProjectId() {
  const raw = localStorage.getItem("codegraph_project_id");
  return raw ? Number(raw) : null;
}

export function setSelectedProjectId(id) {
  if (id === null || id === undefined) localStorage.removeItem("codegraph_project_id");
  else localStorage.setItem("codegraph_project_id", String(id));
}

class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

/** Authenticated fetch wrapper. Throws ApiError on non-2xx.
 * Pass a FormData instance as `body` (e.g. for file uploads) and it will be
 * sent as multipart/form-data instead of JSON. */
export async function apiFetch(path, { method = "GET", body, params } = {}) {
  const url = new URL(getApiUrl() + path);
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, v);
    });
  }

  const isFormData = typeof FormData !== "undefined" && body instanceof FormData;
  const headers = isFormData ? {} : { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(url.toString(), {
    method,
    headers,
    body: body ? (isFormData ? body : JSON.stringify(body)) : undefined,
  });

  if (res.status === 401) {
    setToken(null);
    setStoredUser(null);
    throw new ApiError(401, "Session expired. Please log in again.");
  }

  let data = null;
  try {
    data = await res.json();
  } catch {
    /* no body */
  }

  if (!res.ok) {
    throw new ApiError(res.status, data?.detail || `Request failed (${res.status})`);
  }
  return data;
}

export const api = {
  login: (username, password) => apiFetch("/api/auth/login", { method: "POST", body: { username, password } }),
  me: () => apiFetch("/api/auth/me"),

  graph: (projectId, type) => apiFetch("/api/graph", { params: { project_id: projectId, type } }),
  stats: (projectId) => apiFetch("/api/stats", { params: { project_id: projectId } }),
  search: (projectId, q, limit) => apiFetch("/api/search", { params: { project_id: projectId, q, limit } }),
  edges: (projectId, params) => apiFetch("/api/edges", { params: { project_id: projectId, ...params } }),

  adminListUsers: () => apiFetch("/api/admin/users"),
  adminCreateUser: (username, password, role) =>
    apiFetch("/api/admin/users", { method: "POST", body: { username, password, role } }),
  adminUpdateUser: (id, patch) => apiFetch(`/api/admin/users/${id}`, { method: "PATCH", body: patch }),
  adminRegenerateKey: (id) => apiFetch(`/api/admin/users/${id}/regenerate-key`, { method: "POST" }),
  adminDeleteUser: (id) => apiFetch(`/api/admin/users/${id}`, { method: "DELETE" }),

  // ---- projects ----
  listProjects: () => apiFetch("/api/projects"),
  getProject: (id) => apiFetch(`/api/projects/${id}`),
  createProject: (name, description) =>
    apiFetch("/api/projects", { method: "POST", body: { name, description } }),
  updateProject: (id, patch) => apiFetch(`/api/projects/${id}`, { method: "PATCH", body: patch }),
  deleteProject: (id) => apiFetch(`/api/projects/${id}`, { method: "DELETE" }),
  uploadProjectZip: (id, file, { replace = true } = {}) => {
    const form = new FormData();
    form.append("file", file);
    form.append("replace", replace ? "true" : "false");
    return apiFetch(`/api/projects/${id}/upload`, { method: "POST", body: form });
  },
  indexProject: (id) => apiFetch(`/api/projects/${id}/index`, { method: "POST" }),
};

export { ApiError };
