"""Human-readable Markdown maps rendered from the Spec Master Knowledge Graph.

Pure, deterministic rendering functions — no LLM calls — in the same spirit
as traceability.py's render(): the graph is the source of truth, these
functions just project it into a form a human (or an agent skimming for
context) can read quickly.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .model import Graph

from .traversal import bfs


def render_system_map(graph: "Graph") -> str:
    """A full-graph map: nodes grouped by type, each with its outgoing edges."""
    lines = ["# System Map", ""]
    if not graph.nodes:
        lines.append("_no nodes in graph_")
        lines.append("")
        return "\n".join(lines)

    by_type: dict[str, list] = {}
    for node in graph.nodes.values():
        by_type.setdefault(node.type, []).append(node)

    for type_ in sorted(by_type):
        lines.append(f"## {type_}")
        lines.append("")
        for node in sorted(by_type[type_], key=lambda n: n.id):
            status_flag = "" if node.status == "active" else f" ({node.status})"
            lines.append(f"- **{node.name}** (`{node.id}`){status_flag}")
            edges = graph.neighbors(node.id, direction="out")
            for edge in sorted(edges, key=lambda e: (e.relation, e.target)):
                lines.append(f"  - {edge.relation} → `{edge.target}`")
        lines.append("")

    return "\n".join(lines)


def render_node_map(graph: "Graph", node_id: str, depth: int = 2) -> str:
    """A focused map of one node and its neighborhood within `depth` hops."""
    node = graph.get_node(node_id)
    if node is None:
        return f"# Node Map: {node_id}\n\n_node not found_\n"

    lines = [f"# Node Map: {node.name}", "", f"`{node.id}` ({node.type}, status: {node.status})", ""]

    reached = bfs(graph, node_id, max_depth=depth, direction="both")
    if not reached:
        lines.append("_no connected nodes within range_")
        lines.append("")
        return "\n".join(lines)

    by_depth: dict[int, list[str]] = {}
    for nid, d in reached.items():
        by_depth.setdefault(d, []).append(nid)

    for d in sorted(by_depth):
        lines.append(f"## {d} hop{'s' if d != 1 else ''} away")
        lines.append("")
        for nid in sorted(by_depth[d]):
            neighbor = graph.get_node(nid)
            if neighbor is None:
                continue
            connecting = [
                e for e in graph.neighbors(nid, direction="both")
                if e.source == node_id or e.target == node_id
            ]
            rel_desc = ", ".join(sorted({e.relation for e in connecting})) or "connected"
            lines.append(f"- **{neighbor.name}** (`{neighbor.id}`) — {rel_desc}")
        lines.append("")

    return "\n".join(lines)


def render_dependency_map(graph: "Graph", relation: str = "DEPENDS_ON") -> str:
    """A simple adjacency list for one relation type (default DEPENDS_ON)."""
    lines = [f"# Dependency Map ({relation})", ""]
    edges = [e for e in graph.edges if e.status == "active" and e.relation == relation]
    if not edges:
        lines.append(f"_no active {relation} edges_")
        lines.append("")
        return "\n".join(lines)

    by_source: dict[str, list[str]] = {}
    for edge in edges:
        by_source.setdefault(edge.source, []).append(edge.target)

    for source_id in sorted(by_source):
        source_node = graph.get_node(source_id)
        label = source_node.name if source_node else source_id
        lines.append(f"- **{label}** (`{source_id}`)")
        for target_id in sorted(by_source[source_id]):
            target_node = graph.get_node(target_id)
            target_label = target_node.name if target_node else target_id
            lines.append(f"  - → {target_label} (`{target_id}`)")
    lines.append("")

    return "\n".join(lines)
