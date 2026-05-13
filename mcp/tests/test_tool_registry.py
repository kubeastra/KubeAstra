"""Baseline tests for the unified tool registry (Phase 1 + Phase 2).

These tests validate that the registry contains the expected tools,
aliases resolve correctly, surface filtering works, and the dispatch
function handles edge cases. They serve as a regression safety net
for all subsequent migration phases.
"""

import pytest
import sys
import os

# Ensure mcp/ is on the path (mirrors what ui/backend/main.py does)
MCP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if MCP_DIR not in sys.path:
    sys.path.insert(0, MCP_DIR)

from tool_registry import (
    TOOLS,
    ToolDef,
    DispatchContext,
    resolve_tool,
    tools_for_surface,
    build_react_tool_descriptions,
)


# ── Phase 1: Baseline snapshots ─────────────────────────────────────────────

# Expected tool names in the registry (34 total: 33 original MCP + get_nodes)
EXPECTED_REGISTRY_TOOLS = sorted([
    # Investigation
    "investigate_pod", "investigate_workload", "analyze_namespace",
    # Discovery
    "find_workload", "get_namespaces", "get_nodes", "list_namespace_resources",
    # Pod
    "get_pods", "get_pod_logs", "describe_pod",
    # Cluster state
    "get_events", "get_deployment", "get_service", "get_endpoints",
    "get_rollout_status", "list_services", "get_resource_graph",
    "list_kubeconfig_contexts", "switch_kubeconfig_context",
    "get_current_context", "k8sgpt_analyze",
    # Kubeconfig management
    "add_kubeconfig_context",
    # Deployment repo
    "search_deployment_repo", "get_deployment_repo_file", "list_deployment_repo_path",
    # Write operations
    "exec_pod_command", "delete_pod", "rollout_restart",
    "scale_deployment", "apply_patch",
    # AI analysis
    "analyze_error", "get_fix_commands", "list_error_categories",
    "cluster_report", "error_summary", "generate_runbook",
])

# Aliases that must resolve to canonical names
EXPECTED_ALIASES = {
    "list_contexts": "list_kubeconfig_contexts",
    "switch_context": "switch_kubeconfig_context",
}

# Expected MCP surface tools (36 tools: all registry tools are on MCP)
EXPECTED_MCP_TOOL_COUNT = 36

# Expected chat/react surface tools (subset — excludes MCP-only tools)
EXPECTED_CHAT_TOOLS = sorted([
    "investigate_pod", "investigate_workload", "analyze_namespace",
    "find_workload", "get_namespaces", "get_nodes", "list_namespace_resources",
    "get_pods", "get_pod_logs",
    "get_events", "get_deployment", "get_service", "get_endpoints",
    "get_rollout_status", "list_services", "get_resource_graph",
    "list_kubeconfig_contexts", "switch_kubeconfig_context",
    "analyze_error", "get_fix_commands",
    "cluster_report", "error_summary", "generate_runbook",
])


# ── Tests ────────────────────────────────────────────────────────────────────

class TestRegistryContents:
    """Validate the registry contains exactly the expected tools."""

    def test_all_expected_tools_present(self):
        actual = sorted(TOOLS.keys())
        assert actual == EXPECTED_REGISTRY_TOOLS

    def test_total_tool_count(self):
        assert len(TOOLS) == 36

    def test_every_tool_has_required_fields(self):
        for name, tool in TOOLS.items():
            assert tool.name == name, f"Tool key '{name}' != tool.name '{tool.name}'"
            assert tool.handler is not None, f"Tool '{name}' missing handler"
            assert tool.schema is not None, f"Tool '{name}' missing schema"
            assert tool.description, f"Tool '{name}' has empty description"
            assert tool.category, f"Tool '{name}' has empty category"
            assert tool.surfaces, f"Tool '{name}' has no surfaces"

    def test_write_ops_require_confirm(self):
        for tool in TOOLS.values():
            if tool.write_op:
                assert tool.requires_confirm, (
                    f"Write op '{tool.name}' must set requires_confirm=True"
                )


class TestAliases:
    """Validate alias resolution."""

    def test_known_aliases_resolve(self):
        for alias, canonical in EXPECTED_ALIASES.items():
            tool = resolve_tool(alias)
            assert tool is not None, f"Alias '{alias}' did not resolve"
            assert tool.name == canonical, (
                f"Alias '{alias}' resolved to '{tool.name}', expected '{canonical}'"
            )

    def test_canonical_names_resolve(self):
        for name in EXPECTED_REGISTRY_TOOLS:
            assert resolve_tool(name) is not None, f"Tool '{name}' not found"

    def test_unknown_tool_returns_none(self):
        assert resolve_tool("nonexistent_tool") is None


class TestSurfaceFiltering:
    """Validate tools_for_surface returns the right subsets."""

    def test_mcp_surface_count(self):
        mcp_tools = tools_for_surface("mcp")
        assert len(mcp_tools) == EXPECTED_MCP_TOOL_COUNT

    def test_chat_surface_tools(self):
        chat_tools = sorted(t.name for t in tools_for_surface("chat"))
        assert chat_tools == EXPECTED_CHAT_TOOLS

    def test_react_surface_matches_chat(self):
        # chat and react surfaces should expose the same tools
        chat_names = {t.name for t in tools_for_surface("chat")}
        react_names = {t.name for t in tools_for_surface("react")}
        assert chat_names == react_names

    def test_mcp_only_tools_not_in_chat(self):
        mcp_only = {
            "describe_pod", "get_current_context", "k8sgpt_analyze",
            "add_kubeconfig_context",
            "search_deployment_repo", "get_deployment_repo_file",
            "list_deployment_repo_path",
            "exec_pod_command", "delete_pod", "rollout_restart",
            "scale_deployment", "apply_patch",
            "list_error_categories",
        }
        chat_names = {t.name for t in tools_for_surface("chat")}
        for tool_name in mcp_only:
            assert tool_name not in chat_names, (
                f"MCP-only tool '{tool_name}' should not be in chat surface"
            )


class TestCategories:
    """Validate tool categorization."""

    def test_all_categories_are_known(self):
        known = {"investigation", "discovery", "pod", "cluster", "ai", "write", "repo"}
        for tool in TOOLS.values():
            assert tool.category in known, (
                f"Tool '{tool.name}' has unknown category '{tool.category}'"
            )

    def test_write_ops_are_write_category(self):
        write_tools = [t for t in TOOLS.values() if t.write_op]
        for t in write_tools:
            assert t.category == "write", (
                f"Write tool '{t.name}' has category '{t.category}', expected 'write'"
            )

    def test_ai_tools_return_json_strings(self):
        ai_tools = [t for t in TOOLS.values() if t.category == "ai"]
        for t in ai_tools:
            assert t.returns_json_string, (
                f"AI tool '{t.name}' should have returns_json_string=True"
            )


class TestReactDescriptions:
    """Validate generated ReAct tool descriptions."""

    def test_descriptions_not_empty(self):
        desc = build_react_tool_descriptions()
        assert len(desc) > 200, "Generated descriptions too short"

    def test_descriptions_include_key_tools(self):
        desc = build_react_tool_descriptions()
        key_tools = [
            "investigate_pod", "get_pods", "get_events",
            "find_workload", "analyze_namespace",
        ]
        for tool_name in key_tools:
            assert tool_name in desc or any(
                alias in desc
                for t in TOOLS.values() if t.name == tool_name
                for alias in t.aliases
            ), f"Tool '{tool_name}' missing from generated descriptions"

    def test_aliases_used_in_descriptions(self):
        desc = build_react_tool_descriptions()
        # Aliases like list_contexts should appear instead of list_kubeconfig_contexts
        assert "list_contexts" in desc
        assert "switch_context" in desc

    def test_write_ops_excluded_from_react(self):
        desc = build_react_tool_descriptions()
        write_ops = ["delete_pod", "rollout_restart", "scale_deployment",
                      "apply_patch", "exec_pod_command"]
        for w in write_ops:
            assert w not in desc, (
                f"Write op '{w}' should not appear in ReAct descriptions"
            )


class TestDriftFixes:
    """Validate the specific drift fixes from the proposal."""

    def test_get_nodes_in_all_surfaces(self):
        tool = resolve_tool("get_nodes")
        assert tool is not None
        assert "mcp" in tool.surfaces
        assert "chat" in tool.surfaces
        assert "react" in tool.surfaces

    def test_get_pods_schema_has_status_filter(self):
        tool = resolve_tool("get_pods")
        assert tool is not None
        schema = tool.schema
        fields = schema.model_fields
        assert "status_filter" in fields, "GetPodsInput should have status_filter"

    def test_context_aliases_resolve(self):
        assert resolve_tool("list_contexts").name == "list_kubeconfig_contexts"
        assert resolve_tool("switch_context").name == "switch_kubeconfig_context"
