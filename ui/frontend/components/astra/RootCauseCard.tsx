"use client";

import { useState } from "react";

/** RootCauseCard — severity-rated diagnostic card with metrics and evidence */

interface Metric {
  label: string;
  value: string;
  color: string;
}

interface RootCauseCardProps {
  severity?: "critical" | "warning" | "info";
  title?: string;
  pod?: string;
  namespace?: string;
  summary?: string;
  metrics?: Metric[];
  evidence?: string;
  confidence?: number;
  onReviewExecute?: () => void;
  suggestedActions?: Array<{ label: string; command: string; confirm?: boolean }>;
}

const SEVERITY_COLORS = {
  critical: { bg: "rgba(239,68,68,0.15)", border: "rgba(239,68,68,0.3)", text: "#EF4444" },
  warning:  { bg: "rgba(251,191,36,0.15)", border: "rgba(251,191,36,0.3)", text: "#FBBF24" },
  info:     { bg: "rgba(34,211,238,0.15)", border: "rgba(34,211,238,0.3)", text: "#22D3EE" },
};

export default function RootCauseCard({
  severity = "critical",
  title = "Root Cause Identified",
  pod = "",
  namespace = "",
  summary = "",
  metrics = [],
  evidence = "",
  confidence,
  onReviewExecute,
  suggestedActions = [],
}: RootCauseCardProps) {
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const sev = SEVERITY_COLORS[severity];

  return (
    <div style={{
      maxWidth: 520,
      background: "rgba(13,20,32,0.85)",
      backdropFilter: "blur(16px)",
      border: "1px solid rgba(34,211,238,0.2)",
      borderRadius: 12,
      overflow: "hidden",
      animation: "artifactSlideIn 0.45s cubic-bezier(0.34,1.56,0.64,1) both",
      boxShadow: "0 16px 48px rgba(0,0,0,0.5), 0 0 0 1px rgba(34,211,238,0.05)",
    }}>
      {/* Card header */}
      <div style={{
        padding: "12px 16px",
        background: "rgba(34,211,238,0.05)",
        borderBottom: "1px solid rgba(34,211,238,0.1)",
        display: "flex", alignItems: "center", gap: 10,
      }}>
        <div style={{
          width: 28, height: 28, borderRadius: 7,
          background: sev.bg, border: `1px solid ${sev.border}`,
          display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
        }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
            stroke={sev.text} strokeWidth="2" strokeLinecap="round">
            <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
            <line x1="12" y1="9" x2="12" y2="13"/>
            <line x1="12" y1="17" x2="12.01" y2="17"/>
          </svg>
        </div>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ fontSize: 12, fontWeight: 600, color: "#E2E8F0" }}>{title}</span>
            <span style={{
              fontSize: 9, fontWeight: 700, letterSpacing: "0.12em",
              background: sev.bg, border: `1px solid ${sev.border}`,
              color: sev.text, borderRadius: 3, padding: "1px 6px", textTransform: "uppercase",
            }}>{severity}</span>
          </div>
          {(pod || namespace) && (
            <div style={{ fontSize: 10, color: "#475569", marginTop: 1, fontFamily: "var(--mono)" }}>
              {pod}{namespace ? ` · ${namespace}` : ""}
            </div>
          )}
        </div>
        <div style={{ flex: 1 }}/>
        {confidence !== undefined && (
          <div style={{ fontSize: 10, color: "#2A3A50", fontFamily: "var(--mono)" }}>
            confidence: {confidence.toFixed(2)}
          </div>
        )}
      </div>

      {/* Summary + metrics + evidence */}
      <div style={{ padding: "14px 16px" }}>
        {summary && (
          <div style={{ fontSize: 13, color: "#CBD5E1", lineHeight: 1.6, marginBottom: 12 }}>
            {summary}
          </div>
        )}

        {/* Metrics row */}
        {metrics.length > 0 && (
          <div style={{
            display: "grid", gridTemplateColumns: `repeat(${Math.min(metrics.length, 4)},1fr)`,
            gap: 8, marginBottom: 14,
          }}>
            {metrics.map(m => (
              <div key={m.label} style={{
                background: "#0B1018", border: "1px solid #1A2535",
                borderRadius: 6, padding: "8px 10px", textAlign: "center",
              }}>
                <div style={{ fontSize: 16, fontWeight: 700, color: m.color, fontFamily: "var(--mono)" }}>
                  {m.value}
                </div>
                <div style={{ fontSize: 9, color: "#475569", marginTop: 2, letterSpacing: "0.08em", textTransform: "uppercase" }}>
                  {m.label}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Raw evidence toggle */}
        {evidence && (
          <div style={{
            background: "#080D14", border: "1px solid #1A2535",
            borderRadius: 7, overflow: "hidden", marginBottom: 12,
          }}>
            <div
              onClick={() => setEvidenceOpen(o => !o)}
              style={{
                padding: "7px 12px", cursor: "pointer",
                display: "flex", alignItems: "center", gap: 6,
                borderBottom: evidenceOpen ? "1px solid #1A2535" : "none",
              }}
            >
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none"
                stroke="#475569" strokeWidth="2" strokeLinecap="round">
                <polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>
              </svg>
              <span style={{ fontSize: 10, color: "#475569", fontFamily: "var(--mono)", letterSpacing: "0.06em" }}>
                Raw Evidence
              </span>
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none"
                stroke="#2A3A50" strokeWidth="2" strokeLinecap="round"
                style={{ marginLeft: "auto", transform: evidenceOpen ? "rotate(180deg)" : "none", transition: "transform 0.2s" }}>
                <path d="M6 9l6 6 6-6"/>
              </svg>
            </div>
            {evidenceOpen && (
              <div style={{
                padding: "10px 12px",
                fontFamily: "var(--mono)", fontSize: 11,
                color: "#64748B", lineHeight: 1.8,
                maxHeight: 180, overflowY: "auto",
                whiteSpace: "pre-wrap",
              }}>
                {evidence.split("\n").map((line, i) => (
                  <div key={i} style={{
                    color: line.startsWith("#") ? "#22D3EE" :
                           line.startsWith(">") ? "#C8733A" :
                           line.startsWith("!") ? "#EF4444" :
                           line.startsWith("  ") ? "#94A3B8" : "#64748B",
                    fontWeight: line.startsWith("#") ? 600 : 400,
                  }}>
                    {line || <br/>}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Review & Execute CTA */}
        {(onReviewExecute || suggestedActions.length > 0) && (
          <button
            onClick={onReviewExecute}
            style={{
              width: "100%", padding: "11px",
              background: "linear-gradient(135deg, rgba(200,115,58,0.2), rgba(200,115,58,0.1))",
              border: "1px solid rgba(200,115,58,0.5)",
              borderRadius: 8, cursor: "pointer",
              display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
              transition: "all 0.18s ease",
              fontFamily: "var(--sans)",
            }}
            onMouseEnter={e => {
              e.currentTarget.style.background = "linear-gradient(135deg, rgba(200,115,58,0.35), rgba(200,115,58,0.2))";
              e.currentTarget.style.boxShadow = "0 0 20px rgba(200,115,58,0.25)";
            }}
            onMouseLeave={e => {
              e.currentTarget.style.background = "linear-gradient(135deg, rgba(200,115,58,0.2), rgba(200,115,58,0.1))";
              e.currentTarget.style.boxShadow = "none";
            }}
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none"
              stroke="#C8733A" strokeWidth="2" strokeLinecap="round">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
            </svg>
            <span style={{ fontSize: 12, fontWeight: 600, color: "#C8733A", letterSpacing: "0.06em" }}>
              Review &amp; Execute Fix
            </span>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none"
              stroke="#C8733A" strokeWidth="2" strokeLinecap="round">
              <path d="M5 12h14M12 5l7 7-7 7"/>
            </svg>
          </button>
        )}
      </div>
    </div>
  );
}
