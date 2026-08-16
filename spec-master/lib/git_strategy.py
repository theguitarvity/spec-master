"""Git strategy decisions (CLAUDE.md sections 7, 8, 9).

Purely deterministic: derives a branch name and reports whether the Spec Kit
git extension is already present, so the agent never reinstalls it and never
manages branches in parallel with a mechanism Spec Kit already provides.
"""
from __future__ import annotations

import re


def slugify(name: str) -> str:
    slug = name.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "feature"


_IDENTIFIER_RE = re.compile(r"\b([A-Z][A-Z0-9]+-\d+|issue-\d+)\b")


def extract_identifier(text: str) -> str | None:
    match = _IDENTIFIER_RE.search(text)
    return match.group(1) if match else None


def branch_name(feature_name: str, prefix: str = "feature", issue_id: str | None = None) -> str:
    """Derive an idempotent branch name.

    If an explicit identifier is provided (or found inside feature_name),
    it is preserved verbatim per section 8. Otherwise a slug is derived from
    the feature name.
    """
    identifier = issue_id or extract_identifier(feature_name)
    if identifier:
        return identifier
    return f"{prefix}/{slugify(feature_name)}"


def plan(strategy: str, feature_name: str, issue_id: str | None = None,
         git_extension_installed: bool = False, spec_kit_present: bool = False) -> dict:
    if strategy not in ("git-flow", "trunk"):
        raise ValueError(f"unknown strategy: {strategy}")

    if strategy == "trunk":
        return {
            "strategy": "trunk",
            "create_branch": False,
            "branch": None,
            "install_git_extension": False,
            "reason": "Trunk-Based Development: work stays on the current branch; "
                      "feature separation is logical (specs/ directories), not branch-based.",
        }

    # git-flow / feature branches
    should_install_extension = spec_kit_present and not git_extension_installed
    return {
        "strategy": "git-flow",
        "create_branch": True,
        "branch": branch_name(feature_name, issue_id=issue_id),
        "install_git_extension": should_install_extension,
        "reason": (
            "Spec Kit git extension already present; reusing it."
            if git_extension_installed
            else "Spec Kit git extension not detected; install once (idempotent) before branching."
            if spec_kit_present
            else "Spec Kit not installed; branch will be created without Spec Kit git automation."
        ),
    }
