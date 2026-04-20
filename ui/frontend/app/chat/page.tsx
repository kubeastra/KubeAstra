"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import ResultCard from "../../components/ResultCard";
import {
  sendChat,
  checkHealth,
  getHistory,
  clearHistory,
  getSshTarget,
  saveSshTarget,
  deleteSshTarget,
  type ChatMessage,
  type SSHCredentials,
  type SSHTarget,
  type HistoryMessage,
} from "../../lib/api";

/* ── types ───────────────────────────────────────────────────── */

interface Message {
  id: string;
  role: "user" | "assistant";
  text: string;
  tool?: string;
  result?: Record<string, unknown> | null;
  error?: string | null;
  loading?: boolean;
  viaSSH?: boolean;
}

interface Health {
  ai_enabled: boolean;
  kubectl_available: boolean;
}

/* ── example prompts ─────────────────────────────────────────── */

const EXAMPLES = [
  "My pod is stuck in CrashLoopBackOff — paste the error here",
  "List all pods in the production namespace",
  "Investigate pod api-service-7d4f9b in namespace default",
  "Show me recent events in the staging namespace",
  "What clusters do I have configured?",
  "Generate a runbook for OOMKilled errors",
];

/* ── helpers ─────────────────────────────────────────────────── */

function uid() {
  return Math.random().toString(36).slice(2);
}

function getOrCreateSessionId(): string {
  if (typeof window === "undefined") return uid();
  let sid = localStorage.getItem("k8s_session_id");
  if (!sid) {
    sid = uid() + uid();
    localStorage.setItem("k8s_session_id", sid);
  }
  return sid;
}

function historyToMessages(history: HistoryMessage[]): Message[] {
  return history.map((h) => ({
    id: uid(),
    role: h.role,
    text: h.content,
    tool: h.tool_used,
    result: h.result ?? null,
    error: h.error ?? null,
  }));
}

/* ── App logo components ─────────────────────────────────────── */

/** Circular "K" emblem for the app header */
function AppEmblem({ size = 32 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 44 44" fill="none" xmlns="http://www.w3.org/2000/svg">
      {/* Green circle */}
      <circle cx="22" cy="22" r="22" fill="var(--brand)" />
      {/* Stylised S path in dark/black */}
      <path
        d="M30 15H19a4 4 0 0 0 0 8h6a4 4 0 0 1 0 8H14"
        stroke="#0a0a0a"
        strokeWidth="3.5"
        strokeLinecap="round"
        fill="none"
      />
    </svg>
  );
}

/** App wordmark: emblem + "K8s" + "Ops" in brand color */
function AppWordmark() {
  return (
    <div className="flex items-center gap-2.5">
      <AppEmblem size={30} />
      <span className="text-lg font-bold tracking-tight leading-none select-none" style={{ letterSpacing: "-0.02em" }}>
        <span style={{ color: "var(--text-primary)" }}>K8s</span>
        <span style={{ color: "var(--brand)" }}>Ops</span>
      </span>
    </div>
  );
}

/* ── SSH reconnect banner ────────────────────────────────────── */

interface ReconnectBannerProps {
  target: SSHTarget;
  onReconnect: (password: string) => void;
  onDismiss: () => void;
}

function ReconnectBanner({ target, onReconnect, onDismiss }: ReconnectBannerProps) {
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  const handleReconnect = async () => {
    if (!password) return;
    setBusy(true);
    onReconnect(password);
  };

  return (
    <div
      className="shrink-0 border-b px-4 py-3"
      style={{ background: "var(--brand-dim)", borderColor: "var(--brand-border)" }}
    >
      <div className="max-w-3xl mx-auto flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-2 text-sm flex-1 min-w-0" style={{ color: "var(--brand)" }}>
          <span className="w-2 h-2 rounded-full shrink-0" style={{ background: "var(--brand)" }} />
          <span className="truncate">
            Previous SSH session:{" "}
            <span className="font-mono font-medium">{target.username}@{target.host}</span>
          </span>
        </div>
        <div className="flex items-center gap-2">
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleReconnect()}
            placeholder="Password to reconnect"
            autoFocus
            className="app-input rounded-lg px-3 py-1.5 text-sm w-44"
          />
          <button
            onClick={handleReconnect}
            disabled={!password || busy}
            className="app-btn-primary px-3 py-1.5 rounded-lg text-sm font-medium"
          >
            {busy ? "Connecting…" : "Reconnect"}
          </button>
          <button
            onClick={onDismiss}
            className="app-btn-ghost px-3 py-1.5 rounded-lg text-sm"
          >
            Dismiss
          </button>
        </div>
      </div>
    </div>
  );
}

/* ── SSH panel ───────────────────────────────────────────────── */

interface SSHPanelProps {
  onConnect: (creds: SSHCredentials) => void;
  onDisconnect: () => void;
  connected: SSHCredentials | null;
}

function SSHPanel({ onConnect, onDisconnect, connected }: SSHPanelProps) {
  const [open, setOpen] = useState(false);
  const [host, setHost] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [port, setPort] = useState("22");
  const [testStatus, setTestStatus] = useState<"idle" | "testing" | "ok" | "err">("idle");
  const [testError, setTestError] = useState("");

  const handleConnect = async () => {
    if (!host.trim() || !username.trim() || !password) return;
    const creds: SSHCredentials = {
      host: host.trim(),
      username: username.trim(),
      password,
      port: parseInt(port, 10) || 22,
    };

    setTestStatus("testing");
    setTestError("");
    try {
      const res = await sendChat("list clusters", [], creds);
      if (res.error && res.tool_used === "error") {
        setTestStatus("err");
        setTestError(res.error);
        return;
      }
      setTestStatus("ok");
      onConnect(creds);
      setOpen(false);
    } catch (e) {
      setTestStatus("err");
      setTestError(String(e));
    }
  };

  const handleDisconnect = () => {
    onDisconnect();
    setTestStatus("idle");
    setTestError("");
    setPassword("");
  };

  if (connected) {
    return (
      <div className="flex items-center gap-2 text-xs">
        <span
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-xs font-medium"
          style={{ background: "var(--brand-dim)", borderColor: "var(--brand-border)", color: "var(--brand)" }}
        >
          <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: "var(--brand)" }} />
          SSH: {connected.username}@{connected.host}
        </span>
        <button
          onClick={handleDisconnect}
          className="app-btn-ghost px-2.5 py-1 rounded-lg text-xs hover:!text-red-400 hover:!border-red-700/50"
        >
          Disconnect
        </button>
      </div>
    );
  }

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="app-btn-ghost flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs"
      >
        <svg xmlns="http://www.w3.org/2000/svg" className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <rect x="2" y="2" width="20" height="8" rx="2" />
          <rect x="2" y="14" width="20" height="8" rx="2" />
          <line x1="6" y1="6" x2="6.01" y2="6" />
          <line x1="6" y1="18" x2="6.01" y2="18" />
        </svg>
        SSH Cluster
      </button>

      {open && (
        <div
          className="absolute right-0 top-9 z-50 w-80 rounded-2xl shadow-2xl p-4 flex flex-col gap-3"
          style={{ background: "var(--bg-surface-2)", border: "1px solid var(--border)" }}
        >
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
              Connect to Remote Cluster
            </h3>
            <button
              onClick={() => setOpen(false)}
              className="text-lg leading-none transition"
              style={{ color: "var(--text-muted)" }}
            >
              &times;
            </button>
          </div>

          <p className="text-xs" style={{ color: "var(--text-muted)" }}>
            SSH into a kubeadm master node. All kubectl commands will run remotely for this session.
          </p>

          <div className="flex gap-2">
            <div className="flex-1 flex flex-col gap-1">
              <label className="text-xs" style={{ color: "var(--text-muted)" }}>Hostname / IP</label>
              <input type="text" value={host} onChange={(e) => setHost(e.target.value)}
                placeholder="10.0.1.5" className="app-input rounded-lg px-3 py-1.5 text-sm w-full" />
            </div>
            <div className="w-16 flex flex-col gap-1">
              <label className="text-xs" style={{ color: "var(--text-muted)" }}>Port</label>
              <input type="number" value={port} onChange={(e) => setPort(e.target.value)}
                className="app-input rounded-lg px-3 py-1.5 text-sm w-full" />
            </div>
          </div>

          <div className="flex flex-col gap-1">
            <label className="text-xs" style={{ color: "var(--text-muted)" }}>Username</label>
            <input type="text" value={username} onChange={(e) => setUsername(e.target.value)}
              placeholder="ubuntu" className="app-input rounded-lg px-3 py-1.5 text-sm w-full" />
          </div>

          <div className="flex flex-col gap-1">
            <label className="text-xs" style={{ color: "var(--text-muted)" }}>Password</label>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••" className="app-input rounded-lg px-3 py-1.5 text-sm w-full" />
          </div>

          {testStatus === "err" && (
            <p className="text-xs rounded-lg px-3 py-2" style={{ color: "var(--danger)", background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.2)" }}>
              {testError || "Connection failed"}
            </p>
          )}

          <button
            onClick={handleConnect}
            disabled={!host.trim() || !username.trim() || !password || testStatus === "testing"}
            className="app-btn-primary mt-1 w-full py-2 rounded-xl text-sm font-medium flex items-center justify-center gap-2"
          >
            {testStatus === "testing" ? (
              <>
                <span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Testing connection…
              </>
            ) : "Connect & Test"}
          </button>
        </div>
      )}
    </div>
  );
}

/* ── main component ──────────────────────────────────────────── */

export default function ChatPage() {
  const [sessionId] = useState<string>(() => getOrCreateSessionId());
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [health, setHealth] = useState<Health | null>(null);
  const [healthLoaded, setHealthLoaded] = useState(false);
  const [sshCreds, setSshCreds] = useState<SSHCredentials | null>(null);
  const [pendingReconnect, setPendingReconnect] = useState<SSHTarget | null>(null);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  // edit state
  const [editingIdx, setEditingIdx] = useState<number | null>(null);
  const [editText, setEditText] = useState("");
  const [copiedIdx, setCopiedIdx] = useState<number | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    checkHealth().then((h) => {
      if (h) setHealth(h as Health);
      setHealthLoaded(true);
    });
    getHistory(sessionId).then((history) => {
      if (history.length > 0) setMessages(historyToMessages(history));
      setHistoryLoaded(true);
    });
    getSshTarget(sessionId).then((target) => {
      if (target) setPendingReconnect(target);
    });
  }, [sessionId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const autoResize = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 200) + "px";
  };

  const handleConnect = useCallback((creds: SSHCredentials) => {
    setSshCreds(creds);
    setPendingReconnect(null);
    saveSshTarget(sessionId, { host: creds.host, username: creds.username, port: creds.port ?? 22 });
    setMessages((prev) => [
      ...prev,
      { id: uid(), role: "assistant", text: `Connected to **${creds.username}@${creds.host}** via SSH. All kubectl commands will now run on that cluster.` },
    ]);
  }, [sessionId]);

  const handleDisconnect = useCallback(() => {
    setSshCreds(null);
    deleteSshTarget(sessionId);
    setMessages((prev) => [
      ...prev,
      { id: uid(), role: "assistant", text: "SSH session closed. Reverting to local cluster." },
    ]);
  }, [sessionId]);

  const handleReconnectFromBanner = useCallback(async (password: string) => {
    if (!pendingReconnect) return;
    const creds: SSHCredentials = { ...pendingReconnect, password };
    try {
      const res = await sendChat("list clusters", [], creds, sessionId);
      if (res.error && res.tool_used === "error") {
        deleteSshTarget(sessionId);
        setPendingReconnect(null);
        return;
      }
      setSshCreds(creds);
      setPendingReconnect(null);
      setMessages((prev) => [
        ...prev,
        { id: uid(), role: "assistant", text: `Reconnected to **${creds.username}@${creds.host}** via SSH.` },
      ]);
    } catch {
      deleteSshTarget(sessionId);
      setPendingReconnect(null);
    }
  }, [pendingReconnect, sessionId]);

  const submit = useCallback(async (text: string) => {
    if (!text.trim() || loading) return;

    const userMsg: Message = { id: uid(), role: "user", text: text.trim(), viaSSH: !!sshCreds };
    const thinkingMsg: Message = { id: uid(), role: "assistant", text: "", loading: true };

    setMessages((prev) => [...prev, userMsg, thinkingMsg]);
    setInput("");
    setLoading(true);
    if (textareaRef.current) textareaRef.current.style.height = "auto";

    const history: ChatMessage[] = messages
      .filter((m) => !m.loading)
      .slice(-10)
      .map((m) => ({ role: m.role, content: m.text }));

    try {
      const res = await sendChat(text.trim(), history, sshCreds, sessionId);
      setMessages((prev) =>
        prev.map((m) =>
          m.id === thinkingMsg.id
            ? { ...m, loading: false, text: res.reply, tool: res.tool_used, result: res.result, error: res.error }
            : m
        )
      );
    } catch (err) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === thinkingMsg.id
            ? { ...m, loading: false, text: "Failed to reach the backend. Is it running?", error: String(err) }
            : m
        )
      );
    } finally {
      setLoading(false);
    }
  }, [loading, messages, sshCreds, sessionId]);

  const handleCopy = useCallback((text: string, idx: number) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopiedIdx(idx);
      setTimeout(() => setCopiedIdx(null), 1500);
    });
  }, []);

  const handleEditStart = useCallback((idx: number, text: string) => {
    setEditingIdx(idx);
    setEditText(text);
  }, []);

  const handleEditCancel = useCallback(() => {
    setEditingIdx(null);
    setEditText("");
  }, []);

  const handleEditSubmit = useCallback(async (idx: number) => {
    const text = editText.trim();
    if (!text || loading) return;
    // Remove the original message and everything after it, then re-run
    setMessages((prev) => prev.slice(0, idx));
    setEditingIdx(null);
    setEditText("");
    await submit(text);
  }, [editText, loading, submit]);

  const handleNewChat = useCallback(() => {
    setMessages([]);
    clearHistory(sessionId);
  }, [sessionId]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit(input);
    }
  };

  const isEmpty = historyLoaded && messages.length === 0;

  return (
    <div className="flex flex-col h-screen" style={{ background: "var(--bg-base)", color: "var(--text-primary)" }}>

      {/* ── header ── */}
      <header
        className="shrink-0 px-6 py-4 flex items-center justify-between"
        style={{ borderBottom: "1px solid var(--border)", background: "var(--bg-surface)" }}
      >
        {/* Left: app wordmark + product label */}
        <div className="flex items-center gap-4">
          <AppWordmark />
          {/* Divider */}
          <span className="w-px h-6 shrink-0" style={{ background: "var(--border)" }} />
          <div>
            <p className="text-xs font-medium leading-none" style={{ color: "var(--text-secondary)" }}>
              K8s DevOps Assistant
            </p>
            <p className="text-[10px] mt-0.5 leading-none" style={{ color: "var(--text-muted)" }}>
              Paste an error or ask a question
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3 text-xs">
          <SSHPanel connected={sshCreds} onConnect={handleConnect} onDisconnect={handleDisconnect} />

          {!healthLoaded ? (
            /* Still loading — brief spinner dot */
            <span className="flex items-center gap-1.5 text-xs" style={{ color: "var(--text-muted)" }}>
              <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: "var(--border)" }} />
              Checking…
            </span>
          ) : !health ? (
            /* Backend unreachable */
            <span className="flex items-center gap-1.5 text-xs" style={{ color: "var(--danger)" }}>
              <span className="w-1.5 h-1.5 rounded-full" style={{ background: "var(--danger)" }} />
              Backend offline
            </span>
          ) : (
            <>
              {/* kubectl: green = cluster active, yellow = no cluster configured */}
              <span
                className="flex items-center gap-1.5"
                title={health.kubectl_available ? "kubectl connected" : "No cluster configured — use SSH Cluster to connect"}
                style={{ color: health.kubectl_available ? "var(--success)" : "var(--warning)" }}
              >
                <span className="w-1.5 h-1.5 rounded-full" style={{ background: health.kubectl_available ? "var(--success)" : "var(--warning)" }} />
                {health.kubectl_available ? "kubectl" : "no cluster"}
              </span>
              <span className="flex items-center gap-1.5" style={{ color: health.ai_enabled ? "var(--brand)" : "var(--text-muted)" }}>
                <span className="w-1.5 h-1.5 rounded-full" style={{ background: health.ai_enabled ? "var(--brand)" : "var(--border)" }} />
                AI
              </span>
            </>
          )}

          {messages.length > 0 && (
            <button
              onClick={handleNewChat}
              className="app-btn-ghost ml-2 px-3 py-1 rounded-lg text-xs"
            >
              New chat
            </button>
          )}
        </div>
      </header>

      {/* ── SSH reconnect banner ── */}
      {pendingReconnect && !sshCreds && (
        <ReconnectBanner
          target={pendingReconnect}
          onReconnect={handleReconnectFromBanner}
          onDismiss={() => {
            setPendingReconnect(null);
            deleteSshTarget(sessionId);
          }}
        />
      )}

      {/* ── messages ── */}
      <div className="flex-1 overflow-y-auto px-4 py-6">
        <div className="max-w-3xl mx-auto space-y-6">

          {!historyLoaded && (
            <div className="flex items-center justify-center h-32 text-sm" style={{ color: "var(--text-muted)" }}>
              Loading history…
            </div>
          )}

          {isEmpty && (
            <div className="flex flex-col items-center justify-center h-full min-h-[60vh] text-center gap-6">
              <div>
                {/* App emblem */}
                <div className="mx-auto mb-5 w-fit">
                  <AppEmblem size={60} />
                </div>
                <h2 className="text-2xl font-semibold" style={{ color: "var(--text-primary)" }}>
                  How can I help you today?
                </h2>
                <p className="mt-2 text-sm max-w-md mx-auto" style={{ color: "var(--text-secondary)" }}>
                  Ask about Kubernetes errors, pod status, logs, or events.
                  I&apos;ll route to the right tool automatically.
                </p>
                {!sshCreds && (
                  <p className="mt-2 text-xs" style={{ color: "var(--text-muted)" }}>
                    Connect to a remote cluster via the{" "}
                    <span style={{ color: "var(--brand)" }}>SSH Cluster</span> button above.
                  </p>
                )}
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 w-full max-w-xl">
                {EXAMPLES.map((ex) => (
                  <button
                    key={ex}
                    onClick={() => submit(ex)}
                    className="text-left text-xs rounded-xl px-4 py-3 transition"
                    style={{
                      color: "var(--text-secondary)",
                      background: "var(--bg-surface-2)",
                      border: "1px solid var(--border)",
                    }}
                    onMouseEnter={(e) => {
                      (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--brand-border)";
                      (e.currentTarget as HTMLButtonElement).style.color = "var(--text-primary)";
                    }}
                    onMouseLeave={(e) => {
                      (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--border)";
                      (e.currentTarget as HTMLButtonElement).style.color = "var(--text-secondary)";
                    }}
                  >
                    {ex}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* message list */}
          {messages.map((m, idx) => (
            <div key={m.id} className={`flex gap-3 group ${m.role === "user" ? "flex-row-reverse" : "flex-row"}`}>

              {/* avatar */}
              <div
                className="shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold"
                style={m.role === "user"
                  ? { background: "var(--brand)", color: "#000" }
                  : { background: "var(--bg-surface-3)", color: "var(--text-secondary)", border: "1px solid var(--border)" }
                }
              >
                {m.role === "user" ? "U" : "⎈"}
              </div>

              <div className={`flex flex-col gap-2 max-w-[85%] ${m.role === "user" ? "items-end" : "items-start"}`}>

                {m.role === "user" && m.viaSSH && sshCreds && (
                  <span className="text-[10px] px-1" style={{ color: "var(--brand)" }}>
                    via SSH · {sshCreds.host}
                  </span>
                )}

                {/* For assistant messages with a result card, show the card first so
                    the summary text lands at the bottom after auto-scroll. */}
                {m.role === "assistant" && !m.loading && m.result && m.tool && m.tool !== "none" && (
                  <div className="w-full">
                    <ResultCard tool={m.tool} result={m.result} />
                  </div>
                )}

                {/* ── User message ── */}
                {m.role === "user" && (
                  editingIdx === idx ? (
                    /* Inline edit textarea */
                    <div className="flex flex-col gap-2 w-full max-w-xl">
                      <textarea
                        className="rounded-xl px-4 py-3 text-sm leading-relaxed resize-none"
                        style={{
                          background: "var(--bg-surface-2)",
                          color: "var(--text-primary)",
                          border: "1px solid var(--brand)",
                          outline: "none",
                          minHeight: "80px",
                          maxHeight: "300px",
                        }}
                        value={editText}
                        autoFocus
                        onChange={(e) => setEditText(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleEditSubmit(idx); }
                          if (e.key === "Escape") handleEditCancel();
                        }}
                      />
                      <div className="flex gap-2 justify-end">
                        <button
                          onClick={handleEditCancel}
                          className="px-3 py-1 rounded-lg text-xs"
                          style={{ color: "var(--text-muted)", border: "1px solid var(--border)" }}
                        >
                          Cancel
                        </button>
                        <button
                          onClick={() => handleEditSubmit(idx)}
                          disabled={!editText.trim() || loading}
                          className="px-3 py-1 rounded-lg text-xs font-medium"
                          style={{ background: "var(--brand)", color: "#000" }}
                        >
                          Send
                        </button>
                      </div>
                    </div>
                  ) : (
                    /* Icon-only actions left of bubble, bubble to the right */
                    <div className="flex items-center gap-1.5">
                      <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity duration-150">
                        <button
                          title={copiedIdx === idx ? "Copied!" : "Copy"}
                          onClick={() => handleCopy(m.text, idx)}
                          className="w-7 h-7 rounded-lg flex items-center justify-center transition-colors"
                          style={{
                            background: "var(--bg-surface-3)",
                            border: "1px solid var(--border)",
                            color: copiedIdx === idx ? "var(--success)" : "var(--text-muted)",
                          }}
                        >
                          {copiedIdx === idx ? (
                            <svg width="13" height="13" viewBox="0 0 16 16" fill="none"><path d="M2 8l4 4 8-8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
                          ) : (
                            <svg width="13" height="13" viewBox="0 0 16 16" fill="none"><rect x="5" y="5" width="9" height="9" rx="1.5" stroke="currentColor" strokeWidth="1.5"/><path d="M11 5V3.5A1.5 1.5 0 009.5 2h-6A1.5 1.5 0 002 3.5v6A1.5 1.5 0 003.5 11H5" stroke="currentColor" strokeWidth="1.5"/></svg>
                          )}
                        </button>
                        <button
                          title="Edit and resend"
                          onClick={() => handleEditStart(idx, m.text)}
                          className="w-7 h-7 rounded-lg flex items-center justify-center transition-colors"
                          style={{
                            background: "var(--bg-surface-3)",
                            border: "1px solid var(--border)",
                            color: "var(--text-muted)",
                          }}
                        >
                          <svg width="13" height="13" viewBox="0 0 16 16" fill="none"><path d="M11.5 2.5a1.5 1.5 0 012.12 2.12L5 13.24l-3 .76.76-3L11.5 2.5z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
                        </button>
                      </div>
                      <div className="rounded-2xl rounded-tr-sm px-4 py-3 text-sm leading-relaxed"
                        style={{ background: "var(--brand)", color: "#000" }}
                      >
                        <p className="whitespace-pre-wrap">{m.text}</p>
                      </div>
                    </div>
                  )
                )}

                {/* ── Assistant bubble ── */}
                {m.role === "assistant" && (
                  <div className="rounded-2xl rounded-tl-sm px-4 py-3 text-sm leading-relaxed"
                    style={{ background: "var(--bg-surface-2)", color: "var(--text-primary)", border: "1px solid var(--border)" }}
                  >
                    {m.loading ? (
                      <span className="flex items-center gap-2" style={{ color: "var(--text-muted)" }}>
                        <span className="inline-block w-2 h-2 rounded-full animate-bounce [animation-delay:-0.3s]" style={{ background: "var(--brand)" }} />
                        <span className="inline-block w-2 h-2 rounded-full animate-bounce [animation-delay:-0.15s]" style={{ background: "var(--brand)" }} />
                        <span className="inline-block w-2 h-2 rounded-full animate-bounce" style={{ background: "var(--brand)" }} />
                      </span>
                    ) : (
                      <p className="whitespace-pre-wrap">{m.text}</p>
                    )}
                  </div>
                )}

                {m.error && (
                  <p className="text-xs px-1" style={{ color: "var(--danger)" }}>{m.error}</p>
                )}
              </div>
            </div>
          ))}

          <div ref={bottomRef} />
        </div>
      </div>

      {/* ── input bar ── */}
      <div
        className="shrink-0 px-4 py-4"
        style={{ borderTop: "1px solid var(--border)", background: "var(--bg-surface)" }}
      >
        <div className="max-w-3xl mx-auto">
          {sshCreds && (
            <div className="flex items-center gap-1.5 text-xs mb-2 px-1" style={{ color: "var(--brand)" }}>
              <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: "var(--brand)" }} />
              Sending to <span className="font-medium">{sshCreds.username}@{sshCreds.host}</span> via SSH
            </div>
          )}
          <div
            className="flex items-end gap-3 rounded-2xl px-4 py-3 transition-all"
            style={{
              background: "var(--bg-surface-3)",
              border: `1px solid ${sshCreds ? "var(--brand-border)" : "var(--border)"}`,
            }}
            onFocusCapture={(e) => {
              (e.currentTarget as HTMLDivElement).style.borderColor = sshCreds ? "var(--brand)" : "var(--brand-border)";
            }}
            onBlurCapture={(e) => {
              (e.currentTarget as HTMLDivElement).style.borderColor = sshCreds ? "var(--brand-border)" : "var(--border)";
            }}
          >
            <textarea
              ref={textareaRef}
              rows={1}
              value={input}
              onChange={(e) => { setInput(e.target.value); autoResize(); }}
              onKeyDown={handleKeyDown}
              placeholder={
                sshCreds
                  ? `Ask about ${sshCreds.host}… (Enter to send)`
                  : "Paste an error, describe an issue, or ask a question… (Enter to send, Shift+Enter for new line)"
              }
              disabled={loading}
              className="flex-1 bg-transparent resize-none outline-none text-sm max-h-[200px] disabled:opacity-50"
              style={{ color: "var(--text-primary)" }}
            />
            <button
              onClick={() => submit(input)}
              disabled={!input.trim() || loading}
              className="app-btn-primary shrink-0 w-9 h-9 rounded-xl flex items-center justify-center"
              aria-label="Send"
            >
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4">
                <path d="M3.478 2.405a.75.75 0 00-.926.94l2.432 7.905H13.5a.75.75 0 010 1.5H4.984l-2.432 7.905a.75.75 0 00.926.94 60.519 60.519 0 0018.445-8.986.75.75 0 000-1.218A60.517 60.517 0 003.478 2.405z" />
              </svg>
            </button>
          </div>
          <p className="text-center text-xs mt-2" style={{ color: "var(--text-muted)" }}>
            No tool selection needed — just describe the problem naturally.
          </p>
        </div>
      </div>
    </div>
  );
}
