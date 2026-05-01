"use client";

import { useState } from "react";
import ToolPing from "./ToolPing";

export interface ToolStep {
  tool: string;
  status: "pending" | "running" | "done";
  result?: string;
}

interface ReasoningBubbleProps {
  steps: ToolStep[];
  thinking?: boolean;
}

export default function ReasoningBubble({ steps, thinking }: ReasoningBubbleProps) {
  const [collapsed, setCollapsed] = useState(false);
  const doneCount = steps.filter(s => s.status === 'done').length;

  return (
    <div style={{
      background: '#FFFFFF',
      border: '1px solid var(--rule)',
      borderRadius: 10,
      overflow: 'hidden',
      maxWidth: 500,
      boxShadow: '0 2px 8px rgba(0,0,0,0.06)',
      animation: 'springIn 0.4s cubic-bezier(0.34,1.56,0.64,1) both',
    }}>
      <div
        onClick={() => setCollapsed(c => !c)}
        style={{
          padding: '9px 12px',
          display: 'flex', alignItems: 'center', gap: 8,
          cursor: 'pointer',
          borderBottom: collapsed ? 'none' : '1px solid var(--rule)',
          background: 'var(--paper-2)',
        }}
      >
        {/* Astra mark */}
        <svg viewBox="0 0 16 16" width="14" height="14" style={{ flexShrink: 0 }}>
          <polygon points="8,0.5 14.9,4.25 14.9,11.75 8,15.5 1.1,11.75 1.1,4.25"
            fill="none" stroke="var(--accent)" strokeWidth="0.8" opacity="0.5"/>
          <path d="M8,3 L8.55,7.1 L12.1,5.5 L9,8 L12.1,10.5 L8.55,8.9 L8,13 L7.45,8.9 L3.9,10.5 L7,8 L3.9,5.5 L7.45,7.1 Z"
            fill="var(--accent)"/>
        </svg>
        <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--accent)', letterSpacing: '0.04em' }}>
          Investigation Trail
        </span>
        <span style={{ fontSize: 10, color: 'var(--ink-3)', fontFamily: 'var(--mono)' }}>
          {doneCount}/{steps.length} tools
        </span>
        {thinking && (
          <div style={{ display: 'flex', gap: 3, alignItems: 'center' }}>
            {[0,1,2].map(d => (
              <div key={d} style={{
                width: 3, height: 3, borderRadius: '50%', background: 'var(--accent)',
                animation: `dotBounce 1.2s ${d*0.2}s ease-in-out infinite`,
              }}/>
            ))}
          </div>
        )}
        {/* Progress bar */}
        <div style={{
          flex: 1, height: 2,
          background: 'var(--rule)', borderRadius: 1, overflow: 'hidden', marginLeft: 4,
        }}>
          <div style={{
            height: '100%', borderRadius: 1,
            background: 'var(--accent)',
            width: `${(doneCount / Math.max(1, steps.length)) * 100}%`,
            transition: 'width 0.5s ease',
          }}/>
        </div>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none"
          stroke="var(--ink-4)" strokeWidth="2" strokeLinecap="round"
          style={{ transform: collapsed ? 'rotate(-90deg)' : 'none', transition: 'transform 0.2s', flexShrink: 0 }}>
          <path d="M6 9l6 6 6-6"/>
        </svg>
      </div>
      {!collapsed && (
        <div style={{ padding: '12px', display: 'flex', flexDirection: 'column', gap: 10 }}>
          {steps.map((s, i) => (
            <ToolPing key={s.tool} tool={s.tool} status={s.status} result={s.result} delay={i * 60}/>
          ))}
        </div>
      )}
    </div>
  );
}
