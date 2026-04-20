"""FastAPI backend for the K8s DevOps Web UI.

Imports tool functions directly from mcp (via MCP_PATH env var)
so there is zero code duplication.

Run locally:
    MCP_PATH=../../mcp uvicorn main:app --reload --port 8000
"""

import os
import sys
import time
import uuid
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

# ── Resolve mcp path ───────────────────────────────────────────────
MCP_PATH = os.environ.get(
    "MCP_PATH",
    str(Path(__file__).resolve().parent.parent.parent / "mcp"),
)
if MCP_PATH not in sys.path:
    sys.path.insert(0, MCP_PATH)

# Load .env from MCP project so all settings (GEMINI_API_KEY etc.) are available
from dotenv import load_dotenv
_mcp_env = Path(MCP_PATH) / ".env"
if _mcp_env.exists():
    load_dotenv(str(_mcp_env))

import db
from routers import ai_tools, kubectl, recovery, health, chat, sessions

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(
    title="K8s DevOps Assistant API",
    description="REST API exposing all 32 mcp tools for team self-service",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    request_id = uuid.uuid4().hex[:12]
    request.state.request_id = request_id
    started_at = time.perf_counter()

    try:
        response = await call_next(request)
    except Exception:
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        logger.exception(
            "request_id=%s method=%s path=%s status=500 elapsed_ms=%.1f",
            request_id,
            request.method,
            request.url.path,
            elapsed_ms,
        )
        raise

    elapsed_ms = (time.perf_counter() - started_at) * 1000
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request_id=%s method=%s path=%s status=%s elapsed_ms=%.1f",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    return response

app.include_router(health.router, tags=["health"])
app.include_router(chat.router, prefix="/api", tags=["Chat"])
app.include_router(sessions.router, prefix="/api", tags=["Sessions"])
app.include_router(ai_tools.router, prefix="/api", tags=["AI Analysis"])
app.include_router(kubectl.router, prefix="/api", tags=["Kubectl"])
app.include_router(recovery.router, prefix="/api", tags=["Recovery"])
