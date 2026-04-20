"""AI Tool: analyze_error
Accepts raw error text, classifies it, searches similar past issues via RAG, and returns an AI solution.
Works with pasted errors from logs, CI/CD pipelines, or any source (no live cluster needed).
"""

import json

from services.error_parser import extract_context
from services.llm_service import llm_service
from services.vector_db import vector_db
from services.embeddings import embeddings


def run(error_text: str, tool: str = "kubernetes", environment: str = "production") -> str:
    context = extract_context(error_text, tool)
    context["environment"] = environment

    query_vector = embeddings.embed(error_text)
    similar = vector_db.search(query_vector, tool=tool, limit=5)

    result = llm_service.analyze(error_text, context, similar)

    output = {
        "category":   result.get("category", context["category"]),
        "severity":   result.get("severity", "unknown"),
        "confidence": result.get("confidence", 0.0),
        "root_cause": result.get("root_cause", ""),
        "solution":   result.get("solution", ""),
        "steps":      result.get("steps", []),
        "commands":   result.get("commands", []),
        "prevention": result.get("prevention", ""),
        "similar_cases": [
            {
                "error":        s["error_text"][:150],
                "solution":     s["solution_text"][:200],
                "similarity":   f"{round(s['similarity'] * 100)}%",
                "success_rate": f"{s['success_rate']}%",
            }
            for s in similar
        ],
        "context": {k: v for k, v in context.items() if k not in ("error_hash",)},
    }

    # Pass through corrected code fields when Gemini provides them
    if result.get("corrected_snippet"):
        output["corrected_snippet"] = result["corrected_snippet"]
    if result.get("corrected_file"):
        output["corrected_file"] = result["corrected_file"]

    return json.dumps(output, indent=2)
