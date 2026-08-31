"""Graph health scoring for the Spec Master Knowledge Graph.

Combines structural validation (validation.py) with temporal staleness
(drift.py's detect_temporal_drift) into a single 0-100 score and letter
grade, so an agent (or a human) can get a one-line answer to "is the
project graph still trustworthy" instead of reading a raw issue list.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .model import Graph

from .validation import validate_graph
from .drift import detect_temporal_drift
from .events import append_event, STALE_NODE_DETECTED

# Deduction weights, out of 100. Tuned so a handful of low-confidence edges
# doesn't tank the score, but broken links and unknown types (real
# correctness problems, not just staleness) do.
_ISSUE_WEIGHTS = {
    "broken_wikilinks": 8,
    "unknown_entity_types": 6,
    "unknown_relation_types": 6,
    "invalid_provenance": 6,
    "duplicate_aliases": 3,
    "orphan_nodes": 1,
    "low_confidence_edges": 1,
    "nodes_without_evidence": 2,
}
_STALE_NODE_WEIGHT = 2
_MAX_STALE_DEDUCTION = 20


def _grade(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def compute_health(graph: "Graph", max_age_days: int = 30) -> dict:
    """Compute a structured health report with a 0-100 score and grade."""
    validation = validate_graph(graph)
    temporal_drift = detect_temporal_drift(graph, max_age_days=max_age_days)

    deductions: dict[str, int] = {}
    score = 100
    for key, weight in _ISSUE_WEIGHTS.items():
        count = len(validation.get(key, []))
        if count:
            deduction = min(count * weight, 25)
            deductions[key] = deduction
            score -= deduction

    stale_count = len(temporal_drift["stale_nodes"])
    if stale_count:
        stale_deduction = min(stale_count * _STALE_NODE_WEIGHT, _MAX_STALE_DEDUCTION)
        deductions["stale_nodes"] = stale_deduction
        score -= stale_deduction

    score = max(0, min(100, score))

    return {
        "score": score,
        "grade": _grade(score),
        "total_nodes": len(graph.nodes),
        "total_edges": len(graph.edges),
        "validation": validation,
        "temporal_drift": temporal_drift,
        "deductions": deductions,
    }


def record_stale_nodes(graph: "Graph", events_path: str, max_age_days: int = 30) -> list[str]:
    """Emit a STALE_NODE_DETECTED event per newly-stale node, return the ids."""
    temporal_drift = detect_temporal_drift(graph, max_age_days=max_age_days)
    for node_id in temporal_drift["stale_nodes"]:
        append_event(events_path, STALE_NODE_DETECTED, {"node_id": node_id,
                                                          "max_age_days": max_age_days})
    return temporal_drift["stale_nodes"]


def render_health_report(report: dict) -> str:
    """Render a compute_health() report as Markdown."""
    lines = [
        "# Graph Health Report",
        "",
        f"**Score:** {report['score']}/100 (grade {report['grade']})",
        f"**Nodes:** {report['total_nodes']}  **Edges:** {report['total_edges']}",
        "",
    ]

    validation = report["validation"]
    validation_heading = "clean" if validation["valid"] else f"{validation['total_issues']} issue(s)"
    lines.append(f"## Validation — {validation_heading}")
    lines.append("")
    if validation["valid"]:
        lines.append("No structural issues found.")
    else:
        for key, deduction in report["deductions"].items():
            if key == "stale_nodes":
                continue
            count = len(validation.get(key, []))
            if count:
                lines.append(f"- {key.replace('_', ' ')}: {count} (-{deduction})")
    lines.append("")

    drift = report["temporal_drift"]
    lines.append(f"## Temporal freshness (max age: {drift['max_age_days']} days)")
    lines.append("")
    if drift["stale_nodes"]:
        lines.append(f"- {len(drift['stale_nodes'])} node(s) not re-verified recently: "
                      f"{', '.join(drift['stale_nodes'])}")
    else:
        lines.append("- No stale nodes.")
    if drift["unverified_nodes"]:
        lines.append(f"- {len(drift['unverified_nodes'])} node(s) have never been verified.")
    lines.append("")

    return "\n".join(lines)
