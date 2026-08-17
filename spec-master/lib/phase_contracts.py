"""Per-phase contract: required artifacts, write allowlist, and structural
checks shared by every guarded-mode integration adapter (CLAUDE.md-style
phase contract from docs/spec-master/guarded-mode-spec.md §6-7).

Pure stdlib, no subprocess, no LLM — deterministic and unit-testable.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import re
from pathlib import Path

# Bumped whenever the phase-contract semantics change in a way that could
# retroactively re-validate a previously-blocked attempt (resume's
# contract-revalidation, specs/002-guarded-noop-phase-validation/spec.md
# §11-12). Version 1 is implicit: any attempt recorded before this
# feature shipped has no `contract_version` field at all.
PHASE_CONTRACT_VERSION = 2

# Result policy per phase (specs/002-guarded-noop-phase-validation/spec.md §4).
PHASE_POLICY = {
    "constitution": "produce-or-update",
    "specify": "produce-or-update",
    "clarify": "inspect-or-update",
    "plan": "produce-or-update",
    "tasks": "produce-or-update",
    "analyze": "inspect-or-update",
    "implement": "execute",
    "validate": "produce-or-update",
}

PHASE_ARTIFACTS = {
    "constitution": (".specify/memory/constitution.md",),
    "specify": ("specs/*/spec.md", ".specify/feature.json"),
    "clarify": ("specs/*/spec.md",),
    "plan": ("specs/*/plan.md",),
    "tasks": ("specs/*/tasks.md",),
    "analyze": ("specs/*/spec.md", "specs/*/plan.md", "specs/*/tasks.md"),
    "implement": ("specs/*/tasks.md",),
    "validate": (".spec-master/reports/traceability.md", ".spec-master/reports/quality-gates.md"),
}

PHASE_ALLOWED_WRITES = {
    "constitution": (
        ".specify/memory/constitution.md",
        ".specify/templates/*",
        ".opencode/commands/*",
    ),
    "specify": ("specs/*", ".specify/feature.json"),
    "clarify": ("specs/*/spec.md",),
    "plan": ("specs/*", ".specify/feature.json"),
    "tasks": ("specs/*/tasks.md",),
    "analyze": ("specs/*",),
    "implement": ("*",),
    "validate": (".spec-master/reports/*",),
}

# Always rejected, on top of PHASE_ALLOWED_WRITES, regardless of phase.
PROTECTED_PATHS = (
    ".git/*",
    "spec-master/*",
    ".spec-master/state.json",
    ".spec-master/logs/*",
    ".spec-master/failed-attempts/*",
)

FAKE_TOOL_MARKERS = ("<function=", "<tool_call>", "</tool_call>")

# Known unfilled-template markers actually used by this repository's Spec Kit
# templates (.specify/templates/*.md). Deliberately NOT a generic "any
# [BRACKETED] text" regex: Spec Kit's own task/story labels ([US1], [P],
# [X]) and ordinary Markdown links ([text](url)) use the same bracket
# syntax for legitimate, filled content — a generic pattern would flag a
# correctly-completed tasks.md as still containing placeholders.
_PLACEHOLDER_PATTERNS = tuple(re.compile(pattern) for pattern in (
    r"\[PROJECT_NAME\]",
    r"\[PRINCIPLE_\d+_NAME\]",
    r"\[PRINCIPLE_\d+_DESCRIPTION\]",
    r"\[SECTION_\d+_NAME\]",
    r"\[SECTION_\d+_CONTENT\]",
    r"\[GOVERNANCE_RULES\]",
    r"\[CONSTITUTION_VERSION\]",
    r"\[RATIFICATION_DATE\]",
    r"\[LAST_AMENDED_DATE\]",
    r"\[FEATURE NAME\]",
    r"\[###-feature-name\]",
    r"\[DATE\]",
    r"NEEDS CLARIFICATION",
))

_SNAPSHOT_IGNORED_DIR_NAMES = (
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
)
_SNAPSHOT_IGNORED_RELATIVE_PREFIXES = (
    ".spec-master/failed-attempts/",
    ".spec-master/logs/",
)
_SNAPSHOT_IGNORED_RELATIVE_PATHS = (
    ".spec-master/state.json",
)


def validate_transcript(text: str) -> list[str]:
    return [marker for marker in FAKE_TOOL_MARKERS if marker in text]


def validate_artifacts(project: Path, phase: str) -> list[str]:
    missing = []
    for pattern in PHASE_ARTIFACTS[phase]:
        matches = list(project.glob(pattern))
        if not matches or not any(path.is_file() and path.stat().st_size for path in matches):
            missing.append(pattern)
    return missing


def _snapshot_ignored(relative: str) -> bool:
    parts = relative.split("/")
    if any(part in _SNAPSHOT_IGNORED_DIR_NAMES for part in parts[:-1]):
        return True
    if relative in _SNAPSHOT_IGNORED_RELATIVE_PATHS:
        return True
    return any(relative.startswith(prefix) for prefix in _SNAPSHOT_IGNORED_RELATIVE_PREFIXES)


def snapshot(project: Path) -> dict[str, str]:
    result = {}
    for path in project.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(project).as_posix()
        if _snapshot_ignored(relative):
            continue
        result[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def changed_paths(before: dict[str, str], after: dict[str, str]) -> list[str]:
    return sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path))


def forbidden_writes(paths: list[str], phase: str) -> list[str]:
    allowed = PHASE_ALLOWED_WRITES[phase]
    ignored = (".spec-master/run.lock", ".opencode/package.json", ".opencode/package-lock.json")
    protected = PROTECTED_PATHS
    return sorted([
        path for path in paths
        if path not in ignored
        and (
            any(fnmatch.fnmatch(path, pattern) for pattern in protected)
            or not any(fnmatch.fnmatch(path, pattern) for pattern in allowed)
        )
    ])


def placeholder_artifacts(project: Path, phase: str) -> list[str]:
    placeholders = []
    for pattern in PHASE_ARTIFACTS[phase]:
        for path in project.glob(pattern):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if any(marker.search(text) for marker in _PLACEHOLDER_PATTERNS):
                placeholders.append(path.relative_to(project).as_posix())
    return sorted(placeholders)


class ActiveFeatureUnresolved(Exception):
    pass


def resolve_active_feature_dir(project: Path) -> Path:
    """Resolve the active feature directory from `.specify/feature.json`.

    Never trusts a raw `specs/*/...` glob (which is ambiguous once a
    project has more than one feature directory — specs/002-guarded-noop-
    phase-validation/spec.md §7). Raises `ActiveFeatureUnresolved` for a
    missing/invalid file, an absolute or `..`-containing
    `feature_directory`, or one that resolves (including via a symlink)
    outside the project root.
    """
    project = Path(project).resolve()
    feature_json_path = project / ".specify" / "feature.json"
    try:
        data = json.loads(feature_json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise ActiveFeatureUnresolved(f"feature.json missing or invalid: {exc}") from exc

    feature_directory = data.get("feature_directory") if isinstance(data, dict) else None
    if not feature_directory or not isinstance(feature_directory, str):
        raise ActiveFeatureUnresolved("feature_directory missing or empty in feature.json")

    candidate = Path(feature_directory)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ActiveFeatureUnresolved(f"feature_directory is not a safe relative path: {feature_directory!r}")

    resolved = (project / candidate).resolve()
    try:
        resolved.relative_to(project)
    except ValueError as exc:
        raise ActiveFeatureUnresolved(f"feature_directory resolves outside the project: {feature_directory!r}") from exc
    return resolved


def _has_blocking_placeholder(path: Path) -> bool:
    if not path.is_file() or not path.stat().st_size:
        return True  # missing/empty counts as "not ready", same as a placeholder
    text = path.read_text(encoding="utf-8", errors="replace")
    return any(marker.search(text) for marker in _PLACEHOLDER_PATTERNS)


def clarify_result_ok(project: Path, structured_result: dict) -> bool:
    """Filesystem-level conditions 5-8 of spec.md §5 for a `clarify` no-op.

    Conditions 1-4 (process/transcript-level) and 9-11 (outcome-level) are
    already evaluated by `phase_runner.py` before this is called.
    """
    feature_dir = resolve_active_feature_dir(project)  # may raise ActiveFeatureUnresolved
    spec_path = feature_dir / "spec.md"
    return not _has_blocking_placeholder(spec_path)


def analyze_result_ok(project: Path, structured_result: dict) -> bool:
    """Filesystem-level conditions 1-2 of spec.md §8 for an `analyze` no-op."""
    feature_dir = resolve_active_feature_dir(project)  # may raise ActiveFeatureUnresolved
    return not any(
        _has_blocking_placeholder(feature_dir / name)
        for name in ("spec.md", "plan.md", "tasks.md")
    )
