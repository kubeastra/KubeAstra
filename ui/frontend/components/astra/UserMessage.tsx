"use client";

/** UserMessage — right-aligned chat bubble for user messages */

interface UserMessageProps {
  text: string;
  time?: string;
}

export default function UserMessage({ text, time }: UserMessageProps) {
  return (
    <div style={{ display: 'flex', justifyContent: 'flex-end', animation: 'springIn 0.3s ease both' }}>
      <div style={{
        maxWidth: 440,
        background: 'var(--accent-bg)',
        border: '1px solid var(--accent-bd)',
        borderRadius: '12px 12px 3px 12px',
        padding: '10px 14px',
      }}>
        <div style={{ fontSize: 13, color: 'var(--ink)', lineHeight: 1.55 }}>{text}</div>
        {time && (
          <div style={{ fontSize: 9, color: 'var(--ink-4)', marginTop: 4, textAlign: 'right', fontFamily: 'var(--mono)' }}>
            {time}
          </div>
        )}
      </div>
    </div>
  );
}
