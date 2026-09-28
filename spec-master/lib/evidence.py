"""Evidence required before a feature phase is promoted (constitution Principle IV).

The state machine (state.py) enforces the *order* of the phases. This module
checks the other half of Principle IV: a phase promoted to PASSED must have
left its required artifact behind, inside the feature's own spec directory,
non-empty and free of unresolved template placeholders. The CLI records the
result under `feature["evidence"][phase]` (paths, hashes and the checks that
ran), so a later reader can tell a verified promotion from imported history.

Pure stdlib, no subprocess, no LLM.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re
from pathlib import Path

import phase_contracts

# Artifacts each phase must leave in the feature's spec directory.
PHASE_FILES = {
    "specify": ("spec.md",),
    "clarify": ("spec.md",),
    "plan": ("plan.md",),
    "tasks": ("tasks.md",),
    "analyze": ("spec.md", "plan.md", "tasks.md"),
    "implement": ("tasks.md",),
    "validate": (),
}

_TASK_LINE_RE = re.compile(r"^\s*[-*]\s*\[( |x|X)\]\s*(T\d+[a-z]?)\b")


class EvidenceError(ValueError):
    pass


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve_spec_dir(root: str | Path, feature: dict) -> tuple[Path | None, str | None]:
    """(directory, None) or (None, reason) for the feature's `spec_directory`."""
    spec_dir = feature.get("spec_directory")
    if not isinstance(spec_dir, str) or not spec_dir.strip():
        return None, "feature has no spec_directory (record it with `state upsert-feature`)"
    root = Path(root).resolve()
    try:
        resolved = phase_contracts.feature_dir_path(root, spec_dir)
    except phase_contracts.ActiveFeatureUnresolved as exc:
        return None, str(exc)
    return resolved, None


def open_tasks(text: str) -> list[str]:
    """Ids of the Spec Kit task lines still unchecked (`- [ ] T012 ...`)."""
    return [match.group(2) for match in map(_TASK_LINE_RE.match, (text or "").splitlines())
            if match and match.group(1) == " "]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(root: str | Path, feature: dict, phase: str, *, traceability_rows: list | None = None) -> dict:
    """Evaluate the evidence for promoting `phase` of `feature` to PASSED.

    Returns {"feature", "phase", "ok", "checks": [{name, ok, detail}],
    "artifacts": [{path, sha256, bytes}]}. Never raises for a missing or bad
    artifact: that is a failed check, reported to the caller.
    """
    if phase not in PHASE_FILES:
        raise EvidenceError(f"unknown phase: {phase}")
    root = Path(root).resolve()
    checks: list[dict] = []
    artifacts: list[dict] = []

    if phase == "validate":
        rows = [row for row in (traceability_rows or []) if isinstance(row, dict)]
        checks.append({
            "name": "traceability_rows",
            "ok": bool(rows),
            "detail": f"{len(rows)} traceability row(s) recorded for the feature"
                      + ("" if rows else " — record them with `traceability add` before validating"),
        })
    else:
        spec_dir, problem = resolve_spec_dir(root, feature)
        if problem:
            checks.append({"name": "spec_directory", "ok": False, "detail": problem})
        else:
            for name in PHASE_FILES[phase]:
                path = spec_dir / name
                relative = path.relative_to(root).as_posix()
                if not path.is_file() or path.stat().st_size == 0:
                    checks.append({"name": f"artifact:{name}", "ok": False, "detail": f"{relative} is missing or empty"})
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
                markers = phase_contracts.placeholder_markers(text)
                checks.append({
                    "name": f"artifact:{name}",
                    "ok": not markers,
                    "detail": relative if not markers else f"{relative} has unresolved placeholders: {', '.join(markers)}",
                })
                artifacts.append({"path": relative, "sha256": _sha256(path), "bytes": path.stat().st_size})
                if phase == "implement" and name == "tasks.md":
                    pending = open_tasks(text)
                    checks.append({
                        "name": "tasks_checked",
                        "ok": not pending,
                        "detail": "every task is checked" if not pending
                        else f"{len(pending)} task(s) still unchecked: {', '.join(pending[:10])}",
                    })

    return {
        "feature": feature.get("id"),
        "phase": phase,
        "ok": bool(checks) and all(item["ok"] for item in checks),
        "checks": checks,
        "artifacts": artifacts,
    }


def record(feature: dict, result: dict, *, now: str | None = None) -> dict:
    """Store a passing check under feature["evidence"][phase]."""
    if not result.get("ok"):
        raise EvidenceError(f"cannot record failed evidence for {result.get('phase')}")
    entry = {
        "verified": True,
        "at": now or _now(),
        "checks": [item["name"] for item in result["checks"]],
        "artifacts": result["artifacts"],
    }
    feature.setdefault("evidence", {})[result["phase"]] = entry
    return entry


def record_unverified(feature: dict, phase: str, reason: str, *, now: str | None = None) -> dict:
    """Mark a promotion that did not go through `check` (imported history)."""
    if not (reason or "").strip():
        raise EvidenceError("an unverified promotion needs a reason")
    entry = {"verified": False, "at": now or _now(), "reason": reason.strip()}
    feature.setdefault("evidence", {})[phase] = entry
    return entry


def summary(feature: dict) -> dict:
    """Per-phase evidence status: verified, unverified or missing (PASSED
    without any evidence record — promoted before this module existed)."""
    evidence = feature.get("evidence") or {}
    result = {}
    for phase, status in (feature.get("phases") or {}).items():
        if status != "PASSED":
            continue
        entry = evidence.get(phase)
        if entry is None:
            result[phase] = "missing"
        else:
            result[phase] = "verified" if entry.get("verified") else "unverified"
    return result
