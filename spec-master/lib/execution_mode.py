"""Execution mode parsing and native -> guarded auto-migration policy
(docs/spec-master/guarded-mode-spec.md §2, §9).

Pure stdlib, no clock/subprocess access inside this module: callers pass
`timestamp` explicitly so this stays a deterministic, easily-tested
function library (mirrors how `state.py`/`fingerprint.py` are written).
"""
from __future__ import annotations

MODES = ("native", "guarded", "auto")

# Any single occurrence triggers migration immediately (auto -> guarded).
CRITICAL_EVENTS = frozenset((
    "early_implementation",
    "out_of_project_write",
    "simulated_tool_call",
    "false_phase_completion",
    "rejected_transition_skip",
    "skill_reentry",
))

# Two of these, accumulated across the whole workflow (not reset per
# phase — Clarified 2026-08-17 in spec.md), trigger the same migration.
RECOVERABLE_EVENTS = frozenset((
    "wrong_path",
    "placeholder_not_removed",
    "artifact_wrong_location",
    "recoverable_tool_error",
))

# Only critical on the second *consecutive* occurrence (guarded-mode-spec.md §9:
# "dois timeouts ou duas respostas consecutivas sem progresso").
CONSECUTIVE_EVENTS = frozenset(("timeout", "no_progress"))

RECOVERABLE_EVENT_THRESHOLD = 2


class ExecutionModeError(Exception):
    pass


def parse_mode(value: str | None) -> str:
    """Validate a --mode value. None/omitted resolves to "auto" (GM-002)."""
    if value is None:
        return "auto"
    if value not in MODES:
        raise ExecutionModeError(
            f"unknown execution mode: {value!r} (expected one of {MODES})"
        )
    return value


def init_execution(state: dict, requested_mode: str, integration: str, model: str) -> dict:
    parse_mode(requested_mode)  # raises on an invalid value
    active_mode = "guarded" if requested_mode == "guarded" else "native"
    state["execution"] = {
        "requested_mode": requested_mode,
        "active_mode": active_mode,
        "integration": integration,
        "model": model,
        "recoverable_event_count": 0,
        "mode_transitions": [],
        "last_consecutive_event": None,
    }
    return state["execution"]


def record_event(state: dict, event_type: str, timestamp: str) -> bool:
    """Record one classified event; return True if it should trigger migration.

    Does not itself mutate active_mode/mode_transitions — call
    `maybe_migrate` with the same event_type to actually apply the
    migration once this returns True.
    """
    execution = state["execution"]
    if execution["active_mode"] != "native":
        # Already guarded (or never went through native) — nothing to migrate.
        return False

    if event_type in CRITICAL_EVENTS:
        return True

    if event_type in CONSECUTIVE_EVENTS:
        triggers = execution.get("last_consecutive_event") in CONSECUTIVE_EVENTS
        execution["last_consecutive_event"] = event_type
        return triggers

    if event_type in RECOVERABLE_EVENTS:
        execution["recoverable_event_count"] += 1
        return execution["recoverable_event_count"] >= RECOVERABLE_EVENT_THRESHOLD

    return False


def maybe_migrate(state: dict, event_type: str, timestamp: str, reason: str | None = None) -> bool:
    """Record `event_type` and migrate native -> guarded if it warrants it.

    Returns True iff a migration happened. Never migrates guarded -> native,
    and never migrates when requested_mode == "native" was never in "auto".
    """
    execution = state["execution"]
    should_migrate = record_event(state, event_type, timestamp)
    if not should_migrate:
        return False

    execution["active_mode"] = "guarded"
    execution["mode_transitions"].append({
        "from": "native",
        "to": "guarded",
        "reason": reason or event_type,
        "timestamp": timestamp,
    })
    return True
