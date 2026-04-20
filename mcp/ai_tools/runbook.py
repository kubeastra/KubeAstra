"""
MCP Tool: generate_runbook
Generates a markdown runbook for a given error category, ready to paste into Confluence/Notion.
"""

import json
from services.llm_service import llm_service
from services.error_parser import classify_error


def generate_runbook(category: str = None, error_examples: list[str] = None,
                     error_text: str = None, tool: str = "kubernetes") -> str:
    """
    Generate a runbook for a recurring error category.
    - Provide category name directly, OR
    - Provide error_text and it will classify automatically
    - Optionally provide error_examples (list of raw error strings) for more context
    """
    if not category and error_text:
        category = classify_error(error_text, tool)

    if not category:
        return json.dumps({"error": "Provide either 'category' or 'error_text'"})

    examples = error_examples or []
    if error_text and error_text not in examples:
        examples.insert(0, error_text)

    runbook_md = llm_service.generate_runbook(category, examples)

    output = {
        "category": category,
        "tool":     tool,
        "runbook":  runbook_md,
        "format":   "markdown",
        "tip":      "Paste this into Confluence, Notion, or your team wiki.",
    }
    return json.dumps(output, indent=2)
