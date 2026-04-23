"""LLM orchestration for K8s/Ansible error analysis and runbook generation.

Prompt construction and JSON parsing live here; the actual call to a specific
model lives in `services/llm/`. Swap providers by changing `LLM_PROVIDER` —
no code changes needed.
"""

import json
import logging
from typing import Optional

from config.settings import get_settings
from services.llm import LLMProvider, get_provider
from services.llm.base import LLMProviderError

logger = logging.getLogger(__name__)
settings = get_settings()

SYSTEM_PROMPT = """You are a senior Site Reliability Engineer and Kubernetes/Ansible expert.

You help developers diagnose and fix issues in:
- Kubernetes clusters (pods, deployments, services, ingress, RBAC, storage, networking)
- Ansible automation (playbooks, roles, inventory, Helm chart deployments)

When analyzing errors, respond ONLY with valid JSON in this exact format:
{
    "root_cause": "One sentence explanation of why this is failing",
    "solution": "Clear explanation of how to fix it",
    "steps": ["Step 1: ...", "Step 2: ...", "Step 3: ..."],
    "commands": [
        {"cmd": "kubectl get pods -n <namespace>", "description": "What this does"}
    ],
    "prevention": "How to prevent this in the future",
    "severity": "critical|high|medium|low",
    "confidence": 0.95,
    "category": "pod_crashloop",
    "corrected_snippet": "...",
    "corrected_file": "..."
}

Rules:
- All kubectl/ansible/helm commands must be copy-paste ready
- Replace actual secrets/passwords with <REDACTED> in commands
- Flag destructive operations with a WARNING prefix
- Confidence = your certainty this diagnosis is correct (0.0-1.0)
- Severity = impact on cluster health

corrected_snippet and corrected_file rules:
- If the user's input contains file content (YAML, JSON, Python, shell script, Ansible playbook,
  Helm values, Kubernetes manifests, or any config file) alongside the error, you MUST include:
    * "corrected_snippet": the specific fixed lines with 3-5 lines of surrounding context.
      Use the EXACT same indentation and format as the original file.
      Do NOT add any explanation text inside the snippet — only the corrected code.
    * "corrected_file": the COMPLETE corrected file content as it should be saved.
      Include every line from the original, with only the necessary fixes applied.
      Do NOT truncate or omit any sections. Do NOT add markdown fences or explanation.
- If no file content was provided in the input, omit both fields (or set them to null)."""


class LLMService:
    def __init__(self, provider: Optional[LLMProvider] = None):
        self._provider = provider or get_provider()

    @property
    def provider(self) -> LLMProvider:
        return self._provider

    def analyze(self, error_text: str, context: dict, similar: list[dict] = None) -> dict:
        """Analyze an error and return structured diagnosis with fix commands."""
        if not self._provider.enabled:
            return self._no_llm_response(context)

        similar_block = ""
        if similar:
            parts = [f"- {s['error_text'][:120]} → {s['solution_text'][:200]}" for s in similar[:3]]
            similar_block = "\nSimilar resolved issues:\n" + "\n".join(parts)

        prompt = f"""Analyze this Kubernetes/Ansible error:

Tool: {context.get('tool', 'kubernetes')}
Category detected: {context.get('category', 'unknown')}
{f"Pod: {context['pod']}" if 'pod' in context else ''}
{f"Namespace: {context['namespace']}" if 'namespace' in context else ''}
{f"Deployment: {context['deployment']}" if 'deployment' in context else ''}
{f"Node: {context['node']}" if 'node' in context else ''}
{f"Ansible task: {context['task']}" if 'task' in context else ''}
{f"Ansible host: {context['host']}" if 'host' in context else ''}
{similar_block}

Error:
```
{error_text[:6000]}
```

Respond ONLY with valid JSON."""

        try:
            text = self._provider.generate(prompt, system=SYSTEM_PROMPT, temperature=0.2)
            return self._parse(text)
        except LLMProviderError as e:
            logger.error(f"{self._provider.name} error: {e}")
            return self._no_llm_response(context)

    def analyze_live_investigation(self, pod_name: str, namespace: str,
                                   investigation_data: dict) -> dict:
        """Analyze live kubectl investigation data and provide AI diagnosis."""
        if not self._provider.enabled:
            return {"ai_analysis": None, "ai_enabled": False,
                    "message": self._not_configured_message()}

        mode = investigation_data.get("classification", {}).get("mode", "unknown")
        describe_raw = investigation_data.get("describe", {}).get("raw_output", "")[:3000]
        logs = ""
        if "logs_current" in investigation_data:
            logs = investigation_data["logs_current"].get("logs", "")[:2000]
        if "logs_previous" in investigation_data and not logs:
            logs = investigation_data["logs_previous"].get("logs", "")[:2000]
        events = investigation_data.get("events", {}).get("events", [])
        events_text = "\n".join([
            f"[{e.get('type','')}] {e.get('reason','')} - {e.get('message','')}"
            for e in events[:20]
        ])

        prompt = f"""You are investigating a Kubernetes pod failure. Here is the live cluster data:

Pod: {pod_name}
Namespace: {namespace}
Failure mode detected: {mode}

--- kubectl describe pod (truncated) ---
{describe_raw}

--- Pod logs (truncated) ---
{logs if logs else "No logs available"}

--- Recent events ---
{events_text if events_text else "No events"}

Based on this LIVE cluster data, provide:
1. Root cause diagnosis
2. Step-by-step fix commands (use actual pod name and namespace)
3. Prevention recommendations

Respond ONLY with valid JSON matching this schema:
{{
    "root_cause": "...",
    "solution": "...",
    "steps": ["..."],
    "commands": [{{"cmd": "...", "description": "..."}}],
    "prevention": "...",
    "severity": "critical|high|medium|low",
    "confidence": 0.9,
    "category": "..."
}}"""

        try:
            text = self._provider.generate(prompt, system=SYSTEM_PROMPT, temperature=0.2)
            parsed = self._parse(text)
            return {"ai_analysis": parsed, "ai_enabled": True}
        except LLMProviderError as e:
            logger.error(f"{self._provider.name} live analysis error: {e}")
            return {"ai_analysis": None, "ai_enabled": True,
                    "error": f"AI analysis failed: {e}"}

    def summarize_cluster_issues(self, issues: list[dict]) -> str:
        """Summarize multiple cluster issues into an executive report."""
        if not self._provider.enabled:
            return self._not_configured_message()

        prompt = f"""Summarize these Kubernetes/Ansible issues for a DevOps report:

{json.dumps(issues, indent=2)}

Provide:
1. Executive summary (2-3 sentences)
2. Critical issues requiring immediate attention
3. Recurring patterns you notice
4. Top 3 recommended actions

Keep it concise and actionable."""

        try:
            return self._provider.generate(prompt, temperature=0.3)
        except LLMProviderError as e:
            logger.error(f"{self._provider.name} summarize error: {e}")
            return f"Summary generation failed: {e}"

    def generate_runbook(self, error_category: str, examples: list[str]) -> str:
        """Generate a markdown runbook for a recurring error category."""
        if not self._provider.enabled:
            return self._not_configured_message()

        prompt = f"""Generate a runbook for handling '{error_category}' errors in Kubernetes/Ansible.

Example occurrences:
{chr(10).join(f'- {e[:200]}' for e in examples[:5])}

Format the runbook as:
## Overview
## Symptoms
## Diagnosis Steps (with kubectl/ansible commands)
## Fix Procedures
## Prevention
## Escalation Path"""

        try:
            return self._provider.generate(prompt, temperature=0.2)
        except LLMProviderError as e:
            return f"Runbook generation failed: {e}"

    
    def analyze_workload_investigation(self, workload_name: str, namespace: str,
                                       investigation_data: dict) -> dict:
        """Analyze workload (Deployment/StatefulSet) investigation data and provide AI diagnosis."""
        if not self._provider.enabled:
            return {"ai_analysis": None, "ai_enabled": False,
                    "message": self._not_configured_message()}

        workload_type = investigation_data.get("workload_type", "workload")
        describe_raw = investigation_data.get("describe", "")[:3000]
        
        pods = investigation_data.get("pods", [])
        pods_text = "\n".join([
            f"- {p.get('metadata', {}).get('name', 'unknown')}: {p.get('status', {}).get('phase', 'unknown')}"
            for p in pods[:20]
        ])

        events = investigation_data.get("events", {}).get("items", [])
        events_text = "\n".join([
            f"[{e.get('type','')}] {e.get('reason','')} - {e.get('message','')}"
            for e in events[:20]
        ])

        prompt = f"""You are investigating a Kubernetes {workload_type} failure. Here is the LIVE cluster data:

Workload: {workload_name}
Namespace: {namespace}
Type: {workload_type}

--- kubectl get {workload_type} -o json (truncated) ---
{describe_raw}

--- Associated Pods (up to 20) ---
{pods_text if pods_text else "No pods found matching selector"}

--- Recent Events for {workload_type} ---
{events_text if events_text else "No events"}

Based on this LIVE cluster data, provide:
1. Root cause diagnosis (why are the pods failing, or why is it not scaling/rolling out?)
2. Step-by-step fix commands
3. Prevention recommendations

Respond ONLY with valid JSON matching this schema:
{{
    "root_cause": "...",
    "solution": "...",
    "steps": ["..."],
    "commands": [{{"cmd": "...", "description": "..."}}],
    "prevention": "...",
    "severity": "critical|high|medium|low",
    "confidence": 0.9,
    "category": "..."
}}"""

        try:
            text = self._provider.generate(prompt, system=SYSTEM_PROMPT, temperature=0.2)
            parsed = self._parse(text)
            return {"ai_analysis": parsed, "ai_enabled": True}
        except LLMProviderError as e:
            logger.error(f"{self._provider.name} workload analysis error: {e}")
            return {"ai_analysis": None, "ai_enabled": True,
                    "error": f"AI analysis failed: {e}"}

    def analyze_namespace_health(self, namespace: str, resources: dict, events_data: dict) -> dict:
        """Analyze a holistic namespace overview and provide an AI health report."""
        if not self._provider.enabled:
            return {"ai_analysis": None, "ai_enabled": False,
                    "message": self._not_configured_message()}

        # Summarize resources
        summary = []
        for kind, items in resources.items():
            if kind == "success": continue
            count = len(items) if isinstance(items, list) else 0
            if count > 0:
                summary.append(f"- {count} {kind}")
        resources_text = "\n".join(summary)

        # Summarize events
        events = events_data.get("events", [])
        events_text = "\n".join([
            f"[{e.get('type','')}] {e.get('involvedObject', {}).get('kind','')} {e.get('involvedObject', {}).get('name','')}: {e.get('reason','')} - {e.get('message','')}"
            for e in events[:30]
        ])

        prompt = f"""You are performing a holistic health check on a Kubernetes namespace.

Namespace: {namespace}

--- Resource Summary ---
{resources_text if resources_text else "No resources found"}

--- Recent Warning Events (up to 30) ---
{events_text if events_text else "No warning events"}

Analyze the namespace health. Correlate any warning events to identify systemic, cascading, or configuration failures across the namespace.
If there are no warnings, the health is likely good, but still summarize the state.

Respond ONLY with valid JSON matching this schema:
{{
    "root_cause": "A summary of the systemic health or main issues",
    "solution": "Actionable advice for fixing the identified issues",
    "steps": ["..."],
    "commands": [{{"cmd": "...", "description": "..."}}],
    "prevention": "...",
    "severity": "critical|high|medium|low",
    "confidence": 0.9,
    "category": "..."
}}"""

        try:
            text = self._provider.generate(prompt, system=SYSTEM_PROMPT, temperature=0.2)
            parsed = self._parse(text)
            return {"ai_analysis": parsed, "ai_enabled": True}
        except LLMProviderError as e:
            logger.error(f"{self._provider.name} namespace health analysis error: {e}")
            return {"ai_analysis": None, "ai_enabled": True,
                    "error": f"AI analysis failed: {e}"}

    def _parse(self, text: str) -> dict:
        cleaned = (text or "").strip()
        if "```" in cleaned:
            for part in cleaned.split("```"):
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                if part.startswith("{"):
                    cleaned = part
                    break
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return {
                "root_cause": "Could not parse LLM response",
                "solution": text,
                "steps": [],
                "commands": [],
                "prevention": "",
                "severity": "unknown",
                "confidence": 0.3,
                "category": "unknown",
            }

    def _not_configured_message(self) -> str:
        if self._provider.name == "ollama":
            return (
                "Ollama is not reachable. Set OLLAMA_BASE_URL + OLLAMA_MODEL "
                "and ensure the Ollama server is running."
            )
        return "LLM not configured. Add GEMINI_API_KEY to .env (or set LLM_PROVIDER=ollama)."

    def _no_llm_response(self, context: dict) -> dict:
        return {
            "root_cause": f"LLM not configured. Error category: {context.get('category', 'unknown')}",
            "solution": self._not_configured_message(),
            "steps": [
                "1. Copy .env.example to .env",
                "2. Set LLM_PROVIDER=gemini (default) or LLM_PROVIDER=ollama",
                "3. For Gemini: add GEMINI_API_KEY. For Ollama: ensure the server is running.",
                "4. Restart the MCP server",
            ],
            "commands": [],
            "prevention": "",
            "severity": "unknown",
            "confidence": 0.0,
            "category": context.get("category", "unknown"),
        }


llm_service = LLMService()
