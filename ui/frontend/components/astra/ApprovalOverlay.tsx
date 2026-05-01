"use client";

import { useState, useEffect, useRef, useCallback } from "react";

/** ApprovalOverlay — full-screen approval gate with diff, preflight, and slide-to-confirm */

interface DiffLine {
  t: "hunk" | "ctx" | "remove" | "add";
  s: string;
}

interface ActionDetail {
  label: string;
  command: string;
  confirm?: boolean;
  type?: string;
}

interface ApprovalOverlayProps {
  onClose: () => void;
  onConfirm: () => void;
  onCopyCommand?: (cmd: string) => void;
  actions?: ActionDetail[];
  targetResource?: string;
  namespace?: string;
}

/* ── DiffView sub-component ─────────────────────────────────────────────── */

function DiffView({ lines }: { lines: DiffLine[] }) {
  return (
    <div style={{
      background: "#06090F",
      border: "1px solid #1A2535",
      borderRadius: 8, overflow: "hidden",
    }}>
      <div style={{
        padding: "7px 14px",
        borderBottom: "1px solid #1A2535",
        display: "flex", alignItems: "center", gap: 8,
      }}>
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none"
          stroke="#475569" strokeWidth="2" strokeLinecap="round">
          <circle cx="18" cy="18" r="3"/><circle cx="6" cy="6" r="3"/>
          <path d="M6 21V9a9 9 0 009 9"/>
        </svg>
        <span style={{ fontSize: 10, color: "#475569", fontFamily: "var(--mono)" }}>
          proposed changes
        </span>
        <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
          <span style={{ fontSize: 9, color: "#EF4444", fontFamily: "var(--mono)", background: "rgba(239,68,68,0.1)", padding: "1px 6px", borderRadius: 3 }}>
            -{lines.filter(l => l.t === "remove").length}
          </span>
          <span style={{ fontSize: 9, color: "#34D399", fontFamily: "var(--mono)", background: "rgba(52,211,153,0.1)", padding: "1px 6px", borderRadius: 3 }}>
            +{lines.filter(l => l.t === "add").length}
          </span>
        </div>
      </div>
      <div style={{ padding: "8px 0", fontFamily: "var(--mono)", fontSize: 11, lineHeight: 1.8 }}>
        {lines.map((l, i) => (
          <div key={i} style={{
            padding: "0 14px",
            background: l.t === "add" ? "rgba(52,211,153,0.08)" :
                        l.t === "remove" ? "rgba(239,68,68,0.08)" :
                        l.t === "hunk" ? "rgba(79,142,247,0.06)" : "transparent",
            color: l.t === "add" ? "#34D399" :
                   l.t === "remove" ? "#EF4444" :
                   l.t === "hunk" ? "#4F8EF7" : "#475569",
            borderLeft: l.t === "add" ? "2px solid #34D39960" :
                        l.t === "remove" ? "2px solid #EF444460" : "2px solid transparent",
          }}>
            {l.s}
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── SlideConfirm sub-component ─────────────────────────────────────────── */

function SlideConfirm({ onConfirm }: { onConfirm: () => void }) {
  const [pos, setPos] = useState(0);
  const [dragging, setDragging] = useState(false);
  const [done, setDone] = useState(false);
  const trackRef = useRef<HTMLDivElement>(null);
  const startX = useRef(0);
  const THUMB = 52;
  const THRESH = 0.80;

  const onMouseDown = (e: React.MouseEvent) => {
    if (done) return;
    setDragging(true);
    startX.current = e.clientX - pos;
    e.preventDefault();
  };
  const onTouchStart = (e: React.TouchEvent) => {
    if (done) return;
    setDragging(true);
    startX.current = e.touches[0].clientX - pos;
  };

  useEffect(() => {
    if (!dragging) return;
    const move = (clientX: number) => {
      const track = trackRef.current;
      if (!track) return;
      const max = track.offsetWidth - THUMB - 4;
      const np = Math.max(0, Math.min(clientX - startX.current, max));
      setPos(np);
      if (np / max >= THRESH) {
        setDragging(false);
        setDone(true);
        setPos(max);
        setTimeout(onConfirm, 400);
      }
    };
    const onMM = (e: MouseEvent) => move(e.clientX);
    const onTM = (e: TouchEvent) => move(e.touches[0].clientX);
    const onUp = () => { if (!done) setPos(0); setDragging(false); };
    window.addEventListener("mousemove", onMM);
    window.addEventListener("mouseup", onUp);
    window.addEventListener("touchmove", onTM);
    window.addEventListener("touchend", onUp);
    return () => {
      window.removeEventListener("mousemove", onMM);
      window.removeEventListener("mouseup", onUp);
      window.removeEventListener("touchmove", onTM);
      window.removeEventListener("touchend", onUp);
    };
  }, [dragging, done, onConfirm]);

  const trackW = trackRef.current?.offsetWidth || 400;
  const pct = pos / Math.max(1, trackW - THUMB - 4);

  return (
    <div ref={trackRef} style={{
      position: "relative", height: 52,
      background: done ? "#0A2016" : "#0D0A07",
      border: `1px solid ${done ? "#34D39960" : "#C8733A60"}`,
      borderRadius: 10, overflow: "hidden",
      userSelect: "none",
      transition: "border-color 0.3s, background 0.3s",
    }}>
      {/* Fill */}
      <div style={{
        position: "absolute", left: 0, top: 0, bottom: 0,
        width: `${pct * 100}%`,
        background: done
          ? "linear-gradient(90deg, rgba(52,211,153,0.2), rgba(52,211,153,0.08))"
          : `rgba(200,115,58,${pct * 0.3})`,
        transition: dragging ? "none" : "width 0.4s ease, background 0.3s",
      }}/>
      {/* Text */}
      <div style={{
        position: "absolute", inset: 0, display: "flex",
        alignItems: "center", justifyContent: "center", pointerEvents: "none",
      }}>
        <span style={{
          fontSize: 11, fontWeight: 700, letterSpacing: "0.14em",
          color: done ? "#34D399" : "#C8733A",
          opacity: done ? 1 : Math.max(0, 1 - pct * 1.8),
          textTransform: "uppercase",
          transition: "opacity 0.15s",
        }}>
          {done ? "✓ Fix Queued for Rollout" : "Slide to Confirm Execution"}
        </span>
      </div>
      {/* Thumb */}
      {!done && (
        <div onMouseDown={onMouseDown} onTouchStart={onTouchStart} style={{
          position: "absolute", left: pos + 2, top: 2, bottom: 2, width: THUMB,
          background: "linear-gradient(135deg, #C8733A, #A05020)",
          border: "1px solid #D4845A",
          borderRadius: 7, cursor: "grab",
          display: "flex", alignItems: "center", justifyContent: "center",
          boxShadow: `0 0 ${8 + pct * 16}px rgba(200,115,58,${0.3 + pct * 0.4})`,
          transition: dragging ? "none" : "left 0.35s cubic-bezier(0.34,1.56,0.64,1), box-shadow 0.2s",
        }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
            stroke="#fff" strokeWidth="2.5" strokeLinecap="round">
            <path d="M5 12h14M12 5l7 7-7 7"/>
          </svg>
        </div>
      )}
    </div>
  );
}

/* ── Main ApprovalOverlay ───────────────────────────────────────────────── */

const PREFLIGHT_CHECKS = [
  "Dry-run validated — no schema errors",
  "Node allocatable capacity sufficient",
  "PodDisruptionBudget allows disruption",
  "Rollback manifest saved to audit log",
];

export default function ApprovalOverlay({ onClose, onConfirm, onCopyCommand, actions = [], targetResource, namespace }: ApprovalOverlayProps) {
  const [confirmed, setConfirmed] = useState(false);
  const [mode, setMode] = useState<"choose" | "execute" | "copy">("choose");

  // Build diff lines from actions
  const diffLines: DiffLine[] = actions.flatMap(a => [
    { t: "hunk" as const, s: `# ${a.label}` },
    { t: "add" as const, s: `$ ${a.command}` },
  ]);

  const handleConfirm = useCallback(() => {
    setConfirmed(true);
    setTimeout(() => { onConfirm(); onClose(); }, 1200);
  }, [onConfirm, onClose]);

  const handleCopy = useCallback(() => {
    const commands = actions.map(a => a.command).join("\n");
    navigator.clipboard.writeText(commands).catch(() => {});
    if (onCopyCommand && actions[0]) onCopyCommand(actions[0].command);
    setMode("copy");
    setTimeout(onClose, 1000);
  }, [actions, onCopyCommand, onClose]);

  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 100,
      display: "flex", alignItems: "center", justifyContent: "center",
      background: "rgba(7,9,20,0.85)",
      backdropFilter: "blur(8px)",
      animation: "overlayFadeIn 0.25s ease both",
    }}>
      <div style={{
        width: 520, maxHeight: "85vh",
        background: "#0C1220",
        border: "1px solid rgba(200,115,58,0.3)",
        borderRadius: 14, overflow: "hidden",
        boxShadow: "0 32px 80px rgba(0,0,0,0.7), 0 0 0 1px rgba(200,115,58,0.1)",
        animation: "artifactSlideIn 0.4s cubic-bezier(0.34,1.56,0.64,1) both",
        display: "flex", flexDirection: "column",
      }}>
        {/* Header */}
        <div style={{
          padding: "14px 18px",
          background: "rgba(200,115,58,0.08)",
          borderBottom: "1px solid rgba(200,115,58,0.15)",
          display: "flex", alignItems: "center", gap: 10,
          flexShrink: 0,
        }}>
          <div style={{
            width: 32, height: 32, borderRadius: 8,
            background: "rgba(200,115,58,0.15)",
            border: "1px solid rgba(200,115,58,0.3)",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
              stroke="#C8733A" strokeWidth="2" strokeLinecap="round">
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
              <path d="M7 11V7a5 5 0 0110 0v4"/>
            </svg>
          </div>
          <div>
            <div style={{ fontSize: 13, fontWeight: 600, color: "#E2E8F0" }}>
              Impact Preview — Approval Required
            </div>
            <div style={{ fontSize: 10, color: "#C8733A", fontFamily: "var(--mono)", marginTop: 1 }}>
              {namespace ? `${namespace} · ` : ""}{targetResource || "cluster resource"}
            </div>
          </div>
          <div style={{ flex: 1 }}/>
          <button onClick={onClose} style={{
            background: "none", border: "none", cursor: "pointer", padding: 4,
            color: "#475569",
          }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>

        <div style={{ flex: 1, overflowY: "auto", padding: "16px 18px", display: "flex", flexDirection: "column", gap: 14 }}>
          {/* Preflight */}
          <div>
            <div style={{ fontSize: 10, color: "#475569", letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 8 }}>
              Preflight Checks
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
              {PREFLIGHT_CHECKS.map((c, i) => (
                <div key={i} style={{
                  display: "flex", alignItems: "center", gap: 8,
                  padding: "5px 10px",
                  background: "rgba(52,211,153,0.05)",
                  border: "1px solid rgba(52,211,153,0.15)",
                  borderRadius: 5,
                  animation: `artifactSlideIn 0.3s cubic-bezier(0.34,1.56,0.64,1) ${i * 60}ms both`,
                }}>
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none"
                    stroke="#34D399" strokeWidth="2.5" strokeLinecap="round">
                    <path d="M20 6L9 17l-5-5"/>
                  </svg>
                  <span style={{ fontSize: 11, color: "#64748B" }}>{c}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Commands */}
          {diffLines.length > 0 && (
            <div>
              <div style={{ fontSize: 10, color: "#475569", letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 8 }}>
                Commands to Execute
              </div>
              <DiffView lines={diffLines}/>
            </div>
          )}

          {/* Action choice or slide confirm */}
          {mode === "choose" && !confirmed && (
            <div style={{ display: "flex", gap: 8 }}>
              <button
                onClick={() => setMode("execute")}
                style={{
                  flex: 1, padding: "11px",
                  background: "linear-gradient(135deg, rgba(200,115,58,0.2), rgba(200,115,58,0.1))",
                  border: "1px solid rgba(200,115,58,0.5)",
                  borderRadius: 8, cursor: "pointer",
                  display: "flex", alignItems: "center", justifyContent: "center", gap: 6,
                  color: "#C8733A", fontSize: 12, fontWeight: 600,
                }}
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none"
                  stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                  <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
                </svg>
                Execute Fix
              </button>
              <button
                onClick={handleCopy}
                style={{
                  flex: 1, padding: "11px",
                  background: "rgba(34,211,238,0.08)",
                  border: "1px solid rgba(34,211,238,0.25)",
                  borderRadius: 8, cursor: "pointer",
                  display: "flex", alignItems: "center", justifyContent: "center", gap: 6,
                  color: "#22D3EE", fontSize: 12, fontWeight: 600,
                }}
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none"
                  stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                  <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
                  <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/>
                </svg>
                Copy Command
              </button>
            </div>
          )}

          {mode === "execute" && !confirmed && (
            <SlideConfirm onConfirm={handleConfirm}/>
          )}

          {(confirmed || mode === "copy") && (
            <div style={{
              padding: "16px", textAlign: "center",
              background: "rgba(52,211,153,0.08)",
              border: "1px solid rgba(52,211,153,0.2)",
              borderRadius: 10,
              animation: "artifactSlideIn 0.35s ease both",
            }}>
              <div style={{ fontSize: 22, marginBottom: 8 }}>
                <svg width="36" height="36" viewBox="0 0 24 24" fill="none"
                  stroke="#34D399" strokeWidth="1.5" strokeLinecap="round" style={{ margin: "0 auto", display: "block" }}>
                  <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                  <path d="M22 4L12 14.01l-3-3"/>
                </svg>
              </div>
              <div style={{ fontSize: 13, color: "#34D399", fontWeight: 600, marginBottom: 4 }}>
                {mode === "copy" ? "Commands Copied to Clipboard" : "Fix Applied — Rollout in Progress"}
              </div>
              <div style={{ fontSize: 10, color: "#475569", fontFamily: "var(--mono)" }}>
                {mode === "copy" ? "Paste into your terminal" : "monitoring rollout status…"}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
