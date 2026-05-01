"use client";

import { useState } from "react";

/** IntentBar — redesigned input bar with cluster context badge */

interface IntentBarProps {
  onSend: (text: string) => void;
  listening?: boolean;
  clusterName?: string;
  toolCount?: number;
}

export default function IntentBar({ onSend, listening, clusterName = "LOCAL", toolCount = 32 }: IntentBarProps) {
  const [val, setVal] = useState("");
  const submit = () => {
    if (!val.trim()) return;
    onSend(val.trim());
    setVal("");
  };

  return (
    <div style={{
      padding: "12px 16px",
      borderTop: "1px solid var(--border)",
      background: "rgba(13,17,23,0.9)",
      backdropFilter: "blur(12px)",
      flexShrink: 0,
    }}>
      <div style={{
        display: "flex", alignItems: "center", gap: 0,
        background: "#080D14",
        border: `1px solid ${listening ? "rgba(34,211,238,0.4)" : "var(--border)"}`,
        borderRadius: 10,
        boxShadow: listening ? "0 0 0 3px rgba(34,211,238,0.06)" : "none",
        transition: "border-color 0.3s, box-shadow 0.3s",
        overflow: "hidden",
      }}>
        {/* Cluster context badge */}
        <div style={{
          padding: "0 12px",
          height: "100%", display: "flex", alignItems: "center",
          borderRight: "1px solid var(--border)",
          flexShrink: 0,
        }}>
          <span style={{
            fontSize: 10, fontFamily: "var(--mono)", fontWeight: 600,
            color: "#22D3EE", letterSpacing: "0.06em",
            background: "rgba(34,211,238,0.1)",
            border: "1px solid rgba(34,211,238,0.2)",
            borderRadius: 4, padding: "3px 7px",
          }}>
            {clusterName}
          </span>
        </div>
        {/* Input */}
        <input
          value={val}
          onChange={e => setVal(e.target.value)}
          onKeyDown={e => e.key === "Enter" && submit()}
          placeholder="Ask Astra anything about your cluster…"
          style={{
            flex: 1, padding: "13px 14px",
            background: "transparent", border: "none", outline: "none",
            color: "#E2E8F0", fontSize: 13, fontFamily: "var(--sans)",
          }}
        />
        {/* Listening indicator */}
        {listening && (
          <div style={{ padding: "0 10px", display: "flex", gap: 3, alignItems: "center" }}>
            {[0,1,2].map(d => (
              <div key={d} style={{
                width: 3, height: 3, borderRadius: "50%", background: "#22D3EE",
                animation: `dotBounce 1.2s ${d * 0.2}s ease-in-out infinite`,
              }}/>
            ))}
          </div>
        )}
        {/* Send button */}
        <button onClick={submit} style={{
          padding: "0 14px", height: "100%", minHeight: 48,
          background: val.trim() ? "rgba(34,211,238,0.1)" : "transparent",
          border: "none", borderLeft: "1px solid var(--border)",
          cursor: val.trim() ? "pointer" : "default",
          color: val.trim() ? "#22D3EE" : "#2A3A50",
          transition: "all 0.2s",
          display: "flex", alignItems: "center", justifyContent: "center",
        }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <line x1="22" y1="2" x2="11" y2="13"/>
            <polygon points="22 2 15 22 11 13 2 9 22 2"/>
          </svg>
        </button>
      </div>
      <div style={{
        marginTop: 6, textAlign: "center", fontSize: 9,
        color: "#1E2D40", fontFamily: "var(--mono)", letterSpacing: "0.06em",
      }}>
        Astra has access to {toolCount} investigative tools · {clusterName.toLowerCase()}
      </div>
    </div>
  );
}
