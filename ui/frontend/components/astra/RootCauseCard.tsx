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
  /** Manual fix steps from AI analysis (shown when no automated commands) */
  manualSteps?: string[];
  /** Prevention recommendation */
  prevention?: string;
}

const SEVERITY_COLORS = {
  critical: { bg: "var(--red-bg)", border: "var(--red-bd)", text: "var(--red)", iconBg: "#FEE2E2" },
  warning:  { bg: "var(--amber-bg)", border: "var(--amber-bd)", text: "var(--amber)", iconBg: "#FEF3C7" },
  info:     { bg: "var(--accent-a-bg)", border: "var(--accent-a-bd)", text: "var(--accent-a)", iconBg: "#CFFAFE" },
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
  manualSteps = [],
  prevention = "",
}: RootCauseCardProps) {
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const sev = SEVERITY_COLORS[severity];

  return (
    <div style={{
      maxWidth: 520,
      background: '#FFFFFF',
      border: '1px solid var(--rule)',
      borderRadius: 12,
      overflow: 'hidden',
      boxShadow: '0 4px 20px rgba(0,0,0,0.08), 0 1px 4px rgba(0,0,0,0.05)',
      animation: 'springIn 0.45s cubic-bezier(0.34,1.56,0.64,1) both',
    }}>
      {/* Header strip */}
      <div style={{
        padding: '11px 16px',
        background: sev.bg,
        borderBottom: `1px solid ${sev.border}`,
        display: 'flex', alignItems: 'center', gap: 10,
      }}>
        <div style={{
          width: 26, height: 26, borderRadius: 6,
          background: sev.iconBg, border: `1px solid ${sev.border}`,
          display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
        }}>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none"
            stroke={sev.text} strokeWidth="2.5" strokeLinecap="round">
            <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
            <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
          </svg>
        </div>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
            <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--ink)' }}>{title}</span>
            <span style={{
              fontSize: 9, fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase',
              background: sev.iconBg, border: `1px solid ${sev.border}`, color: sev.text,
              borderRadius: 3, padding: '1px 6px',
            }}>{severity}</span>
          </div>
          {(pod || namespace) && (
            <div style={{ fontSize: 10, color: 'var(--ink-3)', marginTop: 1, fontFamily: 'var(--mono)' }}>
              {pod}{namespace ? ` · ${namespace}` : ""}
            </div>
          )}
        </div>
        <div style={{ flex: 1 }}/>
        {confidence !== undefined && (
          <div style={{
            fontSize: 10, fontFamily: 'var(--mono)', color: 'var(--ink-4)',
            background: 'var(--paper-2)', border: '1px solid var(--rule)',
            borderRadius: 4, padding: '2px 7px',
          }}>
            confidence: {confidence.toFixed(2)}
          </div>
        )}
      </div>

      <div style={{ padding: '14px 16px' }}>
        {/* Summary */}
        {summary && (
          <p style={{ fontSize: 13, color: 'var(--ink-2)', lineHeight: 1.65, marginBottom: 14 }}>
            {summary}
          </p>
        )}

        {/* Metrics */}
        {metrics.length > 0 && (
          <div style={{ display: 'grid', gridTemplateColumns: `repeat(${Math.min(metrics.length, 4)},1fr)`, gap: 8, marginBottom: 14 }}>
            {metrics.map(m => (
              <div key={m.label} style={{
                background: 'var(--paper-2)', border: '1px solid var(--rule)',
                borderRadius: 7, padding: '9px 12px', textAlign: 'center',
              }}>
                <div style={{ fontSize: 18, fontWeight: 700, color: m.color, fontFamily: 'var(--mono)', letterSpacing: '-0.02em' }}>
                  {m.value}
                </div>
                <div style={{ fontSize: 9, color: 'var(--ink-4)', marginTop: 3, letterSpacing: '0.1em', textTransform: 'uppercase', fontWeight: 500 }}>
                  {m.label}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Raw evidence */}
        {evidence && (
          <div style={{
            border: '1px solid var(--rule)', borderRadius: 7,
            overflow: 'hidden', marginBottom: 14,
          }}>
            <button
              onClick={() => setEvidenceOpen(o => !o)}
              style={{
                width: '100%', padding: '7px 12px',
                background: 'var(--paper-2)', border: 'none', cursor: 'pointer',
                display: 'flex', alignItems: 'center', gap: 6,
                borderBottom: evidenceOpen ? '1px solid var(--rule)' : 'none',
              }}
            >
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none"
                stroke="var(--ink-4)" strokeWidth="2" strokeLinecap="round">
                <polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>
              </svg>
              <span style={{ fontSize: 10, color: 'var(--ink-3)', fontFamily: 'var(--mono)', fontWeight: 500 }}>
                Raw Evidence
              </span>
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none"
                stroke="var(--ink-4)" strokeWidth="2" strokeLinecap="round"
                style={{ marginLeft: 'auto', transform: evidenceOpen ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }}>
                <path d="M6 9l6 6 6-6"/>
              </svg>
            </button>
            {evidenceOpen && (
              <div style={{
                padding: '10px 14px', background: '#FAFAF8',
                fontFamily: 'var(--mono)', fontSize: 11, lineHeight: 1.9,
                maxHeight: 200, overflowY: 'auto',
              }}>
                {evidence.split('\n').map((line, i) => (
                  <div key={i} style={{
                    color: line.startsWith('#') ? 'var(--accent)' :
                           line.startsWith('>') ? 'var(--amber)' :
                           line.startsWith('!') ? 'var(--red)' :
                           line.startsWith('  ') ? 'var(--ink-2)' : 'var(--ink-3)',
                    fontWeight: line.startsWith('#') ? 600 : 400,
                  }}>
                    {line || <br/>}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* CTA — either executable fix button or manual steps */}
        {onReviewExecute ? (
          <button
            onClick={onReviewExecute}
            style={{
              width: '100%', padding: '11px',
              background: '#FFFBEB',
              border: '1px solid #FCD34D',
              borderRadius: 8, cursor: 'pointer',
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
              transition: 'all 0.18s ease',
            }}
            onMouseEnter={e => {
              e.currentTarget.style.background = '#FEF3C7';
              e.currentTarget.style.boxShadow = '0 2px 12px rgba(217,119,6,0.2)';
            }}
            onMouseLeave={e => {
              e.currentTarget.style.background = '#FFFBEB';
              e.currentTarget.style.boxShadow = 'none';
            }}
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none"
              stroke="var(--amber)" strokeWidth="2.5" strokeLinecap="round">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
            </svg>
            <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--amber)', letterSpacing: '0.04em' }}>
              Review &amp; Execute Fix
            </span>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none"
              stroke="var(--amber)" strokeWidth="2.5" strokeLinecap="round">
              <path d="M5 12h14M12 5l7 7-7 7"/>
            </svg>
          </button>
        ) : manualSteps.length > 0 ? (
          <div style={{
            background: 'var(--paper-2)', border: '1px solid var(--rule)',
            borderRadius: 8, padding: '12px 14px',
          }}>
            <div style={{
              display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8,
            }}>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none"
                stroke="var(--accent)" strokeWidth="2.5" strokeLinecap="round">
                <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
                <line x1="16" y1="13" x2="8" y2="13"/>
                <line x1="16" y1="17" x2="8" y2="17"/>
              </svg>
              <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--accent)', letterSpacing: '0.04em' }}>
                Manual Steps Required
              </span>
            </div>
            <ol style={{
              margin: 0, paddingLeft: 18,
              fontSize: 12, color: 'var(--ink-2)', lineHeight: 1.7,
            }}>
              {manualSteps.map((step, i) => (
                <li key={i} style={{ marginBottom: 4 }}>{step}</li>
              ))}
            </ol>
            {prevention && (
              <div style={{
                marginTop: 10, paddingTop: 8, borderTop: '1px solid var(--rule)',
                fontSize: 11, color: 'var(--ink-3)', lineHeight: 1.5,
              }}>
                <strong style={{ color: 'var(--ink-2)' }}>Prevention:</strong> {prevention}
              </div>
            )}
          </div>
        ) : null}
      </div>
    </div>
  );
}
