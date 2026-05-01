"use client";

import React from "react";

/** AstraMessage — assistant message wrapper with teal star avatar */

interface AstraMessageProps {
  children?: React.ReactNode;
  time?: string;
  text?: string;
}

export default function AstraMessage({ children, time, text }: AstraMessageProps) {
  return (
    <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start', animation: 'springIn 0.35s ease both' }}>
      {/* Avatar */}
      <div style={{
        width: 28, height: 28, borderRadius: 8, flexShrink: 0,
        background: 'var(--accent-bg)', border: '1px solid var(--accent-bd)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', marginTop: 1,
        boxShadow: '0 1px 4px rgba(0,0,0,0.06)',
      }}>
        <svg viewBox="0 0 16 16" width="13" height="13">
          <path d="M8,2 L8.6,6.4 L12.5,4.4 L9.4,8 L12.5,11.6 L8.6,9.6 L8,14 L7.4,9.6 L3.5,11.6 L6.6,8 L3.5,4.4 L7.4,6.4 Z"
            fill="var(--accent)"/>
        </svg>
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
          <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--accent)', letterSpacing: '0.03em' }}>Astra</span>
          {time && <span style={{ fontSize: 9, color: 'var(--ink-4)', fontFamily: 'var(--mono)' }}>{time}</span>}
        </div>
        {text && (
          <p style={{ fontSize: 13, color: 'var(--ink-2)', lineHeight: 1.6, marginBottom: children ? 10 : 0 }}>
            {text}
          </p>
        )}
        {children}
      </div>
    </div>
  );
}
