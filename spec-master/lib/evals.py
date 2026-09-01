"""Deterministic harness evals for Spec Master.

These are not LLM quality benchmarks. They are executable harness-contract
checks that verify governance primitives remain wired and truthful.
"""
from __future__ import annotations

from graph.model import Graph, GraphNode, GraphEdge
from graph.validation import validate_graph
from graph.traversal import blast_radius

import context_budget
import feature_model
import tool_policy


def run() -> dict:
    checks = []

    ordered = feature_model.order_features([
        {"id": "foundation", "dependencies": []},
        {"id": "ui", "dependencies": ["foundation"]},
    ])
    checks.append({"name": "feature_dag_order", "passed": ordered == ["foundation", "ui"]})

    policy = tool_policy.preflight(["python3 -m pytest", "rm -rf ."])
    checks.append({"name": "tool_policy_blocks_destructive", "passed": policy["allowed"] is False})

    budget = context_budget.budget_items([
        {"id": "small", "content": "abcd"},
        {"id": "large", "content": "x" * 100},
    ], token_budget=10)
    checks.append({"name": "context_budget_omits_overflow", "passed": budget["selected_ids"] == ["small"]})

    graph = Graph()
    graph.add_node(GraphNode(id="component.api", type="Component", name="API", source="DISCOVERED_FROM_CODEBASE"))
    graph.add_node(GraphNode(id="component.ui", type="Component", name="UI", source="DISCOVERED_FROM_CODEBASE"))
    graph.add_edge(GraphEdge(source="component.ui", relation="DEPENDS_ON", target="component.api", provenance="DISCOVERED_FROM_CODEBASE"))
    validation = validate_graph(graph)
    checks.append({"name": "graph_validation_clean", "passed": validation["valid"] is True})
    checks.append({"name": "blast_radius_detects_dependent", "passed": blast_radius(graph, "component.api") == ["component.ui"]})

    passed = sum(1 for c in checks if c["passed"])
    return {
        "total": len(checks),
        "passed": passed,
        "failed": len(checks) - passed,
        "success": passed == len(checks),
        "checks": checks,
    }
