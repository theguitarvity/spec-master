"""Requirement traceability matrix rendering (CLAUDE.md section 35).

Rows live in state["traceability"] (a plain list of dicts) so the agent can
append to them during specify/plan/tasks/implement; rendering itself is a
pure, deterministic function -> testable without an LLM.

Graph-integrated traceability (additive): rows_from_graph()/sync_from_graph()
derive rows directly from Requirement nodes and their SATISFIES/TESTED_BY/
IMPLEMENTS edges in the project knowledge graph, so the matrix can be kept
in sync with the graph instead of relying only on manual add_row() calls.
These are purely additive — add_row()/render() and their existing behavior
are unchanged.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

sys.path.insert(0, str(Path(__file__).resolve().parent))

if TYPE_CHECKING:
    from graph.model import Graph

_COLUMNS = ["requirement", "source", "feature", "spec", "plan", "task", "test", "status"]
_HEADERS = ["Requirement", "Source", "Feature", "Spec", "Plan", "Task", "Test", "Status"]


def add_row(state: dict, row: dict) -> dict:
    state.setdefault("traceability", [])
    normalized = {col: row.get(col, "") for col in _COLUMNS}
    state["traceability"].append(normalized)
    return normalized


def render(state: dict) -> str:
    rows = state.get("traceability", [])
    lines = [
        "# Requirement Traceability",
        "",
        "| " + " | ".join(_HEADERS) + " |",
        "|" + "|".join(["---"] * len(_HEADERS)) + "|",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(col, "")) for col in _COLUMNS) + " |")
    if not rows:
        lines.append("| _no requirements traced yet_ | | | | | | | |")
    lines.append("")
    return "\n".join(lines)


def row_from_requirement_node(graph: "Graph", requirement_id: str) -> dict:
    """Build one traceability row for a Requirement node from its graph edges.

    feature: the other end of a SATISFIES/BELONGS_TO edge to a Feature node.
    task:    the other end of an incoming IMPLEMENTS edge from a Task node.
    test:    the other end of a TESTED_BY edge to a Test node.
    spec/plan have no dedicated graph entity type (they're Spec Kit
    artifacts, not graph nodes) and are left blank — a caller with that
    context can still fill them in via add_row().
    """
    node = graph.get_node(requirement_id)
    if node is None:
        return {}

    def _linked_names(relations, direction, wanted_type):
        names = []
        for edge in graph.neighbors(requirement_id, relations=relations, direction=direction):
            other_id = edge.target if edge.source == requirement_id else edge.source
            other = graph.get_node(other_id)
            if other and other.type == wanted_type:
                names.append(other.name)
        return names

    features = _linked_names(["SATISFIES", "BELONGS_TO"], "both", "Feature")
    tasks = _linked_names(["IMPLEMENTS"], "in", "Task")
    tests = _linked_names(["TESTED_BY"], "out", "Test")

    return {
        "requirement": node.name,
        "source": node.source,
        "feature": ", ".join(sorted(set(features))),
        "spec": "",
        "plan": "",
        "task": ", ".join(sorted(set(tasks))),
        "test": ", ".join(sorted(set(tests))),
        "status": "traced" if tests else "untraced",
    }


def rows_from_graph(graph: "Graph") -> list[dict]:
    """One traceability row per Requirement node currently in the graph."""
    requirement_ids = sorted(nid for nid, n in graph.nodes.items() if n.type == "Requirement")
    rows = [row_from_requirement_node(graph, nid) for nid in requirement_ids]
    return [r for r in rows if r]


def sync_from_graph(state: dict, graph: "Graph") -> list[dict]:
    """Add graph-derived rows for any requirement not already tracked by name.

    Idempotent and additive: existing rows (manually added or from a
    previous sync) are never modified or duplicated — this only fills in
    requirements the graph knows about that the matrix doesn't yet have.
    """
    state.setdefault("traceability", [])
    existing_requirements = {row.get("requirement") for row in state["traceability"]}

    added = []
    for row in rows_from_graph(graph):
        if row["requirement"] not in existing_requirements:
            state["traceability"].append(row)
            existing_requirements.add(row["requirement"])
            added.append(row)
    return added
