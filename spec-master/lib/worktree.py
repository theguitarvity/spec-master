"""Parallel worktree execution: waves, isolated git worktrees, aggregation.

Deterministic core for running independent features concurrently in their
own `git worktree` (spec: specs/003-parallel-worktree-execution/spec.md).
Every git invocation goes through the single `run_git()` boundary so tests
mock one call site instead of requiring a real repository (Principle III).
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path


def run_git(args: list[str], cwd: str) -> subprocess.CompletedProcess:
    """The one `subprocess.run` call site for this module (research.md #3)."""
    return subprocess.run(
        ["git", *args], cwd=cwd, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
    )


def compute_waves(ordered_features: list[dict]) -> list[dict]:
    """Group an already-ordered feature list into concurrency waves (FR-001).

    A feature enters wave N the first time every entry in its own
    `dependencies` list has been placed in an earlier wave (0..N-1). Input
    must already be topologically sorted (`feature_model.order_features()`
    output) — this only groups, it never reorders.
    """
    wave_of: dict[str, int] = {}
    waves: list[list[str]] = []
    for feature in ordered_features:
        feature_id = feature["id"]
        dependencies = feature.get("dependencies", [])
        wave_index = max((wave_of[dep] for dep in dependencies), default=-1) + 1
        wave_of[feature_id] = wave_index
        while len(waves) <= wave_index:
            waves.append([])
        waves[wave_index].append(feature_id)
    return [{"wave_index": index, "feature_ids": ids} for index, ids in enumerate(waves)]


def _worktree_path(project_root: str, feature_id: str) -> str:
    return str(Path(project_root) / ".spec-master" / "worktrees" / feature_id)


def plan_worktree(feature_id: str, project_root: str, strategy: str,
                   wave_size: int = 2, is_git_repo: bool = True) -> dict:
    """Create (or idempotently resume) an isolated worktree for a feature.

    FR-002/FR-003: one isolated worktree per feature in a multi-feature
    wave. FR-004/FR-005: never create one for a single-feature wave or a
    non-git repo — that feature runs directly on `project_root` instead.
    Idempotent (spec.md Edge Case 3, SC-003; research.md #2): if the target
    path already exists, it is reused/resumed as-is, never recreated.
    """
    if wave_size <= 1 or not is_git_repo:
        return {"feature_id": feature_id, "path": project_root, "state": "skipped", "branch": None}

    path = _worktree_path(project_root, feature_id)
    if os.path.isdir(path):
        return {"feature_id": feature_id, "path": path, "state": "created", "branch": None}

    if strategy == "git-flow":
        branch = f"feature/{feature_id}"
        run_git(["worktree", "add", "-b", branch, path], cwd=project_root)
    else:
        branch = None
        run_git(["worktree", "add", "--detach", path], cwd=project_root)

    return {"feature_id": feature_id, "path": path, "state": "created", "branch": branch}


def resolve_project_root(handle: dict) -> str:
    """The project root every phase-loop call for this feature MUST use.

    FR-003, research.md #5: isolation is enforced by which path the caller
    passes to the phase loop, not by new sandboxing logic in the core.
    """
    return handle["path"]


def _resolve_head(path: str) -> str:
    result = run_git(["rev-parse", "HEAD"], cwd=path)
    return (result.stdout or "").strip()


def _changed_files_since(path: str, since_ref: str, head_ref: str) -> set[str]:
    result = run_git(["diff", "--name-only", since_ref, head_ref], cwd=path)
    return {line.strip() for line in (result.stdout or "").splitlines() if line.strip()}


def conflicts(path_a: str, path_b: str) -> dict:
    """Read-only file-level overlap check between two worktrees (FR-007).

    Diff-intersection first pass (research.md #4): each worktree's changed
    files since their common merge-base are computed and intersected. Only
    read-only git plumbing (`rev-parse`, `merge-base`, `diff --name-only`)
    is used, so neither worktree's index or working tree is ever touched —
    unlike an actual `git merge` attempt, which FR-007 forbids equating
    with "discard".
    """
    head_a = _resolve_head(path_a)
    head_b = _resolve_head(path_b)
    base = (run_git(["merge-base", head_a, head_b], cwd=path_a).stdout or "").strip()
    files_a = _changed_files_since(path_a, base, head_a)
    files_b = _changed_files_since(path_b, base, head_b)
    return {"files": sorted(files_a & files_b)}


def aggregate(wave_index: int, handles: list[dict]) -> dict:
    """Fold finished worktree handles into a write-once Aggregation Result.

    FR-006: records each feature's final status and changed files. FR-008:
    never deletes or mutates a handle — a non-terminal handle's directory
    is left exactly as the caller passed it. Conflict detection is a
    separate, explicit `conflicts()` call per handle pair — this is a pure
    fold, it never talks to git itself (contracts/cli-worktree.md).
    """
    features = [
        {
            "feature_id": handle["feature_id"],
            "final_status": handle.get("final_status", handle.get("state")),
            "changed_files": handle.get("changed_files", []),
        }
        for handle in handles
    ]
    return {"wave_index": wave_index, "features": features, "conflicts": []}
