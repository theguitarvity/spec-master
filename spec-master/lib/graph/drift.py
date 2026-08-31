"""Architecture drift detection for the Spec Master Knowledge Graph.

Two kinds of drift:
  1. Structural drift: the graph now says something different than it used
     to (a previously-recorded, high-provenance edge no longer shows up in
     a fresh discovery pass) — detected by diffing two graph snapshots.
  2. Temporal drift: a node/edge hasn't been re-verified in a long time,
     so its accuracy is increasingly suspect even if nothing has explicitly
     contradicted it yet — detected via temporal.is_stale().

Both are pure, deterministic comparisons — no LLM calls.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .model import Graph

from . import temporal
from .events import append_event, ARCHITECTURE_DRIFT_DETECTED

# Provenance levels solid enough that their disappearance is worth flagging
# as drift rather than noise (an UNRESOLVED or low-confidence guess vanishing
# is expected churn, not drift).
_DRIFT_WORTHY_PROVENANCE = {
    "EXPLICIT", "DISCOVERED_FROM_CODEBASE", "DISCOVERED_FROM_CONFIG",
    "DISCOVERED_FROM_SPEC", "DISCOVERED_FROM_ADR", "DISCOVERED_FROM_TEST",
    "USER_CONFIRMED",
}


def diff_graphs(old_graph: "Graph", new_graph: "Graph") -> dict:
    """Structural diff between two graph snapshots of the same project."""
    old_ids, new_ids = set(old_graph.nodes), set(new_graph.nodes)

    added_nodes = sorted(new_ids - old_ids)
    removed_nodes = sorted(old_ids - new_ids)

    changed_nodes = []
    for nid in sorted(old_ids & new_ids):
        old_node, new_node = old_graph.nodes[nid], new_graph.nodes[nid]
        if old_node.status != new_node.status or old_node.type != new_node.type:
            changed_nodes.append({
                "id": nid,
                "old_status": old_node.status, "new_status": new_node.status,
                "old_type": old_node.type, "new_type": new_node.type,
            })

    def _edge_key(e):
        return (e.source, e.relation, e.target)

    old_edges = {_edge_key(e): e for e in old_graph.edges if e.status == "active"}
    new_edges = {_edge_key(e): e for e in new_graph.edges if e.status == "active"}

    added_edges = sorted(set(new_edges) - set(old_edges))
    removed_edges = sorted(set(old_edges) - set(new_edges))

    return {
        "added_nodes": added_nodes,
        "removed_nodes": removed_nodes,
        "changed_nodes": changed_nodes,
        "added_edges": [{"source": s, "relation": r, "target": t} for s, r, t in added_edges],
        "removed_edges": [{"source": s, "relation": r, "target": t} for s, r, t in removed_edges],
    }


def detect_structural_drift(old_graph: "Graph", new_graph: "Graph",
                             events_path: "str | None" = None) -> dict:
    """Flag structural changes that involve high-provenance (trustworthy)
    knowledge, since those are the ones worth an agent's attention — a
    disappeared EXPLICIT dependency likely means the codebase actually
    changed underneath a stale spec, not just re-scan noise.
    """
    diff = diff_graphs(old_graph, new_graph)

    drifted_removed_edges = [
        e for e in diff["removed_edges"]
        for old_edge in old_graph.edges
        if (old_edge.source, old_edge.relation, old_edge.target) == (e["source"], e["relation"], e["target"])
        and old_edge.provenance in _DRIFT_WORTHY_PROVENANCE
    ]
    drifted_removed_nodes = [
        nid for nid in diff["removed_nodes"]
        if old_graph.nodes[nid].source in _DRIFT_WORTHY_PROVENANCE
    ]

    report = {
        "diff": diff,
        "drifted_removed_edges": drifted_removed_edges,
        "drifted_removed_nodes": drifted_removed_nodes,
        "has_drift": bool(drifted_removed_edges or drifted_removed_nodes),
    }

    if events_path and report["has_drift"]:
        append_event(events_path, ARCHITECTURE_DRIFT_DETECTED, {
            "removed_edge_count": len(drifted_removed_edges),
            "removed_node_count": len(drifted_removed_nodes),
        })

    return report


def detect_temporal_drift(graph: "Graph", max_age_days: int = 30) -> dict:
    """Nodes/edges whose last_verified timestamp is older than max_age_days."""
    stale_nodes = [
        nid for nid, n in graph.nodes.items()
        if n.last_verified and temporal.is_stale(n.last_verified, max_age_days)
    ]
    unverified_nodes = [
        nid for nid, n in graph.nodes.items() if not n.last_verified
    ]
    stale_edges = [
        {"source": e.source, "relation": e.relation, "target": e.target}
        for e in graph.edges
        if e.status == "active" and e.last_verified
        and temporal.is_stale(e.last_verified, max_age_days)
    ]
    return {
        "max_age_days": max_age_days,
        "stale_nodes": sorted(stale_nodes),
        "unverified_nodes": sorted(unverified_nodes),
        "stale_edges": stale_edges,
    }
