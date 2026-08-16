"""Requirement traceability matrix rendering (CLAUDE.md section 35).

Rows live in state["traceability"] (a plain list of dicts) so the agent can
append to them during specify/plan/tasks/implement; rendering itself is a
pure, deterministic function -> testable without an LLM.
"""
from __future__ import annotations

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
