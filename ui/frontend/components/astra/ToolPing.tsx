"use client";

import React from "react";

const TOOL_COLORS: Record<string, { bg: string; text: string; dot: string }> = {
  kubectl:    { bg: '#DBEAFE', text: '#1D4ED8', dot: '#2563EB' },
  prometheus: { bg: '#FEF3C7', text: '#B45309', dot: '#D97706' },
  logs:       { bg: '#ECFEFF', text: '#0E7490', dot: '#0891B2' },
  events:     { bg: '#EDE9FE', text: '#6D28D9', dot: '#7C3AED' },
  topology:   { bg: '#DCFCE7', text: '#15803D', dot: '#16A34A' },
  describe:   { bg: '#FEF3C7', text: '#B45309', dot: '#D97706' },
  ai:         { bg: '#F1F5F9', text: '#475569', dot: '#94A3B8' },
};

const TOOL_RESULTS: Record<string, string> = {
  kubectl:    '→ CrashLoopBackOff · restarts=12',
  prometheus: '→ RSS 142Mi > limit 128Mi',
  logs:       '→ OOMKilled · signal: killed',
  events:     '→ 3× OOMKilling / 8min',
  topology:   '→ blast radius: 2 services',
};

export default function ToolPing({ tool, status, result, delay = 0 }: {
  tool: string;
  status: "pending" | "running" | "done";
  result?: string;
  delay?: number;
}) {
  const tc = TOOL_COLORS[tool] || { bg: '#F1F5F9', text: '#475569', dot: '#94A3B8' };
  
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 8,
      animation: `springIn 0.35s cubic-bezier(0.34,1.56,0.64,1) ${delay}ms both`,
    }}>
      {/* Dot */}
      <div style={{ position: 'relative', width: 8, height: 8, flexShrink: 0 }}>
        <div style={{
          width: 8, height: 8, borderRadius: '50%',
          background: status === 'pending' ? '#D1D5DB' : tc.dot,
          boxShadow: status === 'running' ? `0 0 0 2px ${tc.dot}40` : 'none',
          animation: status === 'running' ? 'blink 1s ease-in-out infinite' : 'none',
        }}/>
        {status === 'running' && (
          <div style={{
            position: 'absolute', inset: -3, borderRadius: '50%',
            border: `1.5px solid ${tc.dot}`,
            animation: 'pulseRing 1.4s ease-out infinite',
          }}/>
        )}
      </div>
      {/* Badge */}
      <span style={{
        fontSize: 10, fontFamily: 'var(--mono)', fontWeight: 500,
        background: status === 'pending' ? '#F1F5F9' : tc.bg,
        color: status === 'pending' ? '#9CA3AF' : tc.text,
        border: `1px solid ${status === 'pending' ? '#E5E7EB' : tc.dot + '40'}`,
        borderRadius: 4, padding: '1px 7px', letterSpacing: '0.03em',
        transition: 'all 0.3s ease',
      }}>
        {tool}
      </span>
      {/* Result */}
      {status === 'done' && (
        <span style={{ fontSize: 10, color: 'var(--ink-3)', fontFamily: 'var(--mono)' }}>
          {result ? `→ ${result}` : TOOL_RESULTS[tool] || '→ done'}
        </span>
      )}
      {status === 'running' && (
        <span style={{
          fontSize: 10, color: tc.dot, fontFamily: 'var(--mono)',
          animation: 'blink 0.9s step-end infinite',
        }}>running…</span>
      )}
    </div>
  );
}
