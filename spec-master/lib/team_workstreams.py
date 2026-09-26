"""Team Mode verdict gating: peer review + Tech Lead integration authority.

Turns `conflict_policy.rules`' prose ("no implementation package is complete
until a different dev agent reviews it"; "the tech lead approves integration
after peer review") into enforced structural state (spec:
specs/004-team-mode-parallel-workstreams/spec.md). Wave computation, worktree
creation, and conflict detection are NOT duplicated here — call
`worktree.compute_waves` / `worktree.plan_worktree` / `worktree.conflicts`
directly (research.md #2); this module only adds verdict recording and
verdict-aware aggregation on top of `worktree.aggregate` (FR-008).
"""
from __future__ import annotations

import worktree


def _find_package(packages: list[dict], package_id: str) -> dict:
    for package in packages:
        if package["id"] == package_id:
            return package
    raise ValueError(f"unknown package id: {package_id!r}")


def record_review_verdict(packages: list[dict], package_id: str, reviewer_agent: str,
                           status: str, reason: str | None = None) -> list[dict]:
    """Record a peer-review verdict (FR-004, FR-006, research.md #3).

    Rejects a `reviewer_agent` that does not match the package's own
    assigned `reviewer_agent` — peer review cannot be self-recorded or
    spoofed by an arbitrary agent.
    """
    package = _find_package(packages, package_id)
    assigned = package.get("reviewer_agent")
    if reviewer_agent != assigned:
        raise ValueError(
            f"reviewer_agent {reviewer_agent!r} does not match package "
            f"{package_id!r}'s assigned reviewer_agent {assigned!r}"
        )
    if status == "REJECTED" and not reason:
        raise ValueError("reason is required when status is REJECTED")
    package["review_verdict"] = {
        "status": status,
        "reviewer_agent": reviewer_agent,
        "reason": reason,
    }
    return packages


def record_integration_verdict(packages: list[dict], package_id: str, status: str,
                                reason: str | None = None) -> list[dict]:
    """Record the Tech Lead's integration verdict (FR-005, FR-006, research.md #4).

    No `agent` argument — Team Mode's `technical_owner` is always the fixed
    constant `"tech-lead"`.
    """
    package = _find_package(packages, package_id)
    if status == "REJECTED" and not reason:
        raise ValueError("reason is required when status is REJECTED")
    package["integration_verdict"] = {"status": status, "reason": reason}
    return packages


def integration_state(package: dict) -> str:
    """Derive a package's integration state from its two verdict fields.

    Always computed fresh — never stored directly, so no path exists to
    mark a package integration-ready without both recorded `APPROVED`
    verdicts (FR-004, FR-005, SC-002; data-model.md).
    """
    review = package.get("review_verdict") or {}
    integration = package.get("integration_verdict") or {}
    if review.get("status") == "REJECTED" or integration.get("status") == "REJECTED":
        return "rejected"
    if review.get("status") != "APPROVED":
        return "review_pending"
    if integration.get("status") != "APPROVED":
        return "integration_pending"
    return "integration_ready"


def aggregate_with_verdicts(wave_index: int, handles: list[dict], packages: list[dict]) -> dict:
    """Fold `worktree.aggregate`'s result with each package's integration_state (FR-008).

    Read-only annotation pass over `worktree.aggregate`'s own output — never
    mutates its existing fields (data-model.md, Principle IV).
    """
    result = worktree.aggregate(wave_index, handles)
    packages_by_id = {package["id"]: package for package in packages}
    for feature in result["features"]:
        package = packages_by_id.get(feature["feature_id"])
        feature["integration_state"] = integration_state(package) if package else "review_pending"
    return result
