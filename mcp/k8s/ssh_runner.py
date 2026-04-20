"""SSH-based kubectl runner.

Executes kubectl commands on a remote Kubernetes master node via SSH,
using the exact same interface as KubectlRunner so all wrapper functions
work without any signature changes.

The remote node must have kubectl installed and a working kubeconfig for
the SSH user (always true for a kubeadm master node's default admin user).

Usage (injected per-request via set_runner in chat.py):
    runner = SSHKubectlRunner("10.0.1.5", "ansible", "s3cr3t")
    token = set_runner(runner)
    try:
        result = get_pods("default")   # transparently uses SSH
    finally:
        runner.close()
        runner_ctx.reset(token)
"""

import json
import logging
from datetime import datetime
from typing import List, Optional

from config.settings import settings
from k8s.kubectl_runner import KubectlError, KubectlResult, KubectlTimeoutError

logger = logging.getLogger(__name__)


class SSHConnectionError(Exception):
    """Raised when the SSH connection to the remote node cannot be established."""
    pass


class SSHKubectlRunner:
    """
    Drop-in replacement for KubectlRunner that runs kubectl on a remote
    Kubernetes master node via SSH (paramiko).

    Same run() / run_json() interface — all wrappers work unchanged.
    """

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        port: int = 22,
        timeout: Optional[int] = None,
    ):
        self.host = host
        self.username = username
        self._password = password          # Never logged
        self.port = port
        self.timeout = timeout or settings.kubectl_timeout_seconds
        self.max_output_bytes = settings.max_output_bytes
        self._client = None

    # ── Connection management ─────────────────────────────────────────────────

    def connect(self) -> None:
        """Open SSH connection. Called lazily on first run() call."""
        try:
            import paramiko
        except ImportError:
            raise SSHConnectionError(
                "paramiko is not installed. Run: pip install paramiko"
            )

        try:
            client = paramiko.SSHClient()
            # AutoAddPolicy is acceptable for internal kubeadm VMs where host
            # keys are not pre-registered in a known_hosts file.
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self._password,
                timeout=self.timeout,
                look_for_keys=False,
                allow_agent=False,
            )
            self._client = client
            logger.info(f"SSH connected: {self.username}@{self.host}:{self.port}")
        except Exception as e:
            try:
                import paramiko as _p
                if isinstance(e, _p.AuthenticationException):
                    raise SSHConnectionError(
                        f"SSH authentication failed for {self.username}@{self.host}. "
                        "Check username and password."
                    )
            except ImportError:
                pass
            raise SSHConnectionError(
                f"SSH connection to {self.host}:{self.port} failed: {e}"
            )

    def close(self) -> None:
        """Close the SSH connection."""
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None
            logger.info(f"SSH disconnected from {self.host}")

    def _ensure_connected(self) -> None:
        if self._client is None:
            self.connect()

    # ── kubectl execution ─────────────────────────────────────────────────────

    def run(
        self,
        args: List[str],
        namespace: Optional[str] = None,
        capture_output: bool = True,   # ignored — SSH always captures
        max_output: Optional[int] = None,
    ) -> KubectlResult:
        """
        Run a kubectl command on the remote node via SSH exec_command.

        Builds the same command string that KubectlRunner would build
        locally, then executes it remotely via paramiko.

        Args:
            args: kubectl sub-args e.g. ["get", "pods", "-o", "json"]
            namespace: Optional -n <namespace> injected before args
            max_output: Max stdout bytes (default: settings.max_output_bytes)

        Returns:
            KubectlResult with remote stdout / stderr

        Raises:
            KubectlError: Remote kubectl exited non-zero
            KubectlTimeoutError: Command exceeded timeout
            SSHConnectionError: Cannot reach remote node
        """
        self._ensure_connected()

        # Build command list (mirrors KubectlRunner logic)
        parts: List[str] = ["kubectl"]
        if namespace:
            parts.extend(["-n", namespace])
        parts.extend(args)

        # Shell-safe string for exec_command
        cmd_str = " ".join(self._quote(p) for p in parts)
        logger.info(f"SSH exec on {self.host}: {cmd_str}")

        limit = max_output if max_output is not None else self.max_output_bytes
        start = datetime.now()

        try:
            _, stdout_ch, stderr_ch = self._client.exec_command(
                cmd_str, timeout=self.timeout
            )

            # Read with size cap (+1 to detect overflow)
            raw_out = stdout_ch.read(limit + 1)
            raw_err = stderr_ch.read(self.max_output_bytes + 1)
            returncode = stdout_ch.channel.recv_exit_status()
            duration = (datetime.now() - start).total_seconds()

            stdout = raw_out.decode("utf-8", errors="replace")
            stderr = raw_err.decode("utf-8", errors="replace")
            truncated = False

            if len(raw_out) > limit:
                stdout = stdout[:limit] + "\n[... output truncated ...]"
                truncated = True
            if len(raw_err) > self.max_output_bytes:
                stderr = stderr[:self.max_output_bytes] + "\n[... output truncated ...]"
                truncated = True

            result = KubectlResult(
                stdout=stdout,
                stderr=stderr,
                returncode=returncode,
                command=parts,
                duration_seconds=duration,
                truncated=truncated,
            )

            status = "SUCCESS" if result.success else "FAILED"
            logger.info(
                f"SSH kubectl {status} on {self.host} in {duration:.2f}s: {cmd_str}"
            )
            return result

        except (KubectlError, KubectlTimeoutError):
            raise
        except Exception as e:
            duration = (datetime.now() - start).total_seconds()
            err_str = str(e)

            if "timed out" in err_str.lower() or "timeout" in err_str.lower():
                self._client = None  # force reconnect next call
                raise KubectlTimeoutError(
                    f"kubectl timed out after {self.timeout}s on {self.host}",
                    -1,
                    f"SSH command exceeded timeout of {self.timeout}s",
                )

            if "closed" in err_str.lower() or "eof" in err_str.lower():
                self._client = None

            raise KubectlError(
                f"SSH kubectl error on {self.host}: {err_str}", -1, err_str
            )

    def run_json(
        self,
        args: List[str],
        namespace: Optional[str] = None,
    ) -> dict:
        """Run kubectl on the remote node and parse JSON output.

        Uses a 10 MB cap so JSON is never truncated mid-stream.
        """
        if "-o" not in args and "--output" not in args:
            args = list(args) + ["-o", "json"]

        JSON_MAX = 10 * 1024 * 1024  # 10 MB
        result = self.run(args, namespace=namespace, max_output=JSON_MAX)
        result.raise_for_status()

        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as e:
            raise KubectlError(
                f"Failed to parse kubectl JSON from {self.host}: {e}",
                result.returncode,
                result.stderr,
            )

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _quote(s: str) -> str:
        """Minimal shell quoting for exec_command arguments."""
        if s and all(c.isalnum() or c in "-_./=,:+" for c in s):
            return s
        return "'" + s.replace("'", "'\\''") + "'"

    def __repr__(self) -> str:
        return f"SSHKubectlRunner(host={self.host!r}, user={self.username!r})"
