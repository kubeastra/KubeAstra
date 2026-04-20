"""
MCP Tool: cluster_report / error_summary
Summarizes multiple errors or events into a structured DevOps report.
"""

import json
from collections import Counter
from services.llm_service import llm_service
from services.error_parser import classify_error


def cluster_report(events_text: str, namespace: str = "all") -> str:
    """
    Analyze kubectl events or multiple error logs and produce a cluster health report.
    Pass the output of: kubectl get events --all-namespaces --sort-by='.lastTimestamp'
    """
    lines = [l.strip() for l in events_text.splitlines() if l.strip()]

    warnings   = [l for l in lines if "Warning" in l]
    normals    = [l for l in lines if "Normal" in l]
    categories = Counter()

    parsed_events = []
    for line in warnings[:50]:
        cat = classify_error(line, "kubernetes")
        categories[cat] += 1
        parsed_events.append({"line": line[:200], "category": cat})

    ai_summary = llm_service.summarize_cluster_issues(parsed_events[:20])

    output = {
        "namespace":      namespace,
        "total_events":   len(lines),
        "warnings":       len(warnings),
        "normal_events":  len(normals),
        "top_categories": categories.most_common(10),
        "ai_summary":     ai_summary,
        "critical_warnings": [e["line"] for e in parsed_events if e["category"] in (
            "pod_crashloop", "pod_oom", "api_server", "node", "pod_evicted"
        )][:10],
    }
    return json.dumps(output, indent=2)


def error_summary(errors: list[str], tool: str = "kubernetes") -> str:
    """
    Summarize a list of error messages (e.g. from a CI/CD pipeline run).
    Pass a list of error strings.
    """
    categories = Counter()
    parsed = []

    for err in errors[:30]:
        cat = classify_error(err, tool)
        categories[cat] += 1
        parsed.append({"error": err[:200], "category": cat})

    ai_summary = llm_service.summarize_cluster_issues(parsed[:15])

    output = {
        "total_errors":   len(errors),
        "tool":           tool,
        "top_categories": categories.most_common(10),
        "ai_summary":     ai_summary,
        "errors_analyzed": parsed[:10],
    }
    return json.dumps(output, indent=2)
