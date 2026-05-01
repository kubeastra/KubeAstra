"use client";

/** ToolPing — animated tool execution indicator */

const TOOL_COLORS: Record<string, string> = {
  kubectl:    "#4F8EF7",
  prometheus: "#F97316",
  logs:       "#22D3EE",
  events:     "#A78BFA",
  topology:   "#34D399",
  describe:   "#FBBF24",
  ai:         "#C8733A",
};

interface ToolPingProps {
  tool: string;
  status: "idle" | "running" | "done";
  result?: string;
  delay?: number;
}

export default function ToolPing({ tool, status, result, delay = 0 }: ToolPingProps) {
  const c = TOOL_COLORS[tool] || "#64748B";
  return (
    <div
      style={{
        display: "flex", alignItems: "center", gap: 8,
        animation: `artifactSlideIn 0.35s cubic-bezier(0.34,1.56,0.64,1) ${delay}ms both`,
      }}
    >
      {/* Status dot */}
      <div style={{ position: "relative", width: 8, height: 8, flexShrink: 0 }}>
        <div style={{
          width: 8, height: 8, borderRadius: "50%",
          background: status === "idle" ? "#1E2D40" : c,
          boxShadow: status === "running" ? `0 0 6px ${c}` : "none",
          animation: status === "running" ? "blink 1s ease-in-out infinite" : "none",
        }}/>
        {status === "running" && (
          <div style={{
            position: "absolute", inset: -3, borderRadius: "50%",
            border: `1px solid ${c}`,
            animation: "pulseRing 1.4s ease-out infinite",
          }}/>
        )}
      </div>
      {/* Label */}
      <span style={{
        fontSize: 11, fontFamily: "var(--mono)",
        color: status === "done" ? c : status === "running" ? "#E2E8F0" : "#2A3A50",
        letterSpacing: "0.04em",
      }}>
        {tool}
      </span>
      {/* Result */}
      {status === "done" && result && (
        <span style={{ fontSize: 10, color: "#475569", fontFamily: "var(--mono)" }}>
          → {result}
        </span>
      )}
      {status === "running" && (
        <span style={{
          fontSize: 10, color: "#22D3EE", fontFamily: "var(--mono)",
          animation: "blink 1s step-end infinite",
        }}>running…</span>
      )}
    </div>
  );
}
