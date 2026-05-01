"use client";

import { useState } from "react";
import ToolPing from "./ToolPing";

/** ReasoningBubble — collapsible "Investigation Trail" panel */

export interface ToolStep {
  tool: string;
  status: "idle" | "running" | "done";
  result?: string;
}

interface ReasoningBubbleProps {
  steps: ToolStep[];
  thinking?: boolean;
}

export default function ReasoningBubble({ steps, thinking }: ReasoningBubbleProps) {
  const [collapsed, setCollapsed] = useState(false);
  const doneCount = steps.filter(s => s.status === "done").length;

  return (
    <div style={{
      background: "rgba(13,20,32,0.7)",
      backdropFilter: "blur(12px)",
      border: "1px solid rgba(34,211,238,0.15)",
      borderRadius: 10,
      overflow: "hidden",
      maxWidth: 480,
      animation: "artifactSlideIn 0.4s cubic-bezier(0.34,1.56,0.64,1) both",
    }}>
      {/* Header */}
      <div
        onClick={() => setCollapsed(c => !c)}
        style={{
          padding: "9px 12px",
          display: "flex", alignItems: "center", gap: 8,
          cursor: "pointer",
          borderBottom: collapsed ? "none" : "1px solid rgba(34,211,238,0.08)",
        }}
      >
        {/* Astra mini-mark */}
        <svg viewBox="0 0 16 16" width="14" height="14" style={{ flexShrink: 0 }}>
          <polygon points="8,0.5 14.9,4.25 14.9,11.75 8,15.5 1.1,11.75 1.1,4.25"
            fill="none" stroke="#22D3EE" strokeWidth="0.8" opacity="0.4"/>
          <path d="M8,3 L8.55,7.1 L12.1,5.5 L9,8 L12.1,10.5 L8.55,8.9 L8,13 L7.45,8.9 L3.9,10.5 L7,8 L3.9,5.5 L7.45,7.1 Z"
            fill="#22D3EE" opacity="0.9"/>
        </svg>
        <span style={{ fontSize: 11, fontWeight: 600, color: "#22D3EE", letterSpacing: "0.06em" }}>
          Investigation Trail
        </span>
        <span style={{ fontSize: 10, color: "#475569", fontFamily: "var(--mono)", marginLeft: 2 }}>
          {doneCount}/{steps.length} tools
        </span>
        {thinking && (
          <div style={{ display: "flex", gap: 3, alignItems: "center", marginLeft: 4 }}>
            {[0,1,2].map(d => (
              <div key={d} style={{
                width: 3, height: 3, borderRadius: "50%", background: "#22D3EE",
                animation: `dotBounce 1.2s ${d * 0.2}s ease-in-out infinite`,
              }}/>
            ))}
          </div>
        )}
        <div style={{ flex: 1 }}/>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none"
          stroke="#475569" strokeWidth="2" strokeLinecap="round"
          style={{ transform: collapsed ? "rotate(-90deg)" : "none", transition: "transform 0.2s" }}>
          <path d="M6 9l6 6 6-6"/>
        </svg>
      </div>

      {/* Steps */}
      {!collapsed && (
        <div style={{ padding: "10px 12px", display: "flex", flexDirection: "column", gap: 9 }}>
          {steps.map((s, i) => (
            <ToolPing key={s.tool} tool={s.tool} status={s.status} result={s.result} delay={i * 80}/>
          ))}
        </div>
      )}
    </div>
  );
}
