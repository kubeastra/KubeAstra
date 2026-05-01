const BASE = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, "");

function apiUrl(path: string) {
  return BASE ? `${BASE}${path}` : path;
}

type JsonRequestInit = Omit<RequestInit, "body"> & {
  body?: unknown;
};

async function fetchJson(path: string, init: JsonRequestInit = {}) {
  const headers = new Headers(init.headers);
  let requestBody: BodyInit | undefined;

  if (init.body !== undefined) {
    headers.set("Content-Type", "application/json");
    requestBody = JSON.stringify(init.body);
  }

  const res = await fetch(apiUrl(path), {
    ...init,
    headers,
    body: requestBody,
  });

  if (!res.ok) {
    let message = `HTTP ${res.status}`;
    try {
      const error = await res.json();
      message = error.detail || error.error || message;
    } catch {
      // Fall back to HTTP status when the backend error isn't JSON.
    }
    throw new Error(message);
  }

  return res.json();
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface SSHCredentials {
  host: string;
  username: string;
  password: string;
  port?: number;
}

export interface SSHTarget {
  host: string;
  username: string;
  port: number;
}

export interface HistoryMessage {
  role: "user" | "assistant";
  content: string;
  tool_used?: string;
  result?: Record<string, unknown>;
  error?: string;
  created_at: string;
}

export interface ChatResponse {
  reply: string;
  tool_used: string;
  result: Record<string, unknown> | null;
  error?: string | null;
  timestamp?: number;
  suggested_actions?: Array<{ label: string; command: string; confirm?: boolean }>;
}

export interface ExecuteResponse {
  success: boolean;
  output: string;
  error: string;
}

// ── Chat ──────────────────────────────────────────────────────────────────────

export async function sendChat(
  message: string,
  history: ChatMessage[],
  ssh?: SSHCredentials | null,
  sessionId?: string | null
): Promise<ChatResponse> {
  const body: Record<string, unknown> = { message, history };
  if (ssh) body.ssh = ssh;
  if (sessionId) body.session_id = sessionId;

  const res = await fetch(apiUrl("/api/chat"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

// ── Session history ───────────────────────────────────────────────────────────

export async function getHistory(sessionId: string): Promise<HistoryMessage[]> {
  try {
    const res = await fetch(apiUrl(`/api/sessions/${sessionId}/history`));
    if (!res.ok) return [];
    const data = await res.json();
    return data.messages ?? [];
  } catch {
    return [];
  }
}

export async function clearHistory(sessionId: string): Promise<void> {
  try {
    await fetch(apiUrl(`/api/sessions/${sessionId}/history`), { method: "DELETE" });
  } catch {
    // best-effort
  }
}

// ── SSH target ────────────────────────────────────────────────────────────────

export async function getSshTarget(sessionId: string): Promise<SSHTarget | null> {
  try {
    const res = await fetch(apiUrl(`/api/sessions/${sessionId}/ssh-target`));
    if (!res.ok) return null;
    const data = await res.json();
    return data.ssh_target ?? null;
  } catch {
    return null;
  }
}

export async function saveSshTarget(
  sessionId: string,
  target: SSHTarget
): Promise<void> {
  try {
    await fetch(apiUrl(`/api/sessions/${sessionId}/ssh-target`), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(target),
    });
  } catch {
    // best-effort
  }
}

export async function deleteSshTarget(sessionId: string): Promise<void> {
  try {
    await fetch(apiUrl(`/api/sessions/${sessionId}/ssh-target`), { method: "DELETE" });
  } catch {
    // best-effort
  }
}

// ── Health ────────────────────────────────────────────────────────────────────

export async function checkHealth() {
  try {
    const res = await fetch(apiUrl("/api/health"));
    return res.ok ? res.json() : null;
  } catch {
    return null;
  }
}

// ── Execute (approval gate) ──────────────────────────────────────────────────

export async function executeCommand(
  command: string,
  ssh?: SSHCredentials | null
): Promise<ExecuteResponse> {
  const body: Record<string, unknown> = { command };
  if (ssh) body.ssh = ssh;
  const res = await fetch(apiUrl("/api/execute"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

// ── Legacy form dashboard client ─────────────────────────────────────────────

export const api = {
  analyze: (body: unknown) => fetchJson("/api/analyze", { method: "POST", body }),
  fix: (body: unknown) => fetchJson("/api/fix", { method: "POST", body }),
  categories: () => fetchJson("/api/categories"),
  runbook: (body: unknown) => fetchJson("/api/runbook", { method: "POST", body }),
  report: (body: unknown) => fetchJson("/api/report", { method: "POST", body }),
  summary: (body: unknown) => fetchJson("/api/summary", { method: "POST", body }),
  investigate: (body: unknown) => fetchJson("/api/investigate", { method: "POST", body }),
  pods: (body: unknown) => fetchJson("/api/pods", { method: "POST", body }),
  describe: (body: unknown) => fetchJson("/api/describe", { method: "POST", body }),
  logs: (body: unknown) => fetchJson("/api/logs", { method: "POST", body }),
  events: (body: unknown) => fetchJson("/api/events", { method: "POST", body }),
  find: (body: unknown) => fetchJson("/api/find", { method: "POST", body }),
  deployment: (body: unknown) => fetchJson("/api/deployment", { method: "POST", body }),
  service: (body: unknown) => fetchJson("/api/service", { method: "POST", body }),
  endpoints: (body: unknown) => fetchJson("/api/endpoints", { method: "POST", body }),
  rolloutStatus: (body: unknown) => fetchJson("/api/rollout-status", { method: "POST", body }),
  contexts: () => fetchJson("/api/contexts"),
  currentContext: () => fetchJson("/api/contexts/current"),
  switchContext: (contextName: string) =>
    fetchJson("/api/contexts/switch", { method: "POST", body: { context_name: contextName } }),
  addContext: (body: unknown) => fetchJson("/api/contexts/add", { method: "POST", body }),
  restart: (body: unknown) => fetchJson("/api/restart", { method: "POST", body }),
  scale: (body: unknown) => fetchJson("/api/scale", { method: "POST", body }),
  deletePod: (body: unknown) => fetchJson("/api/delete-pod", { method: "POST", body }),
  exec: (body: unknown) => fetchJson("/api/exec", { method: "POST", body }),
  patch: (body: unknown) => fetchJson("/api/patch", { method: "POST", body }),
};
