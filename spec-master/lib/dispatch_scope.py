"""Per-worktree governance for dispatched subagents (hookd hook point).

A prepared worktree carries `.spec-master/worktree.json` (written by
`dispatch.prepare`). When it exists, writes are limited to the package's
`owned_paths` (plus tests and harness files); a read-only reviewer writes
nothing. Without the marker this module has no opinion. Cost: one `os.stat`
on the hook path when no marker exists.
"""
from __future__ import annotations

import fnmatch
import json
import os

from kernel import paths, policy

MARKER = os.path.join(".spec-master", "worktree.json")


def _relative(root: str, target: str) -> str:
    if os.path.isabs(target):
        return paths.norm(os.path.relpath(os.path.realpath(target), os.path.realpath(root)))
    return paths.norm(target)


def _owned(patterns, relative: str) -> bool:
    for pattern in patterns or []:
        pattern = paths.norm(pattern)
        if pattern.endswith("/") and relative.startswith(pattern):
            return True
        if relative == pattern or fnmatch.fnmatch(relative, pattern):
            return True
    return False


def guard(root: str, target: str):
    """A DENY verdict (`decision`, `reason`) when the write breaks the worktree scope, else None."""
    marker = os.path.join(root, MARKER)
    if not os.path.isfile(marker):
        return None
    try:
        with open(marker, "r", encoding="utf-8") as fh:
            scope = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(scope, dict):
        return None
    relative = _relative(root, target)
    if paths.is_harness(relative) and not scope.get("read_only"):
        return None
    if scope.get("read_only"):
        return {"decision": policy.DENY,
                "reason": f"worktree scope: {scope.get('agent_key')} is a read-only reviewer and cannot write {relative}"}
    if paths.is_test_path(relative) or _owned(scope.get("owned_paths"), relative):
        return None
    return {"decision": policy.DENY,
            "reason": f"worktree scope: {relative} is outside the owned_paths of {scope.get('agent_key')}"}
