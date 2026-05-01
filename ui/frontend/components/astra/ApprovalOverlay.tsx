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
      border: '1px solid var(--rule)', borderRadius: 8, overflow: 'hidden',
      background: '#FAFAF8',
    }}>
      <div style={{
        padding: '7px 14px', borderBottom: '1px solid var(--rule)',
        background: 'var(--paper-2)',
        display: 'flex', alignItems: 'center', gap: 8,
      }}>
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none"
          stroke="var(--ink-4)" strokeWidth="2" strokeLinecap="round">
          <circle cx="18" cy="18" r="3"/><circle cx="6" cy="6" r="3"/>
          <path d="M6 21V9a9 9 0 009 9"/>
        </svg>
        <span style={{ fontSize: 10, color: 'var(--ink-3)', fontFamily: 'var(--mono)' }}>
          proposed changes
        </span>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
          <span style={{ fontSize: 9, fontFamily: 'var(--mono)', background: 'var(--red-bg)', color: 'var(--red)', padding: '1px 6px', borderRadius: 3 }}>
            -{lines.filter(l => l.t === "remove").length}
          </span>
          <span style={{ fontSize: 9, fontFamily: 'var(--mono)', background: 'var(--green-bg)', color: 'var(--green)', padding: '1px 6px', borderRadius: 3 }}>
            +{lines.filter(l => l.t === "add").length}
          </span>
        </div>
      </div>
      <div style={{ padding: '6px 0', fontFamily: 'var(--mono)', fontSize: 11, lineHeight: 1.9 }}>
        {lines.map((l, i) => (
          <div key={i} style={{
            padding: '0 14px',
            background: l.t === 'add' ? 'var(--green-bg)' : l.t === 'remove' ? 'var(--red-bg)' : l.t === 'hunk' ? 'var(--accent-b-bg)' : 'transparent',
            color: l.t === 'add' ? 'var(--green)' : l.t === 'remove' ? 'var(--red)' : l.t === 'hunk' ? 'var(--accent-b)' : 'var(--ink-3)',
            borderLeft: l.t === 'add' ? '3px solid var(--green-bd)' : l.t === 'remove' ? '3px solid var(--red-bd)' : '3px solid transparent',
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
      position: 'relative', height: 52,
      background: done ? 'var(--green-bg)' : 'var(--amber-bg)',
      border: `1.5px solid ${done ? 'var(--green-bd)' : 'var(--amber-bd)'}`,
      borderRadius: 10, overflow: 'hidden', userSelect: 'none',
      transition: 'all 0.3s',
    }}>
      <div style={{
        position: 'absolute', left: 0, top: 0, bottom: 0,
        width: `${pct * 100}%`,
        background: `rgba(217,119,6,${pct * 0.12})`,
        transition: dragging ? 'none' : 'width 0.4s ease',
      }}/>
      <div style={{
        position: 'absolute', inset: 0, display: 'flex',
        alignItems: 'center', justifyContent: 'center', pointerEvents: 'none',
      }}>
        <span style={{
          fontSize: 11, fontWeight: 600, letterSpacing: '0.12em', textTransform: 'uppercase',
          color: done ? 'var(--green)' : 'var(--amber)',
          opacity: done ? 1 : Math.max(0, 1 - pct * 1.8),
          transition: 'opacity 0.15s',
        }}>
          {done ? '✓ Fix Queued for Rollout' : 'Slide to Confirm Execution'}
        </span>
      </div>
      {!done && (
        <div
          onMouseDown={onMouseDown} onTouchStart={onTouchStart}
          style={{
            position: 'absolute', left: pos + 2, top: 2, bottom: 2, width: THUMB,
            background: 'linear-gradient(135deg, #F59E0B, #D97706)',
            border: '1px solid #FBBF24',
            borderRadius: 7, cursor: 'grab',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            boxShadow: `0 2px ${4 + pct * 12}px rgba(217,119,6,${0.25 + pct * 0.35})`,
            transition: dragging ? 'none' : 'left 0.35s cubic-bezier(0.34,1.56,0.64,1)',
          }}
        >
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
      position: 'fixed', inset: 0, zIndex: 100,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'rgba(26,26,24,0.4)', backdropFilter: 'blur(6px)',
      animation: 'overlayIn 0.25s ease both',
    }}>
      <div style={{
        width: 540, maxHeight: '88vh',
        background: '#FFFFFF',
        border: '1px solid var(--rule)',
        borderRadius: 16, overflow: 'hidden',
        boxShadow: '0 32px 80px rgba(0,0,0,0.18), 0 0 0 1px rgba(0,0,0,0.04)',
        animation: 'modalSpring 0.4s cubic-bezier(0.34,1.56,0.64,1) both',
        display: 'flex', flexDirection: 'column',
      }}>
        {/* Header */}
        <div style={{
          padding: '14px 18px', background: 'var(--amber-bg)',
          borderBottom: '1px solid var(--amber-bd)',
          display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0,
        }}>
          <div style={{
            width: 32, height: 32, borderRadius: 8,
            background: '#FEF3C7', border: '1px solid #FDE68A',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
              stroke="var(--amber)" strokeWidth="2.5" strokeLinecap="round">
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
              <path d="M7 11V7a5 5 0 0110 0v4"/>
            </svg>
          </div>
          <div>
            <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--ink)' }}>
              Impact Preview — Approval Required
            </div>
            <div style={{ fontSize: 10, color: 'var(--amber)', fontFamily: 'var(--mono)', marginTop: 1 }}>
              {namespace ? `${namespace} · ` : ""}{targetResource || "cluster resource"}
            </div>
          </div>
          <div style={{ flex: 1 }}/>
          <button onClick={onClose} style={{
            background: 'none', border: 'none', cursor: 'pointer',
            color: 'var(--ink-4)', padding: 4, borderRadius: 5,
          }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 14 }}>
          {/* Preflight */}
          <div>
            <div style={{ fontSize: 10, color: 'var(--ink-4)', letterSpacing: '0.12em', textTransform: 'uppercase', fontWeight: 600, marginBottom: 8 }}>
              Preflight Checks
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
              {PREFLIGHT_CHECKS.map((c, i) => (
                <div key={i} style={{
                  display: 'flex', alignItems: 'center', gap: 8,
                  padding: '6px 10px',
                  background: 'var(--green-bg)', border: '1px solid var(--green-bd)',
                  borderRadius: 5,
                  animation: `springIn 0.3s cubic-bezier(0.34,1.56,0.64,1) ${i * 70}ms both`,
                }}>
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none"
                    stroke="var(--green)" strokeWidth="2.5" strokeLinecap="round">
                    <path d="M20 6L9 17l-5-5"/>
                  </svg>
                  <span style={{ fontSize: 11, color: 'var(--ink-2)' }}>{c}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Commands */}
          {diffLines.length > 0 && (
            <div>
              <div style={{ fontSize: 10, color: 'var(--ink-4)', letterSpacing: '0.12em', textTransform: 'uppercase', fontWeight: 600, marginBottom: 8 }}>
                Proposed Changes
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
                  background: 'var(--amber-bg)',
                  border: '1px solid var(--amber-bd)',
                  borderRadius: 8, cursor: "pointer",
                  display: "flex", alignItems: "center", justifyContent: "center", gap: 6,
                  color: 'var(--amber)', fontSize: 12, fontWeight: 600,
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
                  background: 'var(--accent-bg)',
                  border: '1px solid var(--accent-bd)',
                  borderRadius: 8, cursor: "pointer",
                  display: "flex", alignItems: "center", justifyContent: "center", gap: 6,
                  color: 'var(--accent)', fontSize: 12, fontWeight: 600,
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
              padding: '18px', textAlign: 'center',
              background: 'var(--green-bg)', border: '1px solid var(--green-bd)',
              borderRadius: 10, animation: 'springIn 0.35s ease both',
            }}>
              <svg width="36" height="36" viewBox="0 0 24 24" fill="none"
                stroke="var(--green)" strokeWidth="1.5" strokeLinecap="round" style={{ margin: "0 auto 10px", display: "block" }}>
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                <path d="M22 4L12 14.01l-3-3"/>
              </svg>
              <div style={{ fontSize: 13, color: 'var(--green)', fontWeight: 600, marginBottom: 4 }}>
                {mode === "copy" ? "Commands Copied to Clipboard" : "Fix Applied — Rollout in Progress"}
              </div>
              <div style={{ fontSize: 10, color: 'var(--ink-3)', fontFamily: "var(--mono)" }}>
                {mode === "copy" ? "Paste into your terminal" : "monitoring rollout status…"}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
