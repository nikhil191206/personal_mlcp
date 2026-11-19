// Calls to the local API (proxied by Vite to 127.0.0.1:8765). The browser never holds the Databricks token.

async function request(path, options = {}) {
  let res;
  try {
    res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
  } catch {
    throw Object.assign(new Error("The local API is not answering. Is `npm run dev` still running?"), { detail: "" });
  }
  const type = res.headers.get("content-type") || "";
  if (!res.ok) {
    if ([502, 503, 504].includes(res.status) && !type.includes("json")) {
      throw Object.assign(new Error("The local API is not answering. Is `npm run dev` still running?"), { detail: "" });
    }
    const body = type.includes("json") ? await res.json().catch(() => ({})) : {};
    throw Object.assign(new Error(body.error || `Request failed (${res.status})`), { detail: body.detail || "" });
  }
  return type.includes("json") ? res.json() : res;
}

const post = (path, body) => request(path, { method: "POST", body: JSON.stringify(body ?? {}) });

export const api = {
  health: () => request("/api/health"),
  runs: () => request("/api/runs"),
  run: (id) => request(`/api/runs/${id}`),
  settings: () => request("/api/settings"),
  saveSettings: (body) => post("/api/settings", body),
  facts: () => request("/api/facts"),
  saveFacts: (decisions) => post("/api/facts", { decisions }),
  sources: () => request("/api/sources"),
  setSource: (id, value) => post("/api/sources", { id, value }),
  rerun: () => request("/api/rerun"),
  report: async (runId, fmt) => (await request(`/api/reports/${runId}/${fmt}`, { method: "POST" })).blob(),
  companies: (runId) => request(`/api/companies/${runId}`),
  companyReport: async (runId, id, fmt) => (await request(`/api/companies/${runId}/${id}/report/${fmt}`, { method: "POST" })).blob(),
};
