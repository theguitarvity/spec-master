"""Deterministic graph validation for the Spec Master Knowledge Graph.

No LLM calls. All checks are pure Python, testable without external services.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .model import Graph

from .ontology import validate_entity_type, validate_relation_type, validate_provenance
from .provenance import CONFIDENCE_HYPOTHESIS_MIN


def validate_graph(graph: "Graph", confidence_threshold: float = CONFIDENCE_HYPOTHESIS_MIN
                   ) -> dict:
    """Run all graph validations and return a structured report."""
    results = {
        "orphan_nodes": find_orphan_nodes(graph),
        "stale_nodes": find_stale_nodes(graph),
        "broken_wikilinks": find_broken_links(graph),
        "duplicate_aliases": find_duplicate_aliases(graph),
        "unknown_entity_types": find_unknown_entity_types(graph),
        "unknown_relation_types": find_unknown_relation_types(graph),
        "invalid_provenance": find_invalid_provenance(graph),
        "low_confidence_edges": find_low_confidence_edges(graph, confidence_threshold),
        "nodes_without_evidence": find_nodes_without_evidence(graph),
    }
    results["total_issues"] = sum(
        len(v) for v in results.values() if isinstance(v, list)
    )
    results["valid"] = results["total_issues"] == 0
    return results


def find_orphan_nodes(graph: "Graph") -> list[str]:
    """Nodes with no edges (neither source nor target)."""
    connected = set()
    for edge in graph.edges:
        connected.add(edge.source)
        connected.add(edge.target)
    return [nid for nid in graph.nodes if nid not in connected]


def find_stale_nodes(graph: "Graph") -> list[str]:
    return [nid for nid, n in graph.nodes.items() if n.status == "stale"]


def find_broken_links(graph: "Graph") -> list[dict]:
    """Edges whose source or target node IDs don't exist in the graph."""
    broken = []
    for edge in graph.edges:
        missing = []
        if edge.source not in graph.nodes:
            missing.append(edge.source)
        if edge.target not in graph.nodes:
            missing.append(edge.target)
        if missing:
            broken.append({"edge": edge.to_dict(), "missing_ids": missing})
    return broken


def find_duplicate_aliases(graph: "Graph") -> list[dict]:
    """Aliases that appear in more than one node."""
    alias_to_nodes: dict[str, list[str]] = {}
    for node_id, node in graph.nodes.items():
        for alias in [node.name] + node.aliases:
            alias_lower = alias.lower().strip()
            alias_to_nodes.setdefault(alias_lower, []).append(node_id)
    return [
        {"alias": alias, "nodes": nodes}
        for alias, nodes in alias_to_nodes.items()
        if len(nodes) > 1
    ]


def find_unknown_entity_types(graph: "Graph") -> list[dict]:
    return [
        {"node_id": nid, "type": n.type}
        for nid, n in graph.nodes.items()
        if not validate_entity_type(n.type)
    ]


def find_unknown_relation_types(graph: "Graph") -> list[dict]:
    return [
        {"edge": f"{e.source}->{e.target}", "relation": e.relation}
        for e in graph.edges
        if not validate_relation_type(e.relation)
    ]


def find_invalid_provenance(graph: "Graph") -> list[dict]:
    issues = []
    for nid, node in graph.nodes.items():
        if not validate_provenance(node.source):
            issues.append({"node_id": nid, "provenance": node.source})
    for edge in graph.edges:
        if not validate_provenance(edge.provenance):
            issues.append({
                "edge": f"{edge.source}->{edge.target}",
                "provenance": edge.provenance,
            })
    return issues


def find_low_confidence_edges(graph: "Graph",
                               threshold: float = CONFIDENCE_HYPOTHESIS_MIN
                               ) -> list[dict]:
    return [
        {"edge": f"{e.source}->{e.target}", "confidence": e.confidence,
         "relation": e.relation}
        for e in graph.edges
        if e.confidence < threshold and e.status == "active"
    ]


def find_nodes_without_evidence(graph: "Graph") -> list[str]:
    """Nodes that are INFERRED or GENERATED but have no evidence."""
    from .provenance import INFERRED, GENERATED
    return [
        nid for nid, n in graph.nodes.items()
        if n.source in (INFERRED, GENERATED)
        and not n.raw_frontmatter.get("evidence")
    ]
