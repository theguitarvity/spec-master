"""Agent knowledge profiles for the Spec Master Global Concept Knowledge Base.

Team Mode (team_model.py) and the knowledge base (knowledge/model.py) grew
their role vocabularies independently: team_model.py's AGENT_ROLES uses ids
like "po", "infra", "ui-ux-brand", while knowledge modules' applicable_roles
and depth maps use "product-owner", "infrastructure", "ux" (see model.py's
AGENT_ROLES). This module is the single place that reconciles the two, plus
the per-role knowledge preferences (which categories matter most, and how
many modules a role should typically receive) used by the router.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from .model import AGENT_ROLES as KNOWLEDGE_ROLES  # noqa: E402


# team_model.py role id -> knowledge base role id, for the ids that differ.
# Any role id not listed here is assumed identical in both vocabularies.
TEAM_ROLE_ALIASES: dict[str, str] = {
    "po": "product-owner",
    "infra": "infrastructure",
    "ui-ux-brand": "ux",
}

# Default number of knowledge modules to hand an agent for one task.
# The knowledge base's own design rule is "more knowledge must not mean more
# prompt" (see model.py) — this is the concrete enforcement of that rule.
DEFAULT_MODULE_BUDGET = 8

# Per-role category priority order, used to rank modules when relevance is
# otherwise tied (no keyword/tag match to break the tie on). Categories not
# listed for a role are still eligible, just ranked after the listed ones.
CATEGORY_WEIGHTS_BY_ROLE: dict[str, list[str]] = {
    "architect": ["architecture", "distributed-systems", "design", "foundations", "anti-patterns"],
    "tech-lead": ["architecture", "foundations", "design", "distributed-systems", "anti-patterns"],
    "backend-dev": ["design", "foundations", "distributed-systems", "architecture", "security"],
    "frontend-dev": ["foundations", "design", "architecture"],
    "fullstack-dev": ["foundations", "design", "architecture", "distributed-systems"],
    "qa": ["foundations", "anti-patterns", "security"],
    "devops": ["distributed-systems", "security", "architecture"],
    "infrastructure": ["distributed-systems", "security", "architecture"],
    "security": ["security", "architecture", "distributed-systems"],
    "product-owner": ["agile", "foundations"],
    "scrum-master": ["agile"],
    "ux": ["foundations", "design"],
    "spec-master": ["foundations", "architecture", "agile", "distributed-systems", "security", "design"],
}

# Maps discovery.py's detected stack "language" values to the knowledge base's
# stacks/ subdirectory name, for future stack-specific module routing.
STACK_TO_CATEGORY: dict[str, str] = {
    "node": "node",
    "python": "python",
    "go": "go",
    "java": "java",
    "java/kotlin": "java",
}


def resolve_knowledge_role(role_id: str) -> str:
    """Normalize a team_model.py role id to its knowledge-base role id.

    Returns the input unchanged if it's already a valid knowledge-base role
    id, or has no known alias (callers that filter by role should treat an
    unrecognized id as "no restriction" rather than erroring).
    """
    return TEAM_ROLE_ALIASES.get(role_id, role_id)


def is_known_knowledge_role(role_id: str) -> bool:
    return role_id in KNOWLEDGE_ROLES


def category_weight(role_id: str, category: str) -> int:
    """Lower is higher priority. Unlisted categories rank after listed ones."""
    order = CATEGORY_WEIGHTS_BY_ROLE.get(resolve_knowledge_role(role_id), [])
    if category in order:
        return order.index(category)
    return len(order)


def stack_languages_to_categories(stack_languages: list[str]) -> list[str]:
    """Map discovery.py stack language strings to stacks/ category names."""
    seen = []
    for lang in stack_languages:
        cat = STACK_TO_CATEGORY.get(lang)
        if cat and cat not in seen:
            seen.append(cat)
    return seen
