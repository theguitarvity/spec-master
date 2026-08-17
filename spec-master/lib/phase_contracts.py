"""Per-phase contract: required artifacts, write allowlist, and structural
checks shared by every guarded-mode integration adapter (CLAUDE.md-style
phase contract from docs/spec-master/guarded-mode-spec.md §6-7).

Pure stdlib, no subprocess, no LLM — deterministic and unit-testable.
"""
from __future__ import annotations

import fnmatch
import hashlib
import re
from pathlib import Path

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
