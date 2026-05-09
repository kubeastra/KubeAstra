"""ReAct (Reasoning + Acting) orchestrator for multi-step investigations.

Replaces the single-shot route → dispatch → synthesize pipeline with an
iterative loop where the LLM decides which tools to call, observes the
results, and continues until it has enough information to answer.

Usage:
    from react import react_loop
    result = react_loop(question, history, llm_provider, dispatch_fn)
"""

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

MAX_ITERATIONS = 6           # Enough for discover + investigate + answer
MAX_WALL_CLOCK_SECS = 90     # Hard cap on total loop time (LLM + tool calls)
MAX_OBSERVATION_CHARS = 3000  # Truncate tool output to keep context window sane
MAX_CONTEXT_CHARS = 12000    # Total budget for accumulated observations

# ── Data structures ──────────────────────────────────────────────────────────

@dataclass
class ReActStep:
    """One iteration of the ReAct loop."""
    iteration: int
    thought: str
    action: str                    # tool name or "answer"
    action_params: dict = field(default_factory=dict)
    observation: str = ""          # tool result (truncated)
    duration_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)


@dataclass
class ReActResult:
    """Final output from the ReAct loop."""
    answer: str                    # The LLM's final synthesized answer
    tool_used: str                 # Last tool that was decisive (for compat)
    result: Optional[dict] = None  # Last tool's raw result (for frontend)
    steps: list[ReActStep] = field(default_factory=list)
    total_iterations: int = 0
    total_duration_ms: float = 0.0
    suggested_actions: list = field(default_factory=list)
    error: Optional[str] = None


# ── Tool descriptions for the ReAct system prompt ────────────────────────────

TOOL_DESCRIPTIONS = """Available tools (call exactly one per step):

INVESTIGATION TOOLS (start here for debugging questions):
- investigate_pod(namespace?, pod_name, use_ai=true) — Deep investigation of a specific pod: collects status, describe, logs, events, and AI analysis. Best first tool for "why is X crashing?"
- investigate_workload(namespace, workload_name, workload_type="deployment", use_ai=true) — Investigate a deployment/statefulset/daemonset: replica status, pod health, rollout history, events, AI analysis
- analyze_namespace(namespace) — Holistic health check of an entire namespace: all pods, events, services, issues

DISCOVERY TOOLS (use when you need to find things):
- find_workload(name) — Search for a pod/deployment/service across ALL namespaces by name. Use when namespace is unknown.
- get_namespaces() — List all namespaces in the cluster
- get_nodes() — List all nodes and their status
- list_namespace_resources(namespace) — List all resources (pods, services, deployments, etc.) in a namespace

POD TOOLS:
- get_pods(namespace, status_filter?) — List pods in a namespace. Use namespace="*" for all namespaces. Optional status_filter: "CrashLoopBackOff", "Error", "Pending", etc.
- get_pod_logs(namespace?, pod_name, previous=false, tail=200) — Get logs from a specific pod. Set previous=true for crashed container logs.

CLUSTER STATE TOOLS:
- get_events(namespace, field_selector?) — Get events in a namespace. Use namespace="*" for all. Use field_selector="type=Warning" for warnings only.
- get_deployment(namespace, deployment_name) — Get details of a specific deployment
- get_service(namespace?, service_name) — Get details of a specific service
- get_endpoints(namespace, service_name) — Check endpoints for a service
- get_rollout_status(namespace, deployment_name) — Check if a deployment rollout is progressing
- list_services(namespace) — List all services in a namespace
- get_resource_graph(namespace) — Get the Ingress→Service→Deployment→Pod topology graph
- list_contexts() — List available kubeconfig contexts/clusters
- switch_context(context_name) — Switch to a different cluster context

AI ANALYSIS TOOLS (use after gathering data, or for specific requests):
- analyze_error(error_text) — AI diagnosis of a pasted error message
- get_fix_commands(error_text) — Get specific kubectl fix commands for an error
- generate_runbook(error_text) — Generate a step-by-step runbook (only when user explicitly asks for a runbook)
- cluster_report(events_text) — Generate a cluster health report from events data
- error_summary(errors) — Summarize multiple errors"""


# ── ReAct system prompt ──────────────────────────────────────────────────────

REACT_SYSTEM = """You are Kubeastra, an expert Kubernetes troubleshooting agent. You investigate cluster issues step by step using the tools available to you.

## How you work

You follow a Thought → Action → Observation loop:
1. **Think** about what information you need next
2. **Act** by calling a tool to gather that information
3. **Observe** the result and decide if you need more information

When you have enough information to fully answer the user's question, respond with the "answer" action.

## Response format

You MUST respond with valid JSON in exactly one of these two formats:

### To call a tool:
{
  "thought": "I need to check the pod status to understand why it's crashing",
  "action": "investigate_pod",
  "params": {"pod_name": "my-app", "use_ai": true}
}

### To give a final answer:
{
  "thought": "I now have enough information to explain the root cause",
  "action": "answer",
  "answer": "Your detailed answer here using **markdown** formatting. Be specific with pod names, error messages, and suggested fixes."
}

## Rules

1. **Answer as soon as you can.** For listing questions ("what pods?", "list services"), one tool call is enough — call the tool, then answer immediately with what you got. Do NOT investigate individual pods unless the user explicitly asks to debug or troubleshoot.
2. **Be efficient** — use the most specific tool first. For "why is X crashing?", start with investigate_pod, not get_pods.
3. **Don't repeat tools** with the same parameters — you already have that data.
4. **Cross-reference only when troubleshooting** — if the user asks why something is broken, check dependencies. If they just asked for a listing, answer with the listing.
5. **Namespace discovery** — if you don't know the namespace, use find_workload first. If the user specifies a namespace, use it directly — do NOT search all namespaces.
6. **Keep answers concise** — summarize findings in 2-5 sentences. Use a short table or bullet list for pod/resource lists. Don't list every detail.
7. **Use markdown** in your final answer: **bold** for emphasis, `code` for resource names, bullet points for lists.
8. **Max {max_iterations} tool calls** — if you're running out, give the best answer you can with what you have.

{tool_descriptions}"""


# ── Core loop ────────────────────────────────────────────────────────────────

def react_loop(
    question: str,
    history: list,
    provider,
    dispatch_fn: Callable[[str, dict], dict],
    max_iterations: int = MAX_ITERATIONS,
) -> ReActResult:
    """Run the ReAct loop: think → act → observe → repeat until answered.

    Args:
        question: The user's question
        history: Recent chat history (list of ChatMessage-like objects)
        provider: An LLMProvider instance (Gemini, Ollama, etc.)
        dispatch_fn: Function that takes (tool, params) and returns a dict
        max_iterations: Safety cap on tool calls

    Returns:
        ReActResult with the final answer and full step trace
    """
    loop_start = time.perf_counter()
    steps: list[ReActStep] = []
    observations: list[str] = []  # Accumulated context for the LLM
    last_tool = "none"
    last_result = None

    system = (
        REACT_SYSTEM
        .replace("{max_iterations}", str(max_iterations))
        .replace("{tool_descriptions}", TOOL_DESCRIPTIONS)
    )

    # Build initial context from chat history
    history_context = ""
    if history:
        recent = history[-4:]
        history_context = "\n".join(
            f"{getattr(m, 'role', 'user')}: {getattr(m, 'content', str(m))[:200]}"
            for m in recent
        )
        history_context = f"\nRecent conversation:\n{history_context}\n"

    for iteration in range(1, max_iterations + 1):
        # Wall-clock timeout — don't let the loop run forever
        elapsed = time.perf_counter() - loop_start
        if elapsed > MAX_WALL_CLOCK_SECS:
            logger.warning("react_wall_clock_timeout elapsed=%.1fs", elapsed)
            return ReActResult(
                answer=_emergency_answer(steps, question),
                tool_used=last_tool,
                result=last_result,
                steps=steps,
                total_iterations=iteration - 1,
                total_duration_ms=elapsed * 1000,
                error=f"Investigation timed out after {int(elapsed)}s",
            )

        # Build the prompt with accumulated observations
        prompt = _build_prompt(question, history_context, observations, iteration, max_iterations)

        # Ask the LLM what to do next
        step_start = time.perf_counter()
        # Scale max_tokens: tool-call steps need ~200 tokens, but the final
        # answer step needs room for a detailed markdown response.
        step_budget = 2500 if iteration >= 2 else 800
        try:
            raw = provider.generate(prompt, system=system, temperature=0.1, max_tokens=step_budget)
        except Exception as e:
            logger.warning(f"ReAct LLM call failed at iteration {iteration}: {e}")
            return ReActResult(
                answer=_emergency_answer(steps, question),
                tool_used=last_tool,
                result=last_result,
                steps=steps,
                total_iterations=iteration,
                total_duration_ms=(time.perf_counter() - loop_start) * 1000,
                error=f"LLM error at step {iteration}: {e}",
            )

        # Parse the LLM's response
        parsed = _parse_react_response(raw)
        if parsed is None:
            logger.warning(f"ReAct: unparseable response at iteration {iteration}: {raw[:200]}")
            # Try one more time with a nudge
            if iteration < max_iterations:
                observations.append(
                    f"[System: Your last response was not valid JSON. "
                    f"Respond with ONLY a JSON object with 'thought', 'action', and 'params' or 'answer'.]"
                )
                continue
            else:
                return ReActResult(
                    answer=_emergency_answer(steps, question),
                    tool_used=last_tool,
                    result=last_result,
                    steps=steps,
                    total_iterations=iteration,
                    total_duration_ms=(time.perf_counter() - loop_start) * 1000,
                    error="Failed to parse LLM response",
                )

        thought = parsed.get("thought", "")
        action = parsed.get("action", "")
        params = parsed.get("params", {})

        # ── Final answer ─────────────────────────────────────────────────
        if action == "answer":
            answer_text = parsed.get("answer", "")
            step = ReActStep(
                iteration=iteration,
                thought=thought,
                action="answer",
                duration_ms=(time.perf_counter() - step_start) * 1000,
            )
            steps.append(step)

            logger.info(
                "react_complete iterations=%d tools_called=%d",
                iteration,
                len([s for s in steps if s.action != "answer"]),
            )

            return ReActResult(
                answer=answer_text,
                tool_used=last_tool,
                result=last_result,
                steps=steps,
                total_iterations=iteration,
                total_duration_ms=(time.perf_counter() - loop_start) * 1000,
                suggested_actions=_extract_actions_from_steps(steps, last_result),
            )

        # ── Tool call ────────────────────────────────────────────────────
        logger.info(
            "react_step iteration=%d action=%s params=%s",
            iteration, action, json.dumps(params)[:100],
        )

        tool_start = time.perf_counter()
        try:
            result = dispatch_fn(action, params)
            last_tool = action
            last_result = result
        except Exception as e:
            result = {"error": str(e)}
            logger.warning(f"ReAct tool dispatch failed: {action} → {e}")

        tool_ms = (time.perf_counter() - tool_start) * 1000

        # Truncate observation to keep context manageable
        obs_text = _truncate_observation(result, action)

        step = ReActStep(
            iteration=iteration,
            thought=thought,
            action=action,
            action_params=params,
            observation=obs_text,
            duration_ms=(time.perf_counter() - step_start) * 1000,
        )
        steps.append(step)

        # Add to observations for next iteration
        observations.append(
            f"Step {iteration} — Tool: {action}({json.dumps(params)})\n"
            f"Result:\n{obs_text}"
        )

        # Trim accumulated observations if they're getting too long
        _trim_observations(observations)

    # Exhausted iterations — synthesize best-effort answer
    logger.warning("react_max_iterations_reached iterations=%d", max_iterations)
    return ReActResult(
        answer=_emergency_answer(steps, question),
        tool_used=last_tool,
        result=last_result,
        steps=steps,
        total_iterations=max_iterations,
        total_duration_ms=(time.perf_counter() - loop_start) * 1000,
        error="Reached maximum investigation steps",
    )


# ── Prompt construction ──────────────────────────────────────────────────────

def _build_prompt(
    question: str,
    history_context: str,
    observations: list[str],
    iteration: int,
    max_iterations: int,
) -> str:
    """Build the prompt for the current ReAct iteration."""
    parts = []

    if history_context:
        parts.append(history_context)

    parts.append(f"User question: {question}")

    if observations:
        parts.append("\n--- Investigation so far ---")
        for obs in observations:
            parts.append(obs)
        parts.append("--- End of investigation so far ---\n")

        remaining = max_iterations - iteration
        if remaining <= 2:
            parts.append(
                f"[IMPORTANT: You have {remaining + 1} steps remaining. "
                f"Give your final answer NOW with what you have.]"
            )
        elif len(observations) >= 2:
            parts.append(
                "[You have already gathered data. If you can answer the question, "
                "do so now. Only call another tool if essential information is missing.]"
            )

    parts.append(
        f"Step {iteration}/{max_iterations}: What should you do next? "
        f"Respond with a JSON object."
    )

    return "\n\n".join(parts)


# ── Response parsing ─────────────────────────────────────────────────────────

def _parse_react_response(raw: str) -> Optional[dict]:
    """Parse the LLM's JSON response, handling markdown code fences and truncation.

    The LLM sometimes returns truncated JSON (max_tokens hit mid-response).
    This parser tries progressively harder strategies to recover useful output:
    1. Direct JSON parse
    2. Extract JSON from surrounding text / code fences
    3. Salvage truncated "answer" responses by closing the string + object
    """
    if not raw:
        return None

    text = raw.strip()

    # Strip markdown code fences
    if "```" in text:
        for part in text.split("```"):
            part = part.strip().lstrip("json").strip()
            if part.startswith("{"):
                text = part
                break

    # Try direct JSON parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to extract JSON object from surrounding text
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    # ── Salvage truncated / malformed responses ───────────────────────────

    # If the LLM dropped the opening {"thought": " prefix, prepend it and retry.
    # Pattern: text starts with the thought content directly, e.g.:
    #   I now have enough info",\n  "action": "answer", ...
    if start == -1 and '"action"' in text:
        repaired = '{"thought": "' + text
        end2 = repaired.rfind("}")
        if end2 > 0:
            try:
                return json.loads(repaired[:end2 + 1])
            except json.JSONDecodeError:
                pass

    # Work with the fragment from the first { (if any)
    fragment = text[start:] if start != -1 else text

    # Strategy: if it looks like an answer action, extract what we can
    answer_match = re.search(
        r'"action"\s*:\s*"answer".*?"answer"\s*:\s*"',
        fragment, re.DOTALL,
    )
    if answer_match:
        # Everything after the opening quote of "answer": " is the text
        answer_start = answer_match.end()
        # The answer text may be truncated — take what we have
        answer_body = fragment[answer_start:]
        # Strip trailing incomplete escape sequences or quotes
        answer_body = answer_body.rstrip("\\")
        if answer_body.endswith('"'):
            answer_body = answer_body[:-1]
        # Remove trailing } and whitespace
        answer_body = re.sub(r'"\s*\}\s*$', '', answer_body)
        # Unescape JSON string escapes
        try:
            answer_text = json.loads(f'"{answer_body}"')
        except json.JSONDecodeError:
            # Fallback: use raw text, replacing common escapes
            answer_text = answer_body.replace('\\"', '"').replace("\\n", "\n")

        # Also try to extract the thought
        thought_match = re.search(r'"thought"\s*:\s*"([^"]*)"', fragment)
        thought = thought_match.group(1) if thought_match else ""

        if answer_text.strip():
            return {
                "thought": thought,
                "action": "answer",
                "answer": answer_text.strip(),
            }

    # Strategy: if it looks like a tool call, try to extract action + params
    action_match = re.search(r'"action"\s*:\s*"([^"]+)"', fragment)
    params_match = re.search(r'"params"\s*:\s*\{([^}]*)\}', fragment)
    thought_match = re.search(r'"thought"\s*:\s*"([^"]*)"', fragment)
    if action_match and action_match.group(1) != "answer":
        action = action_match.group(1)
        thought = thought_match.group(1) if thought_match else ""
        params = {}
        if params_match:
            try:
                params = json.loads("{" + params_match.group(1) + "}")
            except json.JSONDecodeError:
                pass
        return {"thought": thought, "action": action, "params": params}

    return None


# ── Observation formatting ───────────────────────────────────────────────────

def _truncate_observation(result: dict, tool: str) -> str:
    """Convert a tool result dict to a string, truncated for context window."""
    if not isinstance(result, dict):
        return str(result)[:MAX_OBSERVATION_CHARS]

    # For investigation tools, extract the most useful parts
    if tool in ("investigate_pod", "investigate_workload", "analyze_namespace"):
        focused = {}
        for key in ("pod_name", "namespace", "classification", "steps_run",
                     "workload_name", "workload_type", "summary", "issues",
                     "pod_count", "health_summary", "error"):
            if key in result:
                focused[key] = result[key]
        # Include AI analysis if present
        ai = result.get("ai", {})
        if isinstance(ai, dict) and ai.get("ai_analysis"):
            focused["ai_analysis"] = ai["ai_analysis"]
        text = json.dumps(focused, default=str)
    elif tool == "get_pods":
        # Include health summary and full pod list so the LLM can answer listing questions
        focused = {
            "namespace": result.get("namespace"),
            "pod_count": result.get("pod_count"),
            "health_summary": result.get("health_summary"),
        }
        pods = result.get("pods", [])
        if pods:
            # Include all pod names/statuses (compact), with unhealthy first
            unhealthy = [p for p in pods if p.get("status") not in ("Running", "Succeeded")]
            healthy = [p for p in pods if p.get("status") in ("Running", "Succeeded")]
            ordered = unhealthy + healthy
            # Compact format: just name, status, restarts, age
            focused["pods"] = [
                {k: p.get(k) for k in ("name", "status", "restarts", "age", "ready") if p.get(k) is not None}
                for p in ordered[:30]
            ]
            focused["total_pods"] = len(pods)
        text = json.dumps(focused, default=str)
    else:
        text = json.dumps(result, default=str)

    if len(text) > MAX_OBSERVATION_CHARS:
        text = text[:MAX_OBSERVATION_CHARS] + "...(truncated)"

    return text


def _trim_observations(observations: list[str]) -> None:
    """Trim oldest observations if total size exceeds budget."""
    total = sum(len(o) for o in observations)
    while total > MAX_CONTEXT_CHARS and len(observations) > 1:
        removed = observations.pop(0)
        total -= len(removed)
        # Add a placeholder so the LLM knows steps were trimmed
        if not observations[0].startswith("[Earlier steps"):
            observations.insert(0, "[Earlier investigation steps were trimmed for brevity]")


# ── Emergency fallback ───────────────────────────────────────────────────────

def _emergency_answer(steps: list[ReActStep], question: str) -> str:
    """Build a best-effort answer from accumulated observations when the loop
    fails or exhausts iterations."""
    if not steps:
        return (
            "I wasn't able to complete the investigation. "
            "Please try asking a more specific question, like "
            "\"investigate pod my-app in namespace staging\"."
        )

    # Collect all observations
    findings = []
    for step in steps:
        if step.observation and step.action != "answer":
            findings.append(f"**{step.action}**: {step.observation[:500]}")

    if findings:
        return (
            "I gathered some information but couldn't complete the full investigation. "
            "Here's what I found:\n\n" + "\n\n".join(findings[:5])
        )

    return (
        "The investigation didn't complete successfully. "
        "Try asking about a specific pod or namespace."
    )


# ── Action extraction (for frontend suggested actions) ───────────────────────

def _extract_actions_from_steps(steps: list[ReActStep], last_result: Optional[dict]) -> list:
    """Extract suggested kubectl *fix* commands from tool results.

    Only includes commands that the execute endpoint will actually accept
    (write operations like delete pod, rollout restart, scale, patch, etc.).
    Diagnostic / read-only commands (get, describe, logs) are filtered out —
    the investigation already ran those.
    """
    # Must match the allowlist in chat.py's execute endpoint
    _EXECUTABLE_PREFIXES = (
        "kubectl patch ", "kubectl apply ", "kubectl scale ",
        "kubectl rollout restart ", "kubectl rollout undo ",
        "kubectl delete pod ", "kubectl delete pods ",
        "kubectl set image ", "kubectl set resources ",
        "kubectl label ", "kubectl annotate ",
        "kubectl cordon ", "kubectl uncordon ", "kubectl drain ",
    )

    actions = []
    seen = set()

    def _add_cmd(c: str, desc: str) -> None:
        c = c.strip()
        if not c.startswith("kubectl") or c in seen:
            return
        # Only include commands that the execute endpoint will accept
        if not any(c.startswith(prefix) for prefix in _EXECUTABLE_PREFIXES):
            return
        seen.add(c)
        actions.append({
            "type": "apply",
            "label": desc or c[:60],
            "command": c,
            "confirm": True,
        })

    # Extract from the last tool result
    if isinstance(last_result, dict):
        # From AI analysis
        ai = last_result.get("ai", {})
        if isinstance(ai, dict):
            ai_analysis = ai.get("ai_analysis", {})
            if isinstance(ai_analysis, dict):
                for cmd in ai_analysis.get("commands", []):
                    c = cmd if isinstance(cmd, str) else (cmd.get("command") or cmd.get("cmd") or "")
                    desc = "" if isinstance(cmd, str) else cmd.get("description", "")
                    _add_cmd(c, desc)

        # From fix commands
        for cmd in last_result.get("commands", []):
            c = cmd if isinstance(cmd, str) else (cmd.get("command") or cmd.get("cmd") or "")
            desc = "" if isinstance(cmd, str) else cmd.get("description", "")
            _add_cmd(c, desc)

    return actions[:5]
