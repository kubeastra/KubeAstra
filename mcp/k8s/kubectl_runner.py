"""Safe kubectl command runner with timeout and output limits."""

import contextvars
import json
import logging
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from config.settings import settings

logger = logging.getLogger(__name__)


class KubectlError(Exception):
    """Raised when kubectl command fails."""
    
    def __init__(self, message: str, returncode: int, stderr: str):
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr


class KubectlTimeoutError(KubectlError):
    """Raised when kubectl command times out."""
    pass


@dataclass
class KubectlResult:
    """Result from kubectl command execution."""
    
    stdout: str
    stderr: str
    returncode: int
    command: List[str]
    duration_seconds: float
    truncated: bool = False
    
    @property
    def success(self) -> bool:
        """Check if command succeeded."""
        return self.returncode == 0
    
    def raise_for_status(self) -> None:
        """Raise exception if command failed."""
        if not self.success:
            raise KubectlError(
                f"kubectl command failed: {' '.join(self.command)}",
                self.returncode,
                self.stderr
            )


class KubectlRunner:
    """Safe kubectl command runner."""

    def __init__(
        self,
        kubeconfig_path: Optional[str] = None,
        context: Optional[str] = None,
    ):
        self.timeout = settings.kubectl_timeout_seconds
        self.max_output_bytes = settings.max_output_bytes
        self.kubeconfig_path = kubeconfig_path or settings.kubeconfig_path_resolved
        self.context = context
        self.audit_enabled = settings.enable_audit_log
        self.audit_log_path = Path(settings.audit_log_path)
    
    def run(
        self,
        args: List[str],
        namespace: Optional[str] = None,
        capture_output: bool = True,
        max_output: Optional[int] = None,
    ) -> KubectlResult:
        """
        Run kubectl command safely.
        
        Args:
            args: Command arguments (e.g., ["get", "pods"])
            namespace: Optional namespace to inject
            capture_output: Whether to capture stdout/stderr
            
        Returns:
            KubectlResult with command output
            
        Raises:
            KubectlError: If command fails
            KubectlTimeoutError: If command times out
        """
        # SAFETY: Validate that command is read-only
        self._validate_read_only_command(args)
        
        # Build command
        cmd = ["kubectl"]

        # Add kubeconfig if configured
        if self.kubeconfig_path:
            cmd.extend(["--kubeconfig", str(self.kubeconfig_path)])

        # Add context if configured (for multi-context kubeconfigs)
        if self.context:
            cmd.extend(["--context", self.context])

        # Add namespace if provided
        if namespace:
            cmd.extend(["--namespace", namespace])
        
        # Add user arguments
        cmd.extend(args)
        
        # Log command for audit
        self._audit_log("EXECUTE", cmd, namespace)
        
        start_time = datetime.now()
        truncated = False
        
        try:
            # Run command with timeout
            # NEVER use shell=True for security
            result = subprocess.run(
                cmd,
                capture_output=capture_output,
                text=True,
                timeout=self.timeout,
                check=False  # We handle errors manually
            )
            
            duration = (datetime.now() - start_time).total_seconds()
            
            # Truncate output if too large
            stdout = result.stdout
            stderr = result.stderr
            limit = max_output if max_output is not None else self.max_output_bytes

            if len(stdout) > limit:
                stdout = stdout[:limit] + "\n[... output truncated ...]"
                truncated = True
            
            if len(stderr) > self.max_output_bytes:
                stderr = stderr[:self.max_output_bytes] + "\n[... output truncated ...]"
                truncated = True
            
            kubectl_result = KubectlResult(
                stdout=stdout,
                stderr=stderr,
                returncode=result.returncode,
                command=cmd,
                duration_seconds=duration,
                truncated=truncated
            )
            
            # Audit log result
            status = "SUCCESS" if kubectl_result.success else "FAILED"
            self._audit_log(status, cmd, namespace, duration)
            
            return kubectl_result
            
        except subprocess.TimeoutExpired as e:
            duration = (datetime.now() - start_time).total_seconds()
            self._audit_log("TIMEOUT", cmd, namespace, duration)
            
            raise KubectlTimeoutError(
                f"kubectl command timed out after {self.timeout}s: {' '.join(cmd)}",
                -1,
                f"Command exceeded timeout of {self.timeout} seconds"
            )
        
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            self._audit_log("ERROR", cmd, namespace, duration, str(e))
            raise
    
    def _validate_read_only_command(self, args: List[str]) -> None:
        """
        Validate that kubectl command is read-only.
        
        Raises:
            ValueError: If command contains write operations
        """
        if not args:
            return
        
        # List of forbidden write operations
        WRITE_OPERATIONS = {
            "create", "apply", "patch", "delete", "edit", "replace",
            "scale", "autoscale", "set", "label", "annotate",
            "expose", "run", "exec", "attach", "port-forward", "proxy",
            "cp", "drain", "cordon", "uncordon", "taint", "top"
        }
        
        # SPECIAL CASE: "rollout" is forbidden EXCEPT "rollout status" which is read-only
        ALLOWED_ROLLOUT_SUBCOMMANDS = {"status", "history"}
        
        command = args[0].lower() if args else ""
        
        # Check for rollout command
        if command == "rollout":
            if len(args) < 2 or args[1].lower() not in ALLOWED_ROLLOUT_SUBCOMMANDS:
                raise ValueError(
                    f"Forbidden kubectl rollout operation. "
                    f"Only 'rollout status' and 'rollout history' are allowed (read-only)."
                )
        elif command in WRITE_OPERATIONS:
            raise ValueError(
                f"Forbidden kubectl operation: '{command}'. "
                f"Only read-only operations are allowed (get, describe, logs, etc.)"
            )
        
        # Additional safety: check for dangerous flags
        DANGEROUS_FLAGS = {"--all-namespaces", "--all", "-A"}
        for arg in args:
            if arg in DANGEROUS_FLAGS:
                logger.warning(f"Potentially dangerous flag detected: {arg}")
                # Allow but log for audit purposes
    
    def run_json(
        self,
        args: List[str],
        namespace: Optional[str] = None
    ) -> dict:
        """
        Run kubectl command and parse JSON output.

        Uses a 10 MB output cap so that JSON is never truncated mid-stream
        (which would make it unparseable).  Individual callers are responsible
        for limiting the number of items they return to the user.

        Args:
            args: Command arguments
            namespace: Optional namespace

        Returns:
            Parsed JSON as dict

        Raises:
            KubectlError: If command fails or output is not valid JSON
        """
        # Ensure JSON output format
        if "-o" not in args and "--output" not in args:
            args = args + ["-o", "json"]

        # Use a 10 MB hard cap — large enough for any realistic kubectl response
        # while still protecting against pathological outputs.
        JSON_MAX_BYTES = 10 * 1024 * 1024  # 10 MB

        result = self.run(args, namespace=namespace, max_output=JSON_MAX_BYTES)
        result.raise_for_status()
        
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as e:
            raise KubectlError(
                f"Failed to parse kubectl JSON output: {e}",
                result.returncode,
                result.stderr
            )
    
    def _audit_log(
        self,
        status: str,
        command: List[str],
        namespace: Optional[str],
        duration: Optional[float] = None,
        error: Optional[str] = None
    ) -> None:
        """Write audit log entry."""
        if not self.audit_enabled:
            return
        
        try:
            timestamp = datetime.now().isoformat()
            cmd_str = " ".join(command)
            
            log_entry = f"{timestamp} | {status} | ns={namespace or 'N/A'} | "
            if duration is not None:
                log_entry += f"duration={duration:.2f}s | "
            log_entry += f"cmd={cmd_str}"
            
            if error:
                log_entry += f" | error={error}"
            
            # Ensure log directory exists
            self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Append to audit log
            with open(self.audit_log_path, "a") as f:
                f.write(log_entry + "\n")
                
        except Exception as e:
            logger.warning(f"Failed to write audit log: {e}")


# Global runner instance (used when no SSH session is active)
kubectl = KubectlRunner()

# ── Per-request runner context ────────────────────────────────────────────────
# Stores an override runner for the current asyncio Task / thread.
# When the ContextVar is empty (default), get_runner() returns the global
# local kubectl instance.  chat.py sets this to an SSHKubectlRunner for
# requests that arrive with SSH credentials.
runner_ctx: contextvars.ContextVar = contextvars.ContextVar(
    "kubectl_runner", default=None
)


def get_runner():
    """Return the active runner for this request context.

    Falls back to the global local KubectlRunner when no SSH runner has
    been set for the current asyncio task / thread.
    """
    return runner_ctx.get() or kubectl


def set_runner(runner) -> contextvars.Token:
    """Override the runner for the current request context.

    Returns a Token that must be passed to runner_ctx.reset() in a
    finally block to restore the previous value when the request ends.

    Example:
        token = set_runner(ssh_runner)
        try:
            ...
        finally:
            runner_ctx.reset(token)
    """
    return runner_ctx.set(runner)
