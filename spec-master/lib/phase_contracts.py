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


def placeholder_markers(text: str) -> list[str]:
    """The unresolved template markers found in `text` (empty when clean)."""
    found = []
    for pattern in _PLACEHOLDER_PATTERNS:
        match = pattern.search(text or "")
        if match:
            found.append(match.group(0))
    return found


def _safe_feature_dir(feature_dir: str | None) -> str | None:
    if not feature_dir:
        return None
    candidate = Path(feature_dir)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"feature_dir is not a safe relative path: {feature_dir!r}")
    return candidate.as_posix().strip("/")


def scoped_patterns(patterns, feature_dir: str | None, *, keep_feature_json: bool = False) -> tuple[str, ...]:
    """Rewrite `specs/*/...` patterns to the given feature directory.

    With several feature directories in `specs/`, a `specs/*/plan.md` glob is
    satisfied (or tripped) by any feature, not the one being worked on. When
    the caller knows the feature's directory, every `specs/*` pattern is
    narrowed to it; `.specify/feature.json` (Spec Kit's own pointer to the
    active feature, gitignored by Spec Kit itself) is then no longer needed as
    an artifact, since the feature directory is already known. `feature_dir`
    None keeps the historical global patterns unchanged.
    """
    scoped_dir = _safe_feature_dir(feature_dir)
    if scoped_dir is None:
        return tuple(patterns)
    result = []
    for pattern in patterns:
        if pattern.startswith("specs/*/"):
            result.append(f"{scoped_dir}/{pattern[len('specs/*/'):]}")
        elif pattern == "specs/*":
            result.append(f"{scoped_dir}/*")
        elif pattern == ".specify/feature.json" and not keep_feature_json:
            continue
        else:
            result.append(pattern)
    return tuple(result)


def phase_artifacts(phase: str, feature_dir: str | None = None) -> tuple[str, ...]:
    return scoped_patterns(PHASE_ARTIFACTS[phase], feature_dir)


def validate_artifacts(project: Path, phase: str, feature_dir: str | None = None) -> list[str]:
    missing = []
    for pattern in phase_artifacts(phase, feature_dir):
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


def forbidden_writes(paths: list[str], phase: str, feature_dir: str | None = None) -> list[str]:
    # Spec Kit's create-new-feature script still writes .specify/feature.json,
    # so it stays writable even when the allowlist is narrowed to one feature.
    allowed = scoped_patterns(PHASE_ALLOWED_WRITES[phase], feature_dir, keep_feature_json=True)
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


def placeholder_artifacts(project: Path, phase: str, feature_dir: str | None = None) -> list[str]:
    placeholders = []
    for pattern in phase_artifacts(phase, feature_dir):
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


def feature_dir_path(project: Path, feature_dir: str | None = None) -> Path:
    """The feature directory: the known one when given (it must exist inside
    the project), else Spec Kit's `.specify/feature.json` pointer."""
    if not feature_dir:
        return resolve_active_feature_dir(project)
    project = Path(project).resolve()
    try:
        relative = _safe_feature_dir(feature_dir)
    except ValueError as exc:
        raise ActiveFeatureUnresolved(str(exc)) from exc
    resolved = (project / relative).resolve()
    try:
        resolved.relative_to(project)
    except ValueError as exc:
        raise ActiveFeatureUnresolved(f"feature_dir resolves outside the project: {feature_dir!r}") from exc
    if not resolved.is_dir():
        raise ActiveFeatureUnresolved(f"feature_dir not found: {feature_dir!r}")
    return resolved


def clarify_result_ok(project: Path, structured_result: dict, feature_dir: str | None = None) -> bool:
    """Filesystem-level conditions 5-8 of spec.md §5 for a `clarify` no-op.

    Conditions 1-4 (process/transcript-level) and 9-11 (outcome-level) are
    already evaluated by `phase_runner.py` before this is called.
    """
    resolved = feature_dir_path(project, feature_dir)  # may raise ActiveFeatureUnresolved
    spec_path = resolved / "spec.md"
    return not _has_blocking_placeholder(spec_path)


def analyze_result_ok(project: Path, structured_result: dict, feature_dir: str | None = None) -> bool:
    """Filesystem-level conditions 1-2 of spec.md §8 for an `analyze` no-op."""
    resolved = feature_dir_path(project, feature_dir)  # may raise ActiveFeatureUnresolved
    return not any(
        _has_blocking_placeholder(resolved / name)
        for name in ("spec.md", "plan.md", "tasks.md")
    )
