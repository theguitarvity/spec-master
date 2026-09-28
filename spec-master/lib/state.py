"""Persistent state machine for /spec-master.

Pure stdlib, no LLM involved. Reads/writes .spec-master/state.json.

Writes are atomic (a uniquely named temp file in the same directory, then
`os.replace`), and every load -> modify -> save cycle made through
`transaction()` holds an exclusive lock on `<state>.lock`, so concurrent
processes (the CLI, the MCP server, parallel workers) never lose each
other's updates.
"""
from __future__ import annotations

import contextlib
import json
import os
import tempfile
import time

try:  # POSIX
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None
try:  # Windows
    import msvcrt
except ImportError:
    msvcrt = None

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
# Phases the risk-adaptive ceremony (risk_profile.py) may skip for XS/S
# features. A SKIPPED phase satisfies the next phase's prerequisite like PASSED.
SKIPPABLE_PHASES = ("clarify",)
DONE_PHASE_STATUSES = ("PASSED", "SKIPPED")

MAX_ANALYZE_REPAIR_CYCLES = 3

LOCK_TIMEOUT_SECONDS = 30

# Feature fields only the workflow's own tooling may write: phases move through
# `transition_phase` (with evidence at the CLI boundary), risk through
# `risk classify/override`, evidence and attempts through the core itself.
TOOL_OWNED_FEATURE_FIELDS = ("phases", "evidence", "attempts", "analyze_repair_cycles", "risk")


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
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=os.path.basename(path) + ".", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2, ensure_ascii=False, sort_keys=False)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def _try_lock(fd: int) -> bool:
    try:
        if fcntl is not None:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        elif msvcrt is not None:  # pragma: no cover - Windows
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        return True
    except (BlockingIOError, PermissionError):
        return False
    except OSError as exc:  # EAGAIN/EACCES on some platforms mean "held"
        if getattr(exc, "errno", None) in (11, 13, 35):
            return False
        raise


def _unlock(fd: int) -> None:
    with contextlib.suppress(OSError):
        if fcntl is not None:
            fcntl.flock(fd, fcntl.LOCK_UN)
        elif msvcrt is not None:  # pragma: no cover - Windows
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)


@contextlib.contextmanager
def locked(path: str, timeout: float = LOCK_TIMEOUT_SECONDS):
    """Hold an exclusive advisory lock on `<path>.lock` for the block."""
    lock_path = path + ".lock"
    os.makedirs(os.path.dirname(lock_path) or ".", exist_ok=True)
    owner = spec_master_dir(lock_path)
    if owner:
        ensure_gitignore(owner)
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        deadline = time.monotonic() + timeout
        while not _try_lock(fd):
            if time.monotonic() >= deadline:
                raise StateError(f"timed out after {timeout:.0f}s waiting for the state lock {lock_path}")
            time.sleep(0.02)
        try:
            yield
        finally:
            _unlock(fd)
    finally:
        os.close(fd)


SPEC_MASTER_DIR = ".spec-master"
# Per-process files that never belong in the project's history.
GITIGNORE_PATTERNS = ("*.lock", "hooks/decisions.jsonl")


def spec_master_dir(path: str) -> str | None:
    """The nearest `.spec-master` directory containing `path`, if any."""
    directory = os.path.dirname(os.path.abspath(path))
    while True:
        if os.path.basename(directory) == SPEC_MASTER_DIR:
            return directory
        parent = os.path.dirname(directory)
        if parent == directory:
            return None
        directory = parent


def ensure_gitignore(directory: str) -> None:
    """Write `<.spec-master>/.gitignore` for the lock files and the hooks'
    audit log, once: an existing file is never touched."""
    path = os.path.join(directory, ".gitignore")
    if os.path.exists(path):
        return
    try:
        with open(path, "x", encoding="utf-8") as fh:
            fh.write("# Spec Master per-process files\n" + "".join(p + "\n" for p in GITIGNORE_PATTERNS))
    except OSError:
        pass  # another process wrote it first, or the directory is read-only


@contextlib.contextmanager
def transaction(path: str, timeout: float = LOCK_TIMEOUT_SECONDS):
    """Locked load -> modify -> save. The state is saved only when the block
    finishes without an exception; a failure leaves the file untouched."""
    with locked(path, timeout):
        state = load(path)
        yield state
        save(path, state)


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


def upsert_feature_metadata(state: dict, incoming: dict, *, allow_unverified: bool = False) -> tuple[dict, dict]:
    """Agent-facing upsert (`state upsert-feature`): metadata only.

    An existing feature is merged key by key; a new one starts PENDING.
    Upsert used to be a way to promote phases without evidence (Principle
    IV), so it no longer changes the fields the workflow's tooling owns
    (`TOOL_OWNED_FEATURE_FIELDS`) and no longer sets `status: COMPLETED`
    while a phase is still open.

    `allow_unverified` is for importing history that never ran through
    Spec Master: it accepts `phases`, `analyze_repair_cycles` and a
    COMPLETED status, and reports the phases it promoted to PASSED in
    `imported_phases` so the caller records them as unverified evidence.
    `evidence`, `attempts` and `risk` are never accepted here.

    Returns (feature, {"imported_phases": [...], "rejected": [...]}).
    """
    if not isinstance(incoming, dict) or not incoming.get("id"):
        raise StateError("feature JSON must be an object with an `id`")
    feature_id = incoming["id"]
    existing = next((f for f in state["features"] if f["id"] == feature_id), None)
    base = dict(existing) if existing else {
        "id": feature_id, "status": "PENDING", "analyze_repair_cycles": 0, "phases": _now_phase_status_map(),
    }
    current_phases = {phase: (base.get("phases") or {}).get(phase, "PENDING") for phase in FEATURE_PHASES}
    incoming_phases = incoming.get("phases") or {}
    if not isinstance(incoming_phases, dict):
        raise StateError("`phases` must be an object of phase -> status")
    for phase, status in incoming_phases.items():
        if phase not in FEATURE_PHASES:
            raise InvalidTransitionError(f"unknown phase: {phase}")
        if status not in PHASE_STATUSES:
            raise InvalidTransitionError(f"unknown phase status for {phase}: {status}")
    wanted_phases = {phase: incoming_phases.get(phase, current_phases[phase]) for phase in FEATURE_PHASES}

    never = [key for key in ("evidence", "attempts", "risk")
             if key in incoming and incoming[key] != base.get(key)]
    guarded = []
    if wanted_phases != current_phases:
        guarded.append("phases")
    if "analyze_repair_cycles" in incoming and incoming["analyze_repair_cycles"] != base.get("analyze_repair_cycles", 0):
        guarded.append("analyze_repair_cycles")
    phases_after = wanted_phases if allow_unverified else current_phases
    if incoming.get("status") == "COMPLETED" and base.get("status") != "COMPLETED":
        if any(phases_after[phase] not in DONE_PHASE_STATUSES for phase in FEATURE_PHASES):
            guarded.append("status")
    if never or (guarded and not allow_unverified):
        rejected = sorted(set(never + guarded))
        hint = ("`evidence`, `attempts` and `risk` are written only by the core "
                "(`state transition`, `risk classify|override`)" if never else
                "to import history that never ran through Spec Master, pass --import-unverified with a --reason")
        raise InvalidTransitionError(
            f"state upsert-feature only records metadata; refused: {', '.join(rejected)} — {hint}"
        )

    merged = dict(base)
    for key, value in incoming.items():
        if key in TOOL_OWNED_FEATURE_FIELDS:
            continue
        merged[key] = value
    if allow_unverified and "analyze_repair_cycles" in incoming:
        merged["analyze_repair_cycles"] = incoming["analyze_repair_cycles"]
    merged["phases"] = dict(phases_after)
    merged.setdefault("status", "PENDING")
    merged.setdefault("analyze_repair_cycles", 0)
    imported = [phase for phase in FEATURE_PHASES
                if phases_after[phase] == "PASSED" and current_phases[phase] != "PASSED"]
    if existing is not None:
        state["features"][state["features"].index(existing)] = merged
    else:
        state["features"].append(merged)
    return merged, {"imported_phases": imported, "rejected": sorted(set(guarded)) if allow_unverified else []}


def upsert_feature(state: dict, feature: dict) -> dict:
    """Low-level upsert used by the core itself and by tests: replaces the
    record as given. Agents go through `upsert_feature_metadata` (the CLI)."""
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
    if status == "SKIPPED" and phase not in SKIPPABLE_PHASES:
        raise InvalidTransitionError(
            f"phase '{phase}' cannot be SKIPPED (skippable: {', '.join(SKIPPABLE_PHASES)})"
        )
    feature = find_feature(state, feature_id)
    phase_idx = FEATURE_PHASES.index(phase)
    if status in ("RUNNING", "PASSED", "SKIPPED") and phase_idx > 0:
        prev_phase = FEATURE_PHASES[phase_idx - 1]
        prev_status = feature["phases"].get(prev_phase, "PENDING")
        if prev_status not in DONE_PHASE_STATUSES:
            raise InvalidTransitionError(
                f"cannot start/pass '{phase}' before '{prev_phase}' has PASSED or been SKIPPED "
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
