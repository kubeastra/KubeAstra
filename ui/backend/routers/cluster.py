"""Cluster connection management endpoints.

GET  /api/cluster/autodetect           — detect local kubeconfig contexts
POST /api/cluster/connect/kubeconfig   — upload kubeconfig, get contexts
POST /api/cluster/connect/context      — select context and connect
POST /api/cluster/disconnect           — disconnect and clean up
GET  /api/cluster/status               — current connection status for a session
"""

import atexit
import logging
import os
import re
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import yaml
from fastapi import APIRouter
from pydantic import BaseModel

import db

logger = logging.getLogger(__name__)

router = APIRouter()

# Directory for session-scoped temp kubeconfig files
_TEMP_DIR = Path(tempfile.gettempdir()) / "kubeastra-kubeconfigs"
_TEMP_DIR.mkdir(exist_ok=True)


# ── Models ────────────────────────────────────────────────────────────────────

class KubeconfigBody(BaseModel):
    """Kubeconfig content submitted by the user."""
    content: str
    session_id: str


class ContextSelectBody(BaseModel):
    """Context selection after kubeconfig parsing."""
    session_id: str
    context_name: str
    mode: str = "kubeconfig-upload"  # "autodetect" | "kubeconfig-upload"
    kubeconfig_path: Optional[str] = None  # set by backend, not user


class DisconnectBody(BaseModel):
    session_id: str


class KubeContext(BaseModel):
    """A single kubeconfig context."""
    name: str
    cluster: str
    server: str
    user: str
    namespace: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_kubeconfig(content: str) -> list[KubeContext]:
    """Parse kubeconfig YAML and extract context info."""
    try:
        config = yaml.safe_load(content)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML: {e}")

    if not isinstance(config, dict) or "contexts" not in config:
        raise ValueError("Not a valid kubeconfig file (missing 'contexts' key)")

    # Build lookup maps
    clusters_map = {}
    for c in config.get("clusters", []):
        name = c.get("name", "")
        cluster_data = c.get("cluster", {})
        clusters_map[name] = cluster_data.get("server", "")

    users_map = {}
    for u in config.get("users", []):
        users_map[u.get("name", "")] = u.get("name", "")

    contexts = []
    for ctx in config.get("contexts", []):
        ctx_name = ctx.get("name", "")
        ctx_data = ctx.get("context", {})
        cluster_name = ctx_data.get("cluster", "")
        user_name = ctx_data.get("user", "")
        namespace = ctx_data.get("namespace", "default")

        contexts.append(KubeContext(
            name=ctx_name,
            cluster=cluster_name,
            server=clusters_map.get(cluster_name, ""),
            user=user_name,
            namespace=namespace,
        ))

    return contexts


def _sanitize_session_id(session_id: str) -> str:
    """Strip anything that isn't alphanumeric or hyphen to prevent path traversal."""
    sanitized = re.sub(r"[^a-zA-Z0-9\-]", "", session_id)
    if not sanitized:
        raise ValueError("Invalid session ID")
    return sanitized[:64]  # cap length


def _write_temp_kubeconfig(session_id: str, content: str) -> str:
    """Write kubeconfig to a session-scoped temp file. Returns the file path."""
    safe_id = _sanitize_session_id(session_id)
    path = _TEMP_DIR / f"ka-{safe_id}.yaml"
    # Verify the resolved path is inside _TEMP_DIR (defense in depth)
    if not path.resolve().parent == _TEMP_DIR.resolve():
        raise ValueError("Invalid session path")
    path.write_text(content)
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600
    logger.info("Wrote temp kubeconfig for session %s (path not logged for security)", safe_id)
    return str(path)


def _delete_temp_kubeconfig(path: Optional[str]) -> None:
    """Delete a temp kubeconfig file if it exists."""
    if not path:
        return
    try:
        p = Path(path)
        if p.exists() and str(p).startswith(str(_TEMP_DIR)):
            p.unlink()
            logger.info("Deleted temp kubeconfig: %s", p.name)
    except Exception as e:
        logger.warning("Failed to delete temp kubeconfig: %s", e)


def _connectivity_check(
    kubeconfig_path: Optional[str] = None,
    context: Optional[str] = None,
) -> dict:
    """Run kubectl cluster-info to verify connectivity. Returns cluster info or error."""
    cmd = ["kubectl", "cluster-info"]
    if kubeconfig_path:
        cmd.extend(["--kubeconfig", kubeconfig_path])
    if context:
        cmd.extend(["--context", context])

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            # Extract control plane URL from output
            lines = result.stdout.strip().split("\n")
            server_url = ""
            for line in lines:
                if "control plane" in line.lower() or "master" in line.lower():
                    # The URL is usually the last word on the line
                    parts = line.split()
                    for part in parts:
                        if part.startswith("http") or "\x1b" in part:
                            # Strip all ANSI escape codes (colors, reset, bold, etc.)
                            cleaned = re.sub(r"\x1b\[[0-9;]*m", "", part).strip()
                            if cleaned.startswith("http"):
                                server_url = cleaned
                                break
            return {"ok": True, "server_url": server_url, "output": lines[0] if lines else ""}
        else:
            return {"ok": False, "error": result.stderr.strip()[:500]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Connection timed out after 10 seconds"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _get_local_kubeconfig_path() -> Optional[str]:
    """Find the local kubeconfig file path."""
    # Check KUBECONFIG env var first
    env_path = os.environ.get("KUBECONFIG")
    if env_path:
        # KUBECONFIG can be colon-separated; use the first existing path
        for p in env_path.split(os.pathsep):
            if Path(p).is_file():
                return p

    # Default path
    default = Path.home() / ".kube" / "config"
    if default.is_file():
        return str(default)

    return None


def _is_in_cluster() -> bool:
    """Check if running inside a Kubernetes cluster (ServiceAccount mounted)."""
    return Path("/var/run/secrets/kubernetes.io/serviceaccount/token").exists()


# ── Cleanup on shutdown ───────────────────────────────────────────────────────

def _cleanup_temp_files():
    """Remove all temp kubeconfig files on process exit."""
    try:
        for f in _TEMP_DIR.glob("ka-*.yaml"):
            f.unlink()
        logger.info("Cleaned up temp kubeconfig files")
    except Exception as e:
        logger.warning("Cleanup failed: %s", e)


atexit.register(_cleanup_temp_files)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/cluster/autodetect")
def autodetect():
    """Detect available cluster contexts from local kubeconfig or in-cluster SA."""
    # Check in-cluster first
    if _is_in_cluster():
        return {
            "in_cluster": True,
            "contexts": [],
            "message": "Running in-cluster with mounted ServiceAccount.",
        }

    # Check local kubeconfig
    kubeconfig_path = _get_local_kubeconfig_path()
    if not kubeconfig_path:
        return {
            "in_cluster": False,
            "contexts": [],
            "kubeconfig_path": None,
            "message": "No kubeconfig found. Upload one or use SSH.",
        }

    try:
        content = Path(kubeconfig_path).read_text()
        contexts = _parse_kubeconfig(content)

        # Get current context
        current_context = None
        try:
            config = yaml.safe_load(content)
            current_context = config.get("current-context")
        except Exception:
            pass

        return {
            "in_cluster": False,
            "contexts": [c.model_dump() for c in contexts],
            "kubeconfig_path": kubeconfig_path,
            "current_context": current_context,
            "message": f"Found {len(contexts)} context(s) in {kubeconfig_path}",
        }
    except Exception as e:
        return {
            "in_cluster": False,
            "contexts": [],
            "kubeconfig_path": kubeconfig_path,
            "error": str(e),
            "message": f"Failed to parse kubeconfig: {e}",
        }


@router.post("/cluster/connect/kubeconfig")
def upload_kubeconfig(body: KubeconfigBody):
    """Accept pasted/uploaded kubeconfig content, write temp file, return contexts."""
    try:
        contexts = _parse_kubeconfig(body.content)
    except ValueError as e:
        return {"error": str(e), "contexts": []}

    if not contexts:
        return {"error": "No contexts found in kubeconfig", "contexts": []}

    # Write to session-scoped temp file
    temp_path = _write_temp_kubeconfig(body.session_id, body.content)

    # Get current-context if set
    current_context = None
    try:
        config = yaml.safe_load(body.content)
        current_context = config.get("current-context")
    except Exception:
        pass

    return {
        "contexts": [c.model_dump() for c in contexts],
        "kubeconfig_path": temp_path,
        "current_context": current_context,
        "message": f"Parsed {len(contexts)} context(s). Select one to connect.",
    }


@router.post("/cluster/connect/context")
def connect_context(body: ContextSelectBody):
    """Select a context and verify connectivity."""
    kubeconfig_path = body.kubeconfig_path
    context_name = body.context_name
    mode = body.mode

    # For autodetect, use the local kubeconfig path
    if mode == "autodetect" and not kubeconfig_path:
        kubeconfig_path = _get_local_kubeconfig_path()

    # Run connectivity check
    check = _connectivity_check(kubeconfig_path, context_name)

    if not check["ok"]:
        return {
            "connected": False,
            "error": check.get("error", "Connection failed"),
        }

    # Parse context details for display
    cluster_name = context_name
    server_url = check.get("server_url", "")
    namespace = "default"

    if kubeconfig_path:
        try:
            content = Path(kubeconfig_path).read_text()
            config = yaml.safe_load(content)
            for ctx in config.get("contexts", []):
                if ctx.get("name") == context_name:
                    ctx_data = ctx.get("context", {})
                    cluster_name = ctx_data.get("cluster", context_name)
                    namespace = ctx_data.get("namespace", "default")
                    break
        except Exception:
            pass

    # Save connection to DB
    db.save_cluster_connection(
        session_id=body.session_id,
        mode=mode,
        context_name=context_name,
        cluster_name=cluster_name,
        server_url=server_url,
        namespace=namespace,
        kubeconfig_path=kubeconfig_path if mode == "kubeconfig-upload" else None,
    )

    return {
        "connected": True,
        "cluster_name": cluster_name,
        "context_name": context_name,
        "server_url": server_url,
        "namespace": namespace,
        "mode": mode,
    }


@router.post("/cluster/disconnect")
def disconnect(body: DisconnectBody):
    """Disconnect from current cluster and clean up temp files."""
    kubeconfig_path = db.delete_cluster_connection(body.session_id)
    _delete_temp_kubeconfig(kubeconfig_path)

    return {"disconnected": True}


@router.get("/cluster/status/{session_id}")
def connection_status(session_id: str):
    """Return current connection status for a session."""
    conn = db.get_cluster_connection(session_id)
    if conn:
        return {
            "connected": True,
            "mode": conn["mode"],
            "context_name": conn["context_name"],
            "cluster_name": conn["cluster_name"],
            "server_url": conn["server_url"],
            "namespace": conn["namespace"],
        }

    # Check if SSH is connected
    ssh = db.get_ssh_target(session_id)
    if ssh:
        return {
            "connected": True,
            "mode": "ssh",
            "cluster_name": ssh["host"],
            "context_name": f"{ssh['username']}@{ssh['host']}",
            "server_url": "",
            "namespace": "",
        }

    return {"connected": False}
