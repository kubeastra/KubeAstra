"use client";

import { useState } from "react";

/** IntentBar — redesigned input bar with cluster context badge */

interface IntentBarProps {
  onSend: (text: string) => void;
  listening?: boolean;
  clusterName?: string;
  toolCount?: number;
}

export default function IntentBar({ onSend, listening, clusterName = "GKE-PROD", toolCount = 32 }: IntentBarProps) {
  const [val, setVal] = useState("");
  const submit = () => {
    if (!val.trim()) return;
    onSend(val.trim());
    setVal("");
  };

  return (
    <div style={{
      padding: '12px 18px 14px',
      borderTop: '1px solid var(--rule)',
      background: '#FFFFFF', flexShrink: 0,
    }}>
      <div style={{
        display: 'flex', alignItems: 'center',
        background: 'var(--paper)',
        border: `1.5px solid ${listening ? 'var(--accent)' : 'var(--rule-2)'}`,
        borderRadius: 10,
        boxShadow: listening ? '0 0 0 3px var(--accent-bd)' : '0 1px 4px rgba(0,0,0,0.05)',
        overflow: 'hidden',
        transition: 'border-color 0.25s, box-shadow 0.25s',
      }}>
        {/* Cluster context badge */}
        <div style={{
          padding: '0 12px', height: '100%',
          display: 'flex', alignItems: 'center',
          borderRight: '1px solid var(--rule)',
          flexShrink: 0,
        }}>
          <span style={{
            fontSize: 10, fontFamily: 'var(--mono)', fontWeight: 600,
            color: 'var(--accent)', letterSpacing: '0.06em',
            background: 'var(--accent-bg)', border: '1px solid var(--accent-bd)',
            borderRadius: 4, padding: '3px 8px',
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
            flex: 1, padding: '13px 14px',
            background: 'transparent', border: 'none', outline: 'none',
            color: 'var(--ink)', fontSize: 13, fontFamily: 'var(--sans)',
          }}
        />
        {/* Listening indicator */}
        {listening && (
          <div style={{ padding: '0 10px', display: 'flex', gap: 3, alignItems: 'center' }}>
            {[0,1,2].map(d => (
              <div key={d} style={{
                width: 4, height: 4, borderRadius: '50%', background: 'var(--accent)',
                animation: `dotBounce 1.2s ${d*0.2}s ease-in-out infinite`,
              }}/>
            ))}
          </div>
        )}
        {/* Send button */}
        <button onClick={submit} style={{
          padding: '0 16px', height: '100%', minHeight: 48,
          background: val.trim() ? 'var(--accent-bg)' : 'transparent',
          border: 'none', borderLeft: '1px solid var(--rule)',
          cursor: val.trim() ? 'pointer' : 'default',
          color: val.trim() ? 'var(--accent)' : 'var(--ink-4)',
          transition: 'all 0.2s',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <line x1="22" y1="2" x2="11" y2="13"/>
            <polygon points="22 2 15 22 11 13 2 9 22 2"/>
          </svg>
        </button>
      </div>
      <div style={{ marginTop: 6, textAlign: 'center', fontSize: 9, color: 'var(--ink-4)', fontFamily: 'var(--mono)' }}>
        Astra has access to {toolCount} investigative tools · {clusterName.toLowerCase()}
      </div>
    </div>
  );
}
