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

Per-feature store (roadmap item 14): once `state["traceability_store"]` is
set (by migrate_from_state), rows live in
`<state dir>/traceability/features/<feature-id>.json` — one small file per
feature instead of an ever-growing inline array in state.json.
`reports/traceability.md` is only ever a render of those files, never a
source of truth. Legacy inline rows are still read, so a state that was
never migrated keeps working unchanged.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

sys.path.insert(0, str(Path(__file__).resolve().parent))

if TYPE_CHECKING:
    from graph.model import Graph

_COLUMNS = ["requirement", "source", "feature", "spec", "plan", "task", "test", "status", "issue"]
_HEADERS = ["Requirement", "Source", "Feature", "Spec", "Plan", "Task", "Test", "Status", "Issue"]

STORE_VERSION = 1
UNASSIGNED_FEATURE = "_unassigned"
_UNSAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")


def _normalize(row: dict) -> dict:
    return {col: row.get(col, "") for col in _COLUMNS}


def add_row(state: dict, row: dict) -> dict:
    state.setdefault("traceability", [])
    normalized = _normalize(row)
    state["traceability"].append(normalized)
    return normalized


def render_rows(rows: list[dict], title: str = "Requirement Traceability") -> str:
    lines = [
        f"# {title}",
        "",
        "| " + " | ".join(_HEADERS) + " |",
        "|" + "|".join(["---"] * len(_HEADERS)) + "|",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(col, "")) for col in _COLUMNS) + " |")
    if not rows:
        lines.append("| _no requirements traced yet_ | " + " | ".join([""] * (len(_HEADERS) - 1)) + " |")
    lines.append("")
    return "\n".join(lines)


def render(state: dict) -> str:
    return render_rows(state.get("traceability", []))


# --- per-feature store (item 14) -------------------------------------------

def store_dir(state_path: str) -> Path:
    return Path(state_path).resolve().parent / "traceability" / "features"


def _feature_filename(feature_id: str) -> str:
    safe = _UNSAFE_FILENAME.sub("-", feature_id or "").strip("-.")
    return f"{safe or UNASSIGNED_FEATURE}.json"


def feature_file(state_path: str, feature_id: str) -> Path:
    return store_dir(state_path) / _feature_filename(feature_id)


def _row_key(row: dict) -> tuple:
    return tuple(str(row.get(col, "")) for col in _COLUMNS)


def _read_feature_file(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = data.get("rows", []) if isinstance(data, dict) else []
    return [r for r in rows if isinstance(r, dict)]


def _write_feature_file(path: Path, feature_id: str, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": STORE_VERSION, "feature": feature_id, "rows": rows}
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def uses_store(state: dict) -> bool:
    return bool(state.get("traceability_store"))


def add_feature_row(state_path: str, row: dict) -> dict:
    """Append one row to its feature's file (deduplicated, atomic write)."""
    normalized = _normalize(row)
    feature_id = normalized["feature"] or UNASSIGNED_FEATURE
    path = feature_file(state_path, feature_id)
    rows = _read_feature_file(path)
    if _row_key(normalized) not in {_row_key(r) for r in rows}:
        rows.append(normalized)
        _write_feature_file(path, feature_id, rows)
    return normalized


def load_store_rows(state_path: str, feature: str | None = None) -> list[dict]:
    directory = store_dir(state_path)
    if feature is not None:
        return _read_feature_file(feature_file(state_path, feature))
    if not directory.is_dir():
        return []
    rows: list[dict] = []
    for path in sorted(directory.glob("*.json")):
        rows.extend(_read_feature_file(path))
    return rows


def load_rows(state: dict, state_path: str, feature: str | None = None) -> list[dict]:
    """Legacy inline rows + per-feature store rows, deduplicated, in order."""
    inline = [r for r in state.get("traceability", []) if feature is None or r.get("feature") == feature]
    merged: list[dict] = []
    seen: set[tuple] = set()
    for row in inline + load_store_rows(state_path, feature):
        key = _row_key(row)
        if key not in seen:
            seen.add(key)
            merged.append(row)
    return merged


def record(state: dict, state_path: str, row: dict) -> dict:
    """Write a row wherever this state keeps traceability (store or inline)."""
    if uses_store(state):
        return add_feature_row(state_path, row)
    return add_row(state, row)


def migrate_from_state(state: dict, state_path: str) -> dict:
    """Move inline rows into per-feature files. Idempotent.

    Returns a summary; the caller persists `state` (inline array removed,
    `traceability_store` set) only after the files are on disk.
    """
    inline = state.get("traceability", [])
    per_feature: dict[str, int] = {}
    for row in inline:
        before = len(load_store_rows(state_path, row.get("feature") or UNASSIGNED_FEATURE))
        add_feature_row(state_path, row)
        after = len(load_store_rows(state_path, row.get("feature") or UNASSIGNED_FEATURE))
        feature_id = row.get("feature") or UNASSIGNED_FEATURE
        per_feature[feature_id] = per_feature.get(feature_id, 0) + (after - before)
    state["traceability"] = []
    state["traceability_store"] = {
        "version": STORE_VERSION,
        "path": os.path.relpath(store_dir(state_path), Path(state_path).resolve().parent),
    }
    return {
        "migrated_rows": sum(per_feature.values()),
        "inline_rows_seen": len(inline),
        "features": per_feature,
        "store": str(store_dir(state_path)),
    }


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


def sync_from_graph(state: dict, graph: "Graph", state_path: str | None = None) -> list[dict]:
    """Add graph-derived rows for any requirement not already tracked by name.

    Idempotent and additive: existing rows (manually added or from a
    previous sync) are never modified or duplicated — this only fills in
    requirements the graph knows about that the matrix doesn't yet have.
    With `state_path` on a migrated state, rows go to the per-feature store.
    """
    state.setdefault("traceability", [])
    use_store = state_path is not None and uses_store(state)
    existing_rows = load_rows(state, state_path) if use_store else state["traceability"]
    existing_requirements = {row.get("requirement") for row in existing_rows}

    added = []
    for row in rows_from_graph(graph):
        if row["requirement"] not in existing_requirements:
            if use_store:
                add_feature_row(state_path, row)
            else:
                state["traceability"].append(row)
            existing_requirements.add(row["requirement"])
            added.append(row)
    return added
