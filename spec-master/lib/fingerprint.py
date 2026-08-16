"""Context fingerprinting and staleness propagation (CLAUDE.md section 33).

Pure stdlib. Computes stable hashes of the normalized context documents and
determines which pipeline phases become stale when a document changes.
"""
from __future__ import annotations

import hashlib
import os

# Downstream propagation order (section 33 example):
# app-features.md changed -> specify stale -> plan stale -> tasks stale -> analyze stale
# implement is never auto-invalidated; impact must be assessed (spec drift), not assumed.
DOC_TO_STALE_PHASES = {
    "app-features.md": ["specify", "clarify", "plan", "tasks", "analyze"],
    "project-goals.md": ["specify", "clarify", "plan", "tasks", "analyze"],
    "tech-stack.md": ["plan", "tasks", "analyze"],
}


def compute_file_hash(path: str) -> str:
    with open(path, "rb") as fh:
        content = fh.read()
    return hashlib.sha256(content).hexdigest()


def compute(files: list[str]) -> dict:
    result = {}
    for f in files:
        name = os.path.basename(f)
        result[name] = compute_file_hash(f) if os.path.exists(f) else None
    return result


def compare(previous: dict, current: dict) -> dict:
    """Compare two {filename: hash} maps.

    Returns {"changed": [...filenames...], "stale_phases": {feature_scope: [...]}}
    stale_phases is a flat, de-duplicated, order-preserving list of phase names
    that any changed doc marks as potentially stale.
    """
    changed = []
    all_names = set(previous.keys()) | set(current.keys())
    for name in sorted(all_names):
        if previous.get(name) != current.get(name):
            changed.append(name)

    stale_phases: list[str] = []
    for name in changed:
        for phase in DOC_TO_STALE_PHASES.get(name, []):
            if phase not in stale_phases:
                stale_phases.append(phase)

    return {"changed": changed, "stale_phases": stale_phases}
