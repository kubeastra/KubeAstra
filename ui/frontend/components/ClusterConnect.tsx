"use client";

/**
 * Cluster connection screen — Auto-Detect / Kubeconfig / SSH tabs.
 *
 * Shown when no cluster is connected. Handles kubeconfig upload/paste,
 * context selection, and connectivity checks.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  clusterAutodetect,
  clusterUploadKubeconfig,
  clusterConnectContext,
  type KubeContext,
} from "../lib/api";

/* ── Types ─────────────────────────────────────────────────────── */

type Tab = "autodetect" | "kubeconfig" | "ssh";
type ConnectState = "idle" | "loading" | "connecting" | "error";

interface SSHFields {
  host: string;
  username: string;
  password: string;
  port: string;
}

export interface ClusterInfo {
  mode: string;
  context_name: string;
  cluster_name: string;
  server_url: string;
  namespace: string;
}

interface Props {
  sessionId: string;
  onConnect: (info: ClusterInfo) => void;
  onSSHConnect: (creds: { host: string; username: string; password: string; port: number }) => void;
}

/* ── Styles ────────────────────────────────────────────────────── */

const CARD: React.CSSProperties = {
  maxWidth: 560,
  width: "100%",
  background: "linear-gradient(135deg, #0f172a 0%, #1e293b 100%)",
  border: "1px solid #334155",
  borderRadius: 16,
  padding: 28,
  boxShadow: "0 20px 60px rgba(0, 0, 0, 0.4)",
};

const TAB_BAR: React.CSSProperties = {
  display: "flex",
  gap: 4,
  marginBottom: 24,
  background: "#0f172a",
  borderRadius: 10,
  padding: 4,
};

const INPUT: React.CSSProperties = {
  width: "100%",
  padding: "10px 14px",
  background: "#0f172a",
  border: "1px solid #334155",
  borderRadius: 8,
  color: "#f1f5f9",
  fontSize: 13,
  fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
  outline: "none",
  boxSizing: "border-box",
};

const TEXTAREA: React.CSSProperties = {
  ...INPUT,
  minHeight: 120,
  resize: "vertical" as const,
};

const SELECT: React.CSSProperties = {
  ...INPUT,
  cursor: "pointer",
  appearance: "none" as const,
  backgroundImage:
    `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%2394a3b8' d='M2 4l4 4 4-4'/%3E%3C/svg%3E")`,
  backgroundRepeat: "no-repeat",
  backgroundPosition: "right 12px center",
  paddingRight: 32,
};

const BTN_PRIMARY: React.CSSProperties = {
  padding: "10px 24px",
  background: "linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)",
  border: "none",
  borderRadius: 8,
  color: "#fff",
  fontSize: 13,
  fontWeight: 600,
  cursor: "pointer",
  width: "100%",
};

const BTN_DISABLED: React.CSSProperties = {
  ...BTN_PRIMARY,
  opacity: 0.5,
  cursor: "not-allowed",
};

const LABEL: React.CSSProperties = {
  display: "block",
  fontSize: 11,
  fontWeight: 600,
  color: "#94a3b8",
  textTransform: "uppercase" as const,
  letterSpacing: "0.06em",
  marginBottom: 6,
};

const ERROR_BOX: React.CSSProperties = {
  padding: "10px 14px",
  background: "#7f1d1d20",
  border: "1px solid #7f1d1d",
  borderRadius: 8,
  color: "#fca5a5",
  fontSize: 12,
  marginTop: 12,
};

const MSG_BOX: React.CSSProperties = {
  padding: "10px 14px",
  background: "#0f172a",
  border: "1px solid #334155",
  borderRadius: 8,
  color: "#94a3b8",
  fontSize: 12,
  marginTop: 12,
  textAlign: "center" as const,
};

/* ── Component ─────────────────────────────────────────────────── */

export default function ClusterConnect({ sessionId, onConnect, onSSHConnect }: Props) {
  const [tab, setTab] = useState<Tab>("autodetect");
  const [state, setState] = useState<ConnectState>("idle");
  const [error, setError] = useState<string | null>(null);

  // Autodetect state
  const [autoContexts, setAutoContexts] = useState<KubeContext[]>([]);
  const [autoCurrentCtx, setAutoCurrentCtx] = useState<string | null>(null);
  const [autoKubeconfigPath, setAutoKubeconfigPath] = useState<string | null>(null);
  const [selectedAutoCtx, setSelectedAutoCtx] = useState("");
  const [autoMessage, setAutoMessage] = useState("");

  // Kubeconfig state
  const [kubeconfigText, setKubeconfigText] = useState("");
  const [kubeContexts, setKubeContexts] = useState<KubeContext[]>([]);
  const [kubeconfigPath, setKubeconfigPath] = useState<string | null>(null);
  const [selectedKubeCtx, setSelectedKubeCtx] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  // SSH state
  const [ssh, setSsh] = useState<SSHFields>({ host: "", username: "", password: "", port: "22" });

  // ── Autodetect on mount ──────────────────────────────
  useEffect(() => {
    let cancelled = false;
    setState("loading");
    setError(null);

    clusterAutodetect().then((res) => {
      if (cancelled) return;
      setState("idle");

      if (res.in_cluster) {
        // In-cluster mode — auto-connect
        onConnect({
          mode: "in-cluster",
          context_name: "in-cluster",
          cluster_name: "in-cluster",
          server_url: "",
          namespace: "default",
        });
        return;
      }

      if (res.contexts && res.contexts.length > 0) {
        setAutoContexts(res.contexts);
        setAutoCurrentCtx(res.current_context ?? null);
        setAutoKubeconfigPath(res.kubeconfig_path ?? null);
        setSelectedAutoCtx(res.current_context ?? res.contexts[0].name);
        setAutoMessage(res.message ?? "");
      } else {
        setAutoMessage(res.message ?? "No kubeconfig found.");
      }
    }).catch(() => {
      if (!cancelled) {
        setState("idle");
        setAutoMessage("Could not detect kubeconfig.");
      }
    });

    return () => { cancelled = true; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Connect handlers ─────────────────────────────────

  const connectAutodetect = useCallback(async () => {
    if (!selectedAutoCtx) return;
    setState("connecting");
    setError(null);
    try {
      const res = await clusterConnectContext(
        sessionId, selectedAutoCtx, "autodetect", autoKubeconfigPath ?? undefined,
      );
      if (res.connected) {
        onConnect({
          mode: res.mode ?? "autodetect",
          context_name: res.context_name ?? selectedAutoCtx,
          cluster_name: res.cluster_name ?? selectedAutoCtx,
          server_url: res.server_url ?? "",
          namespace: res.namespace ?? "default",
        });
      } else {
        setError(res.error ?? "Connection failed");
        setState("error");
      }
    } catch (e) {
      setError(String(e));
      setState("error");
    }
  }, [sessionId, selectedAutoCtx, autoKubeconfigPath, onConnect]);

  const parseKubeconfig = useCallback(async () => {
    if (!kubeconfigText.trim()) return;
    setState("loading");
    setError(null);
    try {
      const res = await clusterUploadKubeconfig(kubeconfigText, sessionId);
      if (res.error) {
        setError(res.error);
        setState("error");
        return;
      }
      setKubeContexts(res.contexts ?? []);
      setKubeconfigPath(res.kubeconfig_path ?? null);
      setSelectedKubeCtx(res.current_context ?? res.contexts?.[0]?.name ?? "");
      setState("idle");
    } catch (e) {
      setError(String(e));
      setState("error");
    }
  }, [kubeconfigText, sessionId]);

  const connectKubeconfig = useCallback(async () => {
    if (!selectedKubeCtx) return;
    setState("connecting");
    setError(null);
    try {
      const res = await clusterConnectContext(
        sessionId, selectedKubeCtx, "kubeconfig-upload", kubeconfigPath ?? undefined,
      );
      if (res.connected) {
        onConnect({
          mode: res.mode ?? "kubeconfig-upload",
          context_name: res.context_name ?? selectedKubeCtx,
          cluster_name: res.cluster_name ?? selectedKubeCtx,
          server_url: res.server_url ?? "",
          namespace: res.namespace ?? "default",
        });
      } else {
        setError(res.error ?? "Connection failed");
        setState("error");
      }
    } catch (e) {
      setError(String(e));
      setState("error");
    }
  }, [sessionId, selectedKubeCtx, kubeconfigPath, onConnect]);

  const connectSSH = useCallback(() => {
    if (!ssh.host || !ssh.username || !ssh.password) return;
    onSSHConnect({
      host: ssh.host,
      username: ssh.username,
      password: ssh.password,
      port: parseInt(ssh.port, 10) || 22,
    });
  }, [ssh, onSSHConnect]);

  const handleFileUpload = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const text = reader.result as string;
      setKubeconfigText(text);
    };
    reader.readAsText(file);
  }, []);

  // ── Tab button helper ────────────────────────────────
  const TabBtn = ({ id, icon, label }: { id: Tab; icon: string; label: string }) => (
    <button
      onClick={() => { setTab(id); setError(null); }}
      style={{
        flex: 1,
        padding: "8px 12px",
        background: tab === id ? "#1e293b" : "transparent",
        border: tab === id ? "1px solid #334155" : "1px solid transparent",
        borderRadius: 8,
        color: tab === id ? "#f1f5f9" : "#64748b",
        fontSize: 12,
        fontWeight: 600,
        cursor: "pointer",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: 6,
        transition: "all 0.15s ease",
      }}
    >
      <span style={{ fontSize: 14 }}>{icon}</span>
      {label}
    </button>
  );

  return (
    <div style={{
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      minHeight: "100%",
      padding: 24,
    }}>
      <div style={CARD}>
        {/* Header */}
        <div style={{ textAlign: "center", marginBottom: 20 }}>
          <div style={{ fontSize: 22, marginBottom: 4 }}>🔌</div>
          <h2 style={{ color: "#f1f5f9", fontSize: 18, fontWeight: 700, margin: 0 }}>
            Connect to a Cluster
          </h2>
          <p style={{ color: "#64748b", fontSize: 12, margin: "6px 0 0" }}>
            Your kubeconfig stays local. Credentials are never sent to any external service.
          </p>
        </div>

        {/* Tabs */}
        <div style={TAB_BAR}>
          <TabBtn id="autodetect" icon="🔍" label="Auto-Detect" />
          <TabBtn id="kubeconfig" icon="📄" label="Kubeconfig" />
          <TabBtn id="ssh" icon="🖥️" label="SSH" />
        </div>

        {/* ── Auto-Detect Tab ─────────────────────────── */}
        {tab === "autodetect" && (
          <div>
            {state === "loading" && (
              <div style={MSG_BOX}>Detecting kubeconfig...</div>
            )}

            {autoContexts.length > 0 ? (
              <>
                <label style={LABEL}>Select Context</label>
                <select
                  value={selectedAutoCtx}
                  onChange={(e) => setSelectedAutoCtx(e.target.value)}
                  style={SELECT}
                >
                  {autoContexts.map((ctx) => (
                    <option key={ctx.name} value={ctx.name}>
                      {ctx.name}{ctx.name === autoCurrentCtx ? " (current)" : ""}
                    </option>
                  ))}
                </select>

                {/* Context details */}
                {selectedAutoCtx && (() => {
                  const ctx = autoContexts.find((c) => c.name === selectedAutoCtx);
                  if (!ctx) return null;
                  return (
                    <div style={{
                      marginTop: 12,
                      padding: "10px 14px",
                      background: "#0f172a",
                      border: "1px solid #1e293b",
                      borderRadius: 8,
                      fontSize: 11,
                    }}>
                      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                        <span style={{ color: "#64748b" }}>Cluster</span>
                        <span style={{ color: "#e2e8f0", fontFamily: "monospace" }}>{ctx.cluster}</span>
                      </div>
                      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                        <span style={{ color: "#64748b" }}>Server</span>
                        <span style={{ color: "#e2e8f0", fontFamily: "monospace" }}>{ctx.server || "—"}</span>
                      </div>
                      <div style={{ display: "flex", justifyContent: "space-between" }}>
                        <span style={{ color: "#64748b" }}>Namespace</span>
                        <span style={{ color: "#e2e8f0", fontFamily: "monospace" }}>{ctx.namespace}</span>
                      </div>
                    </div>
                  );
                })()}

                <button
                  onClick={connectAutodetect}
                  disabled={state === "connecting"}
                  style={state === "connecting" ? BTN_DISABLED : { ...BTN_PRIMARY, marginTop: 16 }}
                >
                  {state === "connecting" ? "Connecting..." : "Connect"}
                </button>
              </>
            ) : state !== "loading" ? (
              <div style={MSG_BOX}>
                {autoMessage || "No kubeconfig found at ~/.kube/config. Try uploading one or use SSH."}
              </div>
            ) : null}
          </div>
        )}

        {/* ── Kubeconfig Tab ──────────────────────────── */}
        {tab === "kubeconfig" && (
          <div>
            {kubeContexts.length === 0 ? (
              <>
                <label style={LABEL}>Paste kubeconfig YAML</label>
                <textarea
                  value={kubeconfigText}
                  onChange={(e) => setKubeconfigText(e.target.value)}
                  placeholder={"apiVersion: v1\nkind: Config\nclusters:\n  ..."}
                  style={TEXTAREA}
                />

                <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
                  <button
                    onClick={parseKubeconfig}
                    disabled={!kubeconfigText.trim() || state === "loading"}
                    style={!kubeconfigText.trim() || state === "loading" ? BTN_DISABLED : BTN_PRIMARY}
                  >
                    {state === "loading" ? "Parsing..." : "Parse Kubeconfig"}
                  </button>
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    style={{
                      ...BTN_PRIMARY,
                      background: "#1e293b",
                      border: "1px solid #334155",
                    }}
                  >
                    Upload File
                  </button>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".yaml,.yml,.conf,.config"
                    onChange={handleFileUpload}
                    style={{ display: "none" }}
                  />
                </div>
              </>
            ) : (
              <>
                <label style={LABEL}>Select Context</label>
                <select
                  value={selectedKubeCtx}
                  onChange={(e) => setSelectedKubeCtx(e.target.value)}
                  style={SELECT}
                >
                  {kubeContexts.map((ctx) => (
                    <option key={ctx.name} value={ctx.name}>
                      {ctx.name}
                    </option>
                  ))}
                </select>

                {/* Context details */}
                {selectedKubeCtx && (() => {
                  const ctx = kubeContexts.find((c) => c.name === selectedKubeCtx);
                  if (!ctx) return null;
                  return (
                    <div style={{
                      marginTop: 12,
                      padding: "10px 14px",
                      background: "#0f172a",
                      border: "1px solid #1e293b",
                      borderRadius: 8,
                      fontSize: 11,
                    }}>
                      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                        <span style={{ color: "#64748b" }}>Cluster</span>
                        <span style={{ color: "#e2e8f0", fontFamily: "monospace" }}>{ctx.cluster}</span>
                      </div>
                      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                        <span style={{ color: "#64748b" }}>Server</span>
                        <span style={{ color: "#e2e8f0", fontFamily: "monospace" }}>{ctx.server || "—"}</span>
                      </div>
                      <div style={{ display: "flex", justifyContent: "space-between" }}>
                        <span style={{ color: "#64748b" }}>Namespace</span>
                        <span style={{ color: "#e2e8f0", fontFamily: "monospace" }}>{ctx.namespace}</span>
                      </div>
                    </div>
                  );
                })()}

                <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
                  <button
                    onClick={connectKubeconfig}
                    disabled={state === "connecting"}
                    style={state === "connecting" ? BTN_DISABLED : { ...BTN_PRIMARY, flex: 1 }}
                  >
                    {state === "connecting" ? "Connecting..." : "Connect"}
                  </button>
                  <button
                    onClick={() => { setKubeContexts([]); setKubeconfigText(""); setKubeconfigPath(null); }}
                    style={{ ...BTN_PRIMARY, flex: 0, background: "#1e293b", border: "1px solid #334155", whiteSpace: "nowrap" }}
                  >
                    Back
                  </button>
                </div>
              </>
            )}
          </div>
        )}

        {/* ── SSH Tab ─────────────────────────────────── */}
        {tab === "ssh" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div>
              <label style={LABEL}>Host</label>
              <input
                value={ssh.host}
                onChange={(e) => setSsh({ ...ssh, host: e.target.value })}
                placeholder="192.168.1.50"
                style={INPUT}
              />
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <div style={{ flex: 1 }}>
                <label style={LABEL}>Username</label>
                <input
                  value={ssh.username}
                  onChange={(e) => setSsh({ ...ssh, username: e.target.value })}
                  placeholder="ubuntu"
                  style={INPUT}
                />
              </div>
              <div style={{ width: 80 }}>
                <label style={LABEL}>Port</label>
                <input
                  value={ssh.port}
                  onChange={(e) => setSsh({ ...ssh, port: e.target.value })}
                  placeholder="22"
                  style={INPUT}
                />
              </div>
            </div>
            <div>
              <label style={LABEL}>Password</label>
              <input
                type="password"
                value={ssh.password}
                onChange={(e) => setSsh({ ...ssh, password: e.target.value })}
                placeholder="••••••••"
                style={INPUT}
                onKeyDown={(e) => { if (e.key === "Enter") connectSSH(); }}
              />
            </div>
            <button
              onClick={connectSSH}
              disabled={!ssh.host || !ssh.username || !ssh.password}
              style={!ssh.host || !ssh.username || !ssh.password ? BTN_DISABLED : BTN_PRIMARY}
            >
              Connect via SSH
            </button>
          </div>
        )}

        {/* Error display */}
        {error && <div style={ERROR_BOX}>{error}</div>}
      </div>
    </div>
  );
}
