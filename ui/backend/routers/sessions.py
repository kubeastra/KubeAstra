"""Session management endpoints.

GET  /api/sessions/{session_id}/history      — load chat history on page mount
DELETE /api/sessions/{session_id}/history    — clear history ("New chat")
GET  /api/sessions/{session_id}/ssh-target   — restore saved SSH host/user/port
POST /api/sessions/{session_id}/ssh-target   — save SSH target after connect
DELETE /api/sessions/{session_id}/ssh-target — clear on disconnect
"""

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

import db

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
