"""Session management endpoints.

GET  /api/sessions/{session_id}/history       — load chat history on page mount
DELETE /api/sessions/{session_id}/history     — clear history ("New chat")
GET  /api/sessions/{session_id}/ssh-target    — restore saved SSH host/user/port
POST /api/sessions/{session_id}/ssh-target    — save SSH target after connect
DELETE /api/sessions/{session_id}/ssh-target  — clear on disconnect
POST /api/sessions/{session_id}/postmortem    — generate post-mortem from session
"""

import json
import logging
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

import db

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Models ────────────────────────────────────────────────────────────────────

class SSHTargetBody(BaseModel):
    host: str
    username: str
    port: int = 22


# ── History ───────────────────────────────────────────────────────────────────

@router.get("/sessions/{session_id}/history")
def get_history(session_id: str, limit: int = 100):
    """Return persisted messages for a session (oldest first)."""
    messages = db.get_history(session_id, limit=limit)
    return {"session_id": session_id, "messages": messages}


@router.delete("/sessions/{session_id}/history")
def clear_history(session_id: str):
    """Delete all messages for a session (New chat)."""
    db.clear_history(session_id)
    return {"ok": True}


# ── SSH target ────────────────────────────────────────────────────────────────

@router.get("/sessions/{session_id}/ssh-target")
def get_ssh_target(session_id: str):
    """Return saved SSH host/username/port, or null if none saved."""
    target = db.get_ssh_target(session_id)
    return {"ssh_target": target}


@router.post("/sessions/{session_id}/ssh-target")
def save_ssh_target(session_id: str, body: SSHTargetBody):
    """Persist SSH target after a successful connection. Password never stored."""
    db.save_ssh_target(session_id, body.host, body.username, body.port)
    return {"ok": True}


@router.delete("/sessions/{session_id}/ssh-target")
def delete_ssh_target(session_id: str):
    """Clear saved SSH target on disconnect."""
    db.delete_ssh_target(session_id)
    return {"ok": True}


# ── Post-mortem generation ───────────────────────────────────────────────────

@router.post("/sessions/{session_id}/postmortem")
def generate_postmortem(session_id: str):
    """Generate a post-mortem document from the session's investigation history.

    Reads all messages + tool results, asks the LLM to produce a structured
    post-mortem with: summary, timeline, root cause, impact, resolution, and
    action items.
    """
    messages = db.get_history(session_id, limit=200)
    if not messages:
        return {"error": "No messages found for this session."}

    # Build a condensed session transcript for the LLM
    transcript_parts = []
    for msg in messages:
        role = msg["role"].upper()
        text = msg["content"][:500]
        tool = msg.get("tool_used", "")
        result = msg.get("result")

        if tool and tool != "none":
            # Extract key findings from tool results
            result_summary = ""
            if isinstance(result, dict):
                react_steps = result.get("react_steps", [])
                if react_steps:
                    step_summaries = [
                        f"  - {s.get('action', '?')}: {s.get('thought', '')[:100]}"
                        for s in react_steps if s.get("action") != "answer"
                    ]
                    result_summary = "\n".join(step_summaries)
                else:
                    result_summary = json.dumps(result, default=str)[:400]
            transcript_parts.append(f"[{role}] (tool: {tool})\n{text}\n{result_summary}")
        else:
            transcript_parts.append(f"[{role}] {text}")

    transcript = "\n\n".join(transcript_parts)

    # Truncate to ~8000 chars to leave room for the system prompt
    if len(transcript) > 8000:
        transcript = transcript[:8000] + "\n\n...(truncated)"

    system = (
        "You are a post-incident report generator for Kubernetes operations. "
        "Given a session transcript of an investigation, produce a structured post-mortem.\n\n"
        "Use this format:\n\n"
        "# Post-Mortem: [Brief title]\n\n"
        "## Summary\n"
        "1-2 sentence overview of what happened.\n\n"
        "## Timeline\n"
        "Bullet points of key investigation steps and findings, in order.\n\n"
        "## Root Cause\n"
        "What specifically caused the issue.\n\n"
        "## Impact\n"
        "What was affected (pods, services, namespaces).\n\n"
        "## Resolution\n"
        "What was done or recommended to fix it.\n\n"
        "## Action Items\n"
        "- [ ] Preventive measures to avoid recurrence\n\n"
        "Use markdown formatting. Be specific — include pod names, error messages, and namespaces."
    )

    try:
        from services.llm import get_provider
        provider = get_provider()
        if not provider or not provider.enabled:
            return {"error": "No LLM provider configured. Set GEMINI_API_KEY or LLM_PROVIDER=ollama."}

        postmortem = provider.generate(
            f"Session transcript:\n\n{transcript}",
            system=system,
            temperature=0.2,
            max_tokens=1500,
        )

        return {"postmortem": postmortem, "session_id": session_id}

    except Exception as e:
        logger.warning(f"Post-mortem generation failed: {e}")
        return {"error": f"Failed to generate post-mortem: {e}"}
