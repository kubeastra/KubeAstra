"use client";

/** UserMessage — right-aligned chat bubble for user messages */

interface UserMessageProps {
  text: string;
  time?: string;
}

export default function UserMessage({ text, time }: UserMessageProps) {
  return (
    <div style={{
      display: "flex", justifyContent: "flex-end",
      animation: "artifactSlideIn 0.3s cubic-bezier(0.34,1.56,0.64,1) both",
    }}>
      <div style={{
        maxWidth: 420,
        background: "rgba(79,142,247,0.12)",
        border: "1px solid rgba(79,142,247,0.2)",
        borderRadius: "12px 12px 3px 12px",
        padding: "10px 14px",
      }}>
        <div style={{ fontSize: 13, color: "#CBD5E1", lineHeight: 1.5 }}>{text}</div>
        {time && (
          <div style={{ fontSize: 9, color: "#2A3A50", marginTop: 4, textAlign: "right", fontFamily: "var(--mono)" }}>
            {time}
          </div>
        )}
      </div>
    </div>
  );
}
