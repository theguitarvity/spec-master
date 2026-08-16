"""Persistent state machine for /spec-master (CLAUDE.md sections 30, 43, 25).

Pure stdlib, no LLM involved. Reads/writes .spec-master/state.json.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

STATE_VERSION = 1

WORKFLOW_STATES = [
    "INITIALIZED",
    "DISCOVERING",
    "CONTEXT_NORMALIZED",
    "WAITING_GIT_STRATEGY",
    "CONSTITUTION_READY",
    "FEATURES_IDENTIFIED",
    "SPECIFYING",
    "CLARIFYING",
    "PLANNING",
    "TASKING",
    "ANALYZING",
    "IMPLEMENTING",
    "VALIDATING",
    "COMPLETED",
]
ALTERNATIVE_STATES = ["BLOCKED", "FAILED", "PAUSED"]
ALL_WORKFLOW_STATES = WORKFLOW_STATES + ALTERNATIVE_STATES

FEATURE_PHASES = [
    "specify",
    "clarify",
    "plan",
    "tasks",
    "analyze",
    "implement",
    "validate",
]
PHASE_STATUSES = ["PENDING", "RUNNING", "PASSED", "FAILED", "BLOCKED", "SKIPPED"]

MAX_ANALYZE_REPAIR_CYCLES = 3


class StateError(Exception):
    pass


class InvalidTransitionError(StateError):
    pass


def _now_phase_status_map() -> dict:
    return {phase: "PENDING" for phase in FEATURE_PHASES}


def default_state(context: str, workflow: str | None = None) -> dict:
    return {
        "version": STATE_VERSION,
        "context": context,
        "workflow": workflow,
        "status": "INITIALIZED",
        "constitution": {"status": "PENDING"},
        "features": [],
        "quality_gates": [],
        "fingerprint": {},
    }


def load(path: str) -> dict:
    if not os.path.exists(path):
        raise StateError(f"state file not found: {path}")
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def save(path: str, state: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, ensure_ascii=False, sort_keys=False)
        fh.write("\n")
    os.replace(tmp, path)


def init(path: str, context: str, workflow: str | None = None) -> dict:
    if os.path.exists(path):
        return load(path)
    state = default_state(context, workflow)
    save(path, state)
    return state


def set_workflow(state: dict, workflow: str) -> dict:
    if workflow not in ("git-flow", "trunk"):
        raise StateError(f"unknown workflow strategy: {workflow}")
    state["workflow"] = workflow
    if state["status"] == "WAITING_GIT_STRATEGY":
        state["status"] = "CONSTITUTION_READY"
    return state


def transition_workflow_status(state: dict, new_status: str) -> dict:
    if new_status not in ALL_WORKFLOW_STATES:
        raise InvalidTransitionError(f"unknown workflow status: {new_status}")
    current = state["status"]
    if new_status in ALTERNATIVE_STATES:
        state["status"] = new_status
        return state
    if current in ALTERNATIVE_STATES:
        # Resuming from BLOCKED/FAILED/PAUSED is always allowed explicitly.
        state["status"] = new_status
        return state
    if current not in WORKFLOW_STATES:
        raise InvalidTransitionError(f"corrupt current status: {current}")
    current_idx = WORKFLOW_STATES.index(current)
    new_idx = WORKFLOW_STATES.index(new_status) if new_status in WORKFLOW_STATES else -1
    if new_idx == -1:
        raise InvalidTransitionError(f"unknown workflow status: {new_status}")
    if new_idx < current_idx:
        raise InvalidTransitionError(
            f"cannot move workflow status backwards: {current} -> {new_status}"
        )
    state["status"] = new_status
    return state


def find_feature(state: dict, feature_id: str) -> dict:
    for feature in state["features"]:
        if feature["id"] == feature_id:
            return feature
    raise StateError(f"unknown feature id: {feature_id}")


def upsert_feature(state: dict, feature: dict) -> dict:
    feature = dict(feature)
    feature.setdefault("status", "PENDING")
    feature.setdefault("analyze_repair_cycles", 0)
    phases = feature.get("phases") or _now_phase_status_map()
    for phase in FEATURE_PHASES:
        phases.setdefault(phase, "PENDING")
    feature["phases"] = phases
    for i, existing in enumerate(state["features"]):
        if existing["id"] == feature["id"]:
            state["features"][i] = feature
            return feature
    state["features"].append(feature)
    return feature


def transition_phase(state: dict, feature_id: str, phase: str, status: str) -> dict:
    if phase not in FEATURE_PHASES:
        raise InvalidTransitionError(f"unknown phase: {phase}")
    if status not in PHASE_STATUSES:
        raise InvalidTransitionError(f"unknown phase status: {status}")
    feature = find_feature(state, feature_id)
    phase_idx = FEATURE_PHASES.index(phase)
    if status in ("RUNNING", "PASSED") and phase_idx > 0:
        prev_phase = FEATURE_PHASES[phase_idx - 1]
        prev_status = feature["phases"].get(prev_phase, "PENDING")
        if prev_status != "PASSED":
            raise InvalidTransitionError(
                f"cannot start/pass '{phase}' before '{prev_phase}' has PASSED "
                f"(currently {prev_status})"
            )
    feature["phases"][phase] = status
    return feature


def analyze_cycle(state: dict, feature_id: str, action: str) -> dict:
    feature = find_feature(state, feature_id)
    count = feature.get("analyze_repair_cycles", 0)
    if action == "check":
        return {
            "feature": feature_id,
            "cycles": count,
            "max": MAX_ANALYZE_REPAIR_CYCLES,
            "exhausted": count >= MAX_ANALYZE_REPAIR_CYCLES,
        }
    if action == "increment":
        if count >= MAX_ANALYZE_REPAIR_CYCLES:
            raise StateError(
                f"feature '{feature_id}' exhausted the {MAX_ANALYZE_REPAIR_CYCLES} "
                "analyze repair cycles; escalate to BLOCKED"
            )
        count += 1
        feature["analyze_repair_cycles"] = count
        return {
            "feature": feature_id,
            "cycles": count,
            "max": MAX_ANALYZE_REPAIR_CYCLES,
            "exhausted": count >= MAX_ANALYZE_REPAIR_CYCLES,
        }
    raise StateError(f"unknown analyze-cycle action: {action}")


def summarize(state: dict) -> dict:
    return {
        "status": state["status"],
        "workflow": state.get("workflow"),
        "features": [
            {
                "id": f["id"],
                "name": f.get("name"),
                "status": f.get("status"),
                "phases": f.get("phases"),
                "analyze_repair_cycles": f.get("analyze_repair_cycles", 0),
            }
            for f in state["features"]
        ],
    }
