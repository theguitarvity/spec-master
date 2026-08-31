"""Ergonomic query API over the Spec Master Knowledge Graph.

Graph.neighbors() (model.py) already covers direct-edge lookups; this module
adds the filter/search operations agents actually need when asking questions
like "what services exist", "what's tagged payments", or "find anything
matching this text" — without needing to hand-roll a comprehension over
graph.nodes every time.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from .model import Graph, GraphNode, GraphEdge


def find_by_type(graph: "Graph", type_: str) -> list["GraphNode"]:
    return [n for n in graph.nodes.values() if n.type == type_]


def find_by_tag(graph: "Graph", tag: str) -> list["GraphNode"]:
    return [n for n in graph.nodes.values() if tag in n.tags]


def find_by_status(graph: "Graph", status: str) -> list["GraphNode"]:
    return [n for n in graph.nodes.values() if n.status == status]


def find_by_relation(graph: "Graph", relation: str,
                      direction: str = "out") -> list["GraphEdge"]:
    """Active edges of a given relation type, in either or both directions."""
    result = []
    for edge in graph.edges:
        if edge.status != "active" or edge.relation != relation:
            continue
        result.append(edge)
    return result


def find_matching(graph: "Graph",
                   predicate: "Callable[[GraphNode], bool]") -> list["GraphNode"]:
    """General-purpose filter for queries the other helpers don't cover."""
    return [n for n in graph.nodes.values() if predicate(n)]


def search(graph: "Graph", query: str) -> list["GraphNode"]:
    """Simple case-insensitive text search over id, name, tags, and content."""
    q = query.lower().strip()
    if not q:
        return []
    results = []
    for node in graph.nodes.values():
        if (q in node.id.lower() or q in node.name.lower()
                or any(q in t.lower() for t in node.tags)
                or any(q in a.lower() for a in node.aliases)
                or q in node.content.lower()):
            results.append(node)
    return results


def edges_between(graph: "Graph", source_id: str, target_id: str) -> list["GraphEdge"]:
    """All active edges directly connecting two specific nodes, either direction."""
    return [
        e for e in graph.edges
        if e.status == "active"
        and ((e.source == source_id and e.target == target_id)
             or (e.source == target_id and e.target == source_id))
    ]


def nodes_by_confidence(graph: "Graph", min_confidence: float = 0.0,
                         max_confidence: float = 1.0) -> list["GraphNode"]:
    return [
        n for n in graph.nodes.values()
        if min_confidence <= n.confidence <= max_confidence
    ]
