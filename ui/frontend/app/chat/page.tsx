"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import ResultCard from "../../components/ResultCard";
import UserMessage from "../../components/astra/UserMessage";
import AstraMessage from "../../components/astra/AstraMessage";
import ReasoningBubble, { type ToolStep } from "../../components/astra/ReasoningBubble";
import RootCauseCard from "../../components/astra/RootCauseCard";
import IntentBar from "../../components/astra/IntentBar";
import ApprovalOverlay from "../../components/astra/ApprovalOverlay";
import {
  sendChat,
  checkHealth,
  getHistory,
  clearHistory,
  getSshTarget,
  saveSshTarget,
  deleteSshTarget,
  executeCommand,
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
  suggestedActions?: Array<{ label: string; command: string; confirm?: boolean }>;
}

interface Health {
  ai_enabled: boolean;
  kubectl_available: boolean;
}

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

function formatTime(): string {
  const d = new Date();
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
}

/** Map tool_used to reasoning steps */
function toolToSteps(tool: string, result: Record<string, unknown> | null): ToolStep[] {
  const steps: ToolStep[] = [];
  if (tool === "investigate_pod" || tool === "investigate_workload") {
    steps.push({ tool: "kubectl", status: "done", result: "pod status retrieved" });
    if (result?.logs || result?.current_logs) steps.push({ tool: "logs", status: "done", result: "log tail captured" });
    if (result?.events) steps.push({ tool: "events", status: "done", result: "events scanned" });
    if (result?.describe_highlights) steps.push({ tool: "describe", status: "done", result: "highlights extracted" });
    steps.push({ tool: "ai", status: "done", result: "analysis complete" });
  } else if (tool === "get_pods") {
    steps.push({ tool: "kubectl", status: "done", result: "pods listed" });
  } else if (tool === "get_events") {
    steps.push({ tool: "events", status: "done", result: "events fetched" });
  } else if (tool === "get_pod_logs") {
    steps.push({ tool: "logs", status: "done", result: "logs retrieved" });
  } else if (tool === "analyze_error") {
    steps.push({ tool: "ai", status: "done", result: "error analyzed" });
  } else if (tool) {
    steps.push({ tool: tool, status: "done" });
  }
  return steps;
}

/** Extract root-cause data from investigation results */
function extractRootCause(result: Record<string, unknown>) {
  const classification = (result.classification as string) || "";
  const severity = classification.toLowerCase().includes("critical") ? "critical" as const
    : classification.toLowerCase().includes("warn") ? "warning" as const
    : "info" as const;

  const highlights = (result.describe_highlights || {}) as Record<string, unknown>;
  const metrics = [];
  if (highlights.restart_count !== undefined) {
    metrics.push({ label: "Restarts", value: String(highlights.restart_count), color: Number(highlights.restart_count) > 0 ? "#EF4444" : "#64748B" });
  }
  const status = String(result.effective_status || result.status || highlights.state || "");
  if (status) metrics.push({ label: "Status", value: status, color: status.includes("Crash") || status.includes("OOM") ? "#EF4444" : "#34D399" });
  const ready = String(highlights.ready || "");
  if (ready) metrics.push({ label: "Ready", value: ready, color: ready === "True" ? "#34D399" : "#EF4444" });

  // Build evidence string
  const evidenceLines: string[] = [];
  if (result.current_logs) evidenceLines.push("# Current Logs", String(result.current_logs).slice(0, 500));
  if (result.previous_logs) evidenceLines.push("", "# Previous Logs", String(result.previous_logs).slice(0, 300));

  const pod = String(result.pod_name || result.pod || result.name || "");
  const ns = String(result.namespace || "");
  const summary = String(result.ai_analysis || result.analysis || classification || "");

  return { severity, pod, namespace: ns, summary, metrics, evidence: evidenceLines.join("\n"), title: classification || "Investigation Result" };
}

/* ── SSH Panel (collapsible drawer) ──────────────────────────── */

function SSHDrawer({ onConnect, onDisconnect, connected }: {
  onConnect: (creds: SSHCredentials) => void;
  onDisconnect: () => void;
  connected: SSHCredentials | null;
}) {
  const [open, setOpen] = useState(false);
  const [host, setHost] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [port, setPort] = useState("22");
  const [testStatus, setTestStatus] = useState<"idle" | "testing" | "ok" | "err">("idle");
  const [testError, setTestError] = useState("");

  const handleConnect = async () => {
    if (!host.trim() || !username.trim() || !password) return;
    const creds: SSHCredentials = { host: host.trim(), username: username.trim(), password, port: parseInt(port, 10) || 22 };
    setTestStatus("testing");
    setTestError("");
    try {
      const res = await sendChat("list clusters", [], creds);
      if (res.error && res.tool_used === "error") { setTestStatus("err"); setTestError(res.error); return; }
      setTestStatus("ok");
      onConnect(creds);
      setOpen(false);
    } catch (e) { setTestStatus("err"); setTestError(String(e)); }
  };

  if (connected) {
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <span style={{
          fontSize: 10, fontFamily: "var(--mono)", fontWeight: 600, color: "#22D3EE",
          background: "rgba(34,211,238,0.1)", border: "1px solid rgba(34,211,238,0.2)",
          borderRadius: 4, padding: "3px 7px", display: "flex", alignItems: "center", gap: 4,
        }}>
          <span style={{ width: 5, height: 5, borderRadius: "50%", background: "#22D3EE", animation: "blink 2s infinite" }}/>
          SSH: {connected.username}@{connected.host}
        </span>
        <button onClick={() => { onDisconnect(); setTestStatus("idle"); setPassword(""); }}
          style={{ fontSize: 10, color: "#475569", background: "none", border: "1px solid #1A2535", borderRadius: 4, padding: "3px 7px", cursor: "pointer" }}>
          Disconnect
        </button>
      </div>
    );
  }

  return (
    <div style={{ position: "relative" }}>
      <button onClick={() => setOpen(v => !v)}
        style={{ fontSize: 10, color: "#475569", background: "none", border: "1px solid #1A2535", borderRadius: 4, padding: "3px 7px", cursor: "pointer", fontFamily: "var(--mono)" }}>
        SSH Cluster
      </button>
      {open && (
        <div style={{
          position: "absolute", right: 0, top: 32, zIndex: 50, width: 300, padding: 14,
          background: "#0C1220", border: "1px solid rgba(34,211,238,0.2)", borderRadius: 10,
          boxShadow: "0 16px 48px rgba(0,0,0,0.5)", display: "flex", flexDirection: "column", gap: 8,
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: 12, fontWeight: 600, color: "#E2E8F0" }}>Connect to Remote Cluster</span>
            <button onClick={() => setOpen(false)} style={{ background: "none", border: "none", color: "#475569", cursor: "pointer", fontSize: 16 }}>&times;</button>
          </div>
          <div style={{ display: "flex", gap: 6 }}>
            <input value={host} onChange={e => setHost(e.target.value)} placeholder="10.0.1.5"
              style={{ flex: 1, background: "#080D14", border: "1px solid #1A2535", borderRadius: 6, padding: "6px 10px", color: "#E2E8F0", fontSize: 12, outline: "none" }}/>
            <input value={port} onChange={e => setPort(e.target.value)} style={{ width: 50, background: "#080D14", border: "1px solid #1A2535", borderRadius: 6, padding: "6px 10px", color: "#E2E8F0", fontSize: 12, outline: "none" }}/>
          </div>
          <input value={username} onChange={e => setUsername(e.target.value)} placeholder="ubuntu"
            style={{ background: "#080D14", border: "1px solid #1A2535", borderRadius: 6, padding: "6px 10px", color: "#E2E8F0", fontSize: 12, outline: "none" }}/>
          <input type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="••••••••"
            style={{ background: "#080D14", border: "1px solid #1A2535", borderRadius: 6, padding: "6px 10px", color: "#E2E8F0", fontSize: 12, outline: "none" }}/>
          {testStatus === "err" && <div style={{ fontSize: 10, color: "#EF4444", padding: "4px 8px", background: "rgba(239,68,68,0.08)", borderRadius: 4 }}>{testError}</div>}
          <button onClick={handleConnect} disabled={!host.trim() || !username.trim() || !password || testStatus === "testing"}
            style={{ padding: "8px", background: "rgba(34,211,238,0.15)", border: "1px solid rgba(34,211,238,0.3)", borderRadius: 6, color: "#22D3EE", fontSize: 12, fontWeight: 600, cursor: "pointer" }}>
            {testStatus === "testing" ? "Testing…" : "Connect & Test"}
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
  const [loading, setLoading] = useState(false);
  const [health, setHealth] = useState<Health | null>(null);
  const [healthLoaded, setHealthLoaded] = useState(false);
  const [sshCreds, setSshCreds] = useState<SSHCredentials | null>(null);
  const [pendingReconnect, setPendingReconnect] = useState<SSHTarget | null>(null);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const [showOverlay, setShowOverlay] = useState(false);
  const [overlayActions, setOverlayActions] = useState<Array<{ label: string; command: string }>>([]);
  const [overlayResource, setOverlayResource] = useState("");
  const [overlayNamespace, setOverlayNamespace] = useState("");
  // reasoning animation
  const [reasoningSteps, setReasoningSteps] = useState<ToolStep[]>([]);
  const [isThinking, setIsThinking] = useState(false);

  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    checkHealth().then((h) => { if (h) setHealth(h as Health); setHealthLoaded(true); });
    getHistory(sessionId).then((history) => { if (history.length > 0) setMessages(historyToMessages(history)); setHistoryLoaded(true); });
    getSshTarget(sessionId).then((target) => { if (target) setPendingReconnect(target); });
  }, [sessionId]);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, reasoningSteps]);

  const handleConnect = useCallback((creds: SSHCredentials) => {
    setSshCreds(creds);
    setPendingReconnect(null);
    saveSshTarget(sessionId, { host: creds.host, username: creds.username, port: creds.port ?? 22 });
    setMessages(prev => [...prev, { id: uid(), role: "assistant", text: `Connected to **${creds.username}@${creds.host}** via SSH.` }]);
  }, [sessionId]);

  const handleDisconnect = useCallback(() => {
    setSshCreds(null);
    deleteSshTarget(sessionId);
    setMessages(prev => [...prev, { id: uid(), role: "assistant", text: "SSH session closed. Reverting to local cluster." }]);
  }, [sessionId]);

  const handleReconnect = useCallback(async (password: string) => {
    if (!pendingReconnect) return;
    const creds: SSHCredentials = { ...pendingReconnect, password };
    try {
      const res = await sendChat("list clusters", [], creds, sessionId);
      if (res.error && res.tool_used === "error") { deleteSshTarget(sessionId); setPendingReconnect(null); return; }
      setSshCreds(creds); setPendingReconnect(null);
      setMessages(prev => [...prev, { id: uid(), role: "assistant", text: `Reconnected to **${creds.username}@${creds.host}** via SSH.` }]);
    } catch { deleteSshTarget(sessionId); setPendingReconnect(null); }
  }, [pendingReconnect, sessionId]);

  const submit = useCallback(async (text: string) => {
    if (!text.trim() || loading) return;
    const userMsg: Message = { id: uid(), role: "user", text: text.trim(), viaSSH: !!sshCreds };
    const thinkingMsg: Message = { id: uid(), role: "assistant", text: "", loading: true };
    setMessages(prev => [...prev, userMsg, thinkingMsg]);
    setLoading(true);
    setIsThinking(true);

    // Simulate reasoning animation while waiting
    setReasoningSteps([{ tool: "kubectl", status: "running" }]);
    const simTimers: ReturnType<typeof setTimeout>[] = [];
    const simTools = ["kubectl", "logs", "events", "ai"];
    simTools.forEach((t, i) => {
      simTimers.push(setTimeout(() => {
        setReasoningSteps(prev => {
          const next = [...prev];
          if (next[i]) next[i] = { ...next[i], status: "done" };
          if (i + 1 < simTools.length) next[i + 1] = { tool: simTools[i + 1], status: "running" };
          return next;
        });
      }, 800 + i * 700));
    });

    const history: ChatMessage[] = messages.filter(m => !m.loading).slice(-10).map(m => ({ role: m.role, content: m.text }));
    try {
      const res = await sendChat(text.trim(), history, sshCreds, sessionId);
      simTimers.forEach(clearTimeout);
      // Build final reasoning steps from actual result
      const finalSteps = toolToSteps(res.tool_used, res.result);
      setReasoningSteps(finalSteps);
      setIsThinking(false);
      setMessages(prev => prev.map(m =>
        m.id === thinkingMsg.id
          ? { ...m, loading: false, text: res.reply, tool: res.tool_used, result: res.result, error: res.error, suggestedActions: res.suggested_actions }
          : m
      ));
    } catch (err) {
      simTimers.forEach(clearTimeout);
      setReasoningSteps([]);
      setIsThinking(false);
      setMessages(prev => prev.map(m =>
        m.id === thinkingMsg.id
          ? { ...m, loading: false, text: "Failed to reach the backend. Is it running?", error: String(err) }
          : m
      ));
    } finally { setLoading(false); }
  }, [loading, messages, sshCreds, sessionId]);

  const handleNewChat = useCallback(() => {
    setMessages([]);
    setReasoningSteps([]);
    clearHistory(sessionId);
  }, [sessionId]);

  const handleReviewExecute = useCallback((actions: Array<{ label: string; command: string }>, resource: string, ns: string) => {
    setOverlayActions(actions);
    setOverlayResource(resource);
    setOverlayNamespace(ns);
    setShowOverlay(true);
  }, []);

  const handleExecuteConfirm = useCallback(async () => {
    for (const action of overlayActions) {
      try {
        const res = await executeCommand(action.command, sshCreds);
        setMessages(prev => [...prev, {
          id: uid(), role: "assistant",
          text: res.success ? `✓ Executed: \`${action.command}\`\n\n${res.output}` : `✗ Failed: ${res.error}`,
        }]);
      } catch (e) {
        setMessages(prev => [...prev, { id: uid(), role: "assistant", text: `✗ Execution error: ${e}` }]);
      }
    }
  }, [overlayActions, sshCreds]);

  const clusterName = sshCreds ? `${sshCreds.host}` : health?.kubectl_available ? "LOCAL" : "NO CLUSTER";
  const isEmpty = historyLoaded && messages.length === 0;
  const isInvestigation = (tool?: string) => tool === "investigate_pod" || tool === "investigate_workload";

  return (
    <div style={{ width: "100vw", height: "100vh", background: "var(--bg-base)", display: "flex", flexDirection: "column", overflow: "hidden", position: "relative" }}>

      {/* ── Top bar ── */}
      <div style={{
        height: 48, flexShrink: 0, background: "var(--bg-surface)", borderBottom: "1px solid var(--border)",
        display: "flex", alignItems: "center", padding: "0 18px", gap: 12,
      }}>
        <svg viewBox="0 0 20 20" width="18" height="18">
          <polygon points="10,0.5 18.7,5.25 18.7,14.75 10,19.5 1.3,14.75 1.3,5.25"
            fill="none" stroke="#22D3EE" strokeWidth="0.8" opacity="0.4"/>
          <path d="M10,3 L10.7,8.2 L15.4,5.9 L11.5,10 L15.4,14.1 L10.7,11.8 L10,17 L9.3,11.8 L4.6,14.1 L8.5,10 L4.6,5.9 L9.3,8.2 Z"
            fill="#22D3EE" opacity="0.9"/>
        </svg>
        <span style={{ fontSize: 13, fontWeight: 700, color: "#E2E8F0", letterSpacing: "-0.01em" }}>
          Kube<span style={{ color: "#22D3EE" }}>Astra</span>
        </span>
        <div style={{ width: 1, height: 18, background: "var(--border)" }}/>
        <span style={{ fontSize: 10, color: "#475569", fontFamily: "var(--mono)" }}>Astra Intent</span>
        <div style={{ flex: 1 }}/>

        <SSHDrawer connected={sshCreds} onConnect={handleConnect} onDisconnect={handleDisconnect}/>

        {healthLoaded && health && (
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <div style={{ width: 6, height: 6, borderRadius: "50%", background: health.kubectl_available ? "#34D399" : "#FBBF24", boxShadow: health.kubectl_available ? "0 0 5px #34D399" : "none" }}/>
            <span style={{ fontSize: 10, color: "#475569", fontFamily: "var(--mono)" }}>
              {sshCreds ? `${sshCreds.host}` : health.kubectl_available ? "local-cluster" : "no cluster"}
            </span>
          </div>
        )}

        {messages.length > 0 && (
          <button onClick={handleNewChat} style={{ fontSize: 10, color: "#475569", background: "none", border: "1px solid #1A2535", borderRadius: 4, padding: "3px 8px", cursor: "pointer" }}>
            New chat
          </button>
        )}
      </div>

      {/* ── Reconnect banner ── */}
      {pendingReconnect && !sshCreds && (
        <div style={{ padding: "8px 18px", background: "rgba(34,211,238,0.05)", borderBottom: "1px solid rgba(34,211,238,0.15)", display: "flex", alignItems: "center", gap: 8, fontSize: 12 }}>
          <span style={{ color: "#22D3EE" }}>Previous SSH: {pendingReconnect.username}@{pendingReconnect.host}</span>
          <input type="password" placeholder="Password" id="reconnect-pw"
            style={{ background: "#080D14", border: "1px solid #1A2535", borderRadius: 4, padding: "4px 8px", color: "#E2E8F0", fontSize: 11, outline: "none", width: 140 }}
            onKeyDown={e => { if (e.key === "Enter") { handleReconnect((e.target as HTMLInputElement).value); } }}/>
          <button onClick={() => { const el = document.getElementById("reconnect-pw") as HTMLInputElement; if (el) handleReconnect(el.value); }}
            style={{ fontSize: 10, color: "#22D3EE", background: "rgba(34,211,238,0.1)", border: "1px solid rgba(34,211,238,0.2)", borderRadius: 4, padding: "3px 8px", cursor: "pointer" }}>
            Reconnect
          </button>
          <button onClick={() => { setPendingReconnect(null); deleteSshTarget(sessionId); }}
            style={{ fontSize: 10, color: "#475569", background: "none", border: "none", cursor: "pointer" }}>
            Dismiss
          </button>
        </div>
      )}

      {/* ── Thread ── */}
      <div style={{ flex: 1, overflowY: "auto", padding: "24px 18px", display: "flex", flexDirection: "column", gap: 20 }}>
        <div style={{ maxWidth: 720, width: "100%", margin: "0 auto", display: "flex", flexDirection: "column", gap: 20 }}>

          {!historyLoaded && (
            <div style={{ textAlign: "center", padding: 32, fontSize: 12, color: "#475569" }}>Loading history…</div>
          )}

          {/* Welcome */}
          {isEmpty && (
            <div style={{ textAlign: "center", paddingTop: 80, animation: "artifactSlideIn 0.5s ease both" }}>
              <svg viewBox="0 0 48 48" width="48" height="48" style={{ margin: "0 auto 16px", display: "block" }}>
                <polygon points="24,2 43.2,13 43.2,35 24,46 4.8,35 4.8,13"
                  fill="none" stroke="#22D3EE" strokeWidth="1" opacity="0.3"/>
                <path d="M24,7 L25.7,19.5 L37,14.2 L27.5,24 L37,33.8 L25.7,28.5 L24,41 L22.3,28.5 L11,33.8 L20.5,24 L11,14.2 L22.3,19.5 Z"
                  fill="#22D3EE"/>
              </svg>
              <div style={{ fontSize: 16, fontWeight: 600, color: "#94A3B8", marginBottom: 8 }}>Astra is ready</div>
              <div style={{ fontSize: 13, color: "#2A3A50" }}>Ask anything about your cluster</div>
            </div>
          )}

          {/* Messages */}
          {messages.map((m) => {
            if (m.role === "user") {
              return <UserMessage key={m.id} text={m.text} time={formatTime()}/>;
            }

            // Assistant message
            if (m.loading) {
              return (
                <AstraMessage key={m.id} time={formatTime()} text="Investigating across your cluster…">
                  {reasoningSteps.length > 0 && <ReasoningBubble steps={reasoningSteps} thinking={isThinking}/>}
                </AstraMessage>
              );
            }

            // Investigation result → RootCauseCard
            if (isInvestigation(m.tool) && m.result) {
              const rc = extractRootCause(m.result);
              const actions = (m.suggestedActions || []).map(a => ({ label: a.label, command: a.command }));
              return (
                <AstraMessage key={m.id} time={formatTime()} text={m.text ? undefined : "Investigation complete."}>
                  {reasoningSteps.length > 0 && <ReasoningBubble steps={reasoningSteps}/>}
                  <div style={{ marginTop: 10 }}>
                    <RootCauseCard
                      severity={rc.severity}
                      title={rc.title}
                      pod={rc.pod}
                      namespace={rc.namespace}
                      summary={rc.summary || m.text}
                      metrics={rc.metrics}
                      evidence={rc.evidence}
                      onReviewExecute={actions.length > 0 ? () => handleReviewExecute(actions, rc.pod, rc.namespace) : undefined}
                    />
                  </div>
                </AstraMessage>
              );
            }

            // Regular result card
            if (m.result && m.tool && m.tool !== "none") {
              return (
                <AstraMessage key={m.id} time={formatTime()}>
                  <ResultCard tool={m.tool} result={m.result}/>
                  {m.text && (
                    <div style={{ marginTop: 10, fontSize: 13, color: "#94A3B8", lineHeight: 1.6 }}>
                      <ReactMarkdown>{m.text}</ReactMarkdown>
                    </div>
                  )}
                </AstraMessage>
              );
            }

            // Plain text
            return (
              <AstraMessage key={m.id} time={formatTime()}>
                <div style={{ fontSize: 13, color: "#94A3B8", lineHeight: 1.6 }}>
                  <ReactMarkdown>{m.text}</ReactMarkdown>
                </div>
                {m.error && <div style={{ fontSize: 11, color: "#EF4444", marginTop: 4 }}>{m.error}</div>}
              </AstraMessage>
            );
          })}

          <div ref={bottomRef}/>
        </div>
      </div>

      {/* ── Intent bar ── */}
      <IntentBar onSend={submit} listening={loading} clusterName={clusterName}/>

      {/* ── Approval overlay ── */}
      {showOverlay && (
        <ApprovalOverlay
          onClose={() => setShowOverlay(false)}
          onConfirm={handleExecuteConfirm}
          actions={overlayActions}
          targetResource={overlayResource}
          namespace={overlayNamespace}
        />
      )}
    </div>
  );
}
