"""SQLite persistence layer for chat history and SSH targets.

Database file location:
  - Default: ./chat_history.db  (next to main.py)
  - Override: DB_PATH environment variable

Tables:
  sessions    — one row per browser session (session_id from localStorage)
  messages    — every chat turn (user + assistant), linked to session
  ssh_targets — remembered SSH host/user/port per session (password never stored)
"""

import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Generator, List, Optional

logger = logging.getLogger(__name__)

DB_PATH = os.environ.get(
    "DB_PATH",
    str(Path(__file__).parent / "chat_history.db"),
)

# Maximum messages returned when loading history (keeps payloads small)
MAX_HISTORY_MESSAGES = 100


# ── Connection helper ─────────────────────────────────────────────────────────

@contextmanager
def _conn() -> Generator[sqlite3.Connection, None, None]:
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")   # safe concurrent reads
    con.execute("PRAGMA foreign_keys=ON")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


# ── Schema ────────────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id  TEXT PRIMARY KEY,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    last_active TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT    NOT NULL,
    role        TEXT    NOT NULL,   -- 'user' | 'assistant'
    content     TEXT    NOT NULL,
    tool_used   TEXT,
    result_json TEXT,               -- JSON-encoded result dict
    error       TEXT,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);

CREATE TABLE IF NOT EXISTS ssh_targets (
    session_id  TEXT PRIMARY KEY,
    host        TEXT NOT NULL,
    username    TEXT NOT NULL,
    port        INTEGER NOT NULL DEFAULT 22,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS cluster_connections (
    session_id      TEXT PRIMARY KEY,
    mode            TEXT NOT NULL,           -- 'autodetect' | 'kubeconfig-upload'
    context_name    TEXT NOT NULL,
    cluster_name    TEXT NOT NULL DEFAULT '',
    server_url      TEXT NOT NULL DEFAULT '',
    namespace       TEXT NOT NULL DEFAULT 'default',
    kubeconfig_path TEXT,                    -- temp file path for uploads, NULL for autodetect
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);
"""


def init_db() -> None:
    """Create tables if they don't exist. Called once at app startup."""
    with _conn() as con:
        con.executescript(_SCHEMA)
    logger.info(f"SQLite DB ready at {DB_PATH}")


# ── Session helpers ───────────────────────────────────────────────────────────

def upsert_session(session_id: str) -> None:
    """Create session if new, or bump last_active if existing."""
    with _conn() as con:
        con.execute(
            """
            INSERT INTO sessions(session_id) VALUES(?)
            ON CONFLICT(session_id) DO UPDATE SET last_active = datetime('now')
            """,
            (session_id,),
        )


# ── Message helpers ───────────────────────────────────────────────────────────

def save_message(
    session_id: str,
    role: str,
    content: str,
    tool_used: Optional[str] = None,
    result: Optional[dict] = None,
    error: Optional[str] = None,
) -> None:
    """Persist a single chat turn message."""
    upsert_session(session_id)
    result_json = json.dumps(result) if result is not None else None
    with _conn() as con:
        con.execute(
            """
            INSERT INTO messages(session_id, role, content, tool_used, result_json, error)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (session_id, role, content, tool_used, result_json, error),
        )


def get_history(session_id: str, limit: int = MAX_HISTORY_MESSAGES) -> List[dict]:
    """Return the last `limit` messages for a session, oldest first."""
    with _conn() as con:
        rows = con.execute(
            """
            SELECT role, content, tool_used, result_json, error, created_at
            FROM messages
            WHERE session_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()

    # Reverse so messages are oldest-first for the frontend
    result = []
    for row in reversed(rows):
        entry: dict = {
            "role": row["role"],
            "content": row["content"],
            "created_at": row["created_at"],
        }
        if row["tool_used"]:
            entry["tool_used"] = row["tool_used"]
        if row["result_json"]:
            try:
                entry["result"] = json.loads(row["result_json"])
            except Exception:
                pass
        if row["error"]:
            entry["error"] = row["error"]
        result.append(entry)
    return result


def clear_history(session_id: str) -> None:
    """Delete all messages for a session (used by 'New chat' button)."""
    with _conn() as con:
        con.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))


# ── SSH target helpers ────────────────────────────────────────────────────────

def save_ssh_target(session_id: str, host: str, username: str, port: int = 22) -> None:
    """Remember SSH host/user/port for a session. Password is never stored."""
    upsert_session(session_id)
    with _conn() as con:
        con.execute(
            """
            INSERT INTO ssh_targets(session_id, host, username, port)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                host = excluded.host,
                username = excluded.username,
                port = excluded.port,
                updated_at = datetime('now')
            """,
            (session_id, host, username, port),
        )


def get_ssh_target(session_id: str) -> Optional[dict]:
    """Return saved SSH target for a session, or None if not set."""
    with _conn() as con:
        row = con.execute(
            "SELECT host, username, port FROM ssh_targets WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    if row:
        return {"host": row["host"], "username": row["username"], "port": row["port"]}
    return None


def delete_ssh_target(session_id: str) -> None:
    """Clear saved SSH target (called on disconnect)."""
    with _conn() as con:
        con.execute("DELETE FROM ssh_targets WHERE session_id = ?", (session_id,))


# ── Cluster connection helpers ───────────────────────────────────────────────

def save_cluster_connection(
    session_id: str,
    mode: str,
    context_name: str,
    cluster_name: str = "",
    server_url: str = "",
    namespace: str = "default",
    kubeconfig_path: Optional[str] = None,
) -> None:
    """Save an active cluster connection for a session."""
    upsert_session(session_id)
    with _conn() as con:
        con.execute(
            """
            INSERT INTO cluster_connections(
                session_id, mode, context_name, cluster_name,
                server_url, namespace, kubeconfig_path
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                mode = excluded.mode,
                context_name = excluded.context_name,
                cluster_name = excluded.cluster_name,
                server_url = excluded.server_url,
                namespace = excluded.namespace,
                kubeconfig_path = excluded.kubeconfig_path,
                updated_at = datetime('now')
            """,
            (session_id, mode, context_name, cluster_name,
             server_url, namespace, kubeconfig_path),
        )


def get_cluster_connection(session_id: str) -> Optional[dict]:
    """Return the active cluster connection for a session, or None."""
    with _conn() as con:
        row = con.execute(
            """SELECT mode, context_name, cluster_name, server_url,
                      namespace, kubeconfig_path
               FROM cluster_connections WHERE session_id = ?""",
            (session_id,),
        ).fetchone()
    if row:
        return {
            "mode": row["mode"],
            "context_name": row["context_name"],
            "cluster_name": row["cluster_name"],
            "server_url": row["server_url"],
            "namespace": row["namespace"],
            "kubeconfig_path": row["kubeconfig_path"],
        }
    return None


def delete_cluster_connection(session_id: str) -> Optional[str]:
    """Delete cluster connection. Returns the kubeconfig_path for cleanup."""
    with _conn() as con:
        row = con.execute(
            "SELECT kubeconfig_path FROM cluster_connections WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        con.execute(
            "DELETE FROM cluster_connections WHERE session_id = ?",
            (session_id,),
        )
    return row["kubeconfig_path"] if row else None
