"""Knowledge Router — selects a budgeted set of relevant knowledge modules
for an agent, instead of ever loading the whole knowledge base.

This is the enforcement point for the knowledge base's core design rule
(see model.py): "MORE KNOWLEDGE must not mean MORE PROMPT." Every selection
method here returns a ranked, capped list — callers get the most relevant
modules for their role and task, not everything that matches.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from .manifest import KnowledgeManifest
from .model import KnowledgeModule, DEPTH_LEVELS
from . import profiles


_DEPTH_RANK = {level: i for i, level in enumerate(sorted(DEPTH_LEVELS))}  # L0..L4 -> 0..4


def _depth_rank(module: KnowledgeModule, role: str) -> int:
    return _DEPTH_RANK.get(module.depth_for_role(role), 0)


def _keyword_score(module: KnowledgeModule, keywords: list[str]) -> int:
    if not keywords:
        return 0
    haystacks = [module.id.lower(), module.name.lower(), *(t.lower() for t in module.tags)]
    content = module.content.lower()
    score = 0
    for kw in keywords:
        k = kw.lower().strip()
        if not k:
            continue
        if any(k in h for h in haystacks):
            score += 3
        elif k in content:
            score += 1
    return score


def _rank(modules: list[KnowledgeModule], role: str, keywords: list[str],
          preferred_categories: list[str]) -> list[KnowledgeModule]:
    def sort_key(m: KnowledgeModule):
        cat_rank = preferred_categories.index(m.category) if m.category in preferred_categories else len(preferred_categories)
        return (
            -_keyword_score(m, keywords),
            -_depth_rank(m, role),
            cat_rank,
            m.id,
        )
    return sorted(modules, key=sort_key)


class KnowledgeRouter:
    """Selects relevant, budgeted knowledge modules for an agent role/task."""

    def __init__(self, manifest: "KnowledgeManifest | None" = None) -> None:
        self.manifest = manifest or KnowledgeManifest()

    def for_role(self, role: str, limit: int = profiles.DEFAULT_MODULE_BUDGET
                 ) -> list[KnowledgeModule]:
        """Modules applicable to a role, ranked by expected depth and category fit."""
        k_role = profiles.resolve_knowledge_role(role)
        candidates = self.manifest.by_role(k_role)
        preferred = profiles.CATEGORY_WEIGHTS_BY_ROLE.get(k_role, [])
        ranked = _rank(candidates, k_role, [], preferred)
        return ranked[:limit]

    def for_query(self, role: str, query: str,
                  limit: int = profiles.DEFAULT_MODULE_BUDGET
                  ) -> list[KnowledgeModule]:
        """Modules applicable to a role that also match a free-text query."""
        k_role = profiles.resolve_knowledge_role(role)
        role_ids = {m.id for m in self.manifest.by_role(k_role)}
        matches = [m for m in self.manifest.search(query) if m.id in role_ids]
        preferred = profiles.CATEGORY_WEIGHTS_BY_ROLE.get(k_role, [])
        ranked = _rank(matches, k_role, [query], preferred)
        return ranked[:limit]

    def for_context(self, role: str, keywords: "list[str] | None" = None,
                     tech_stacks: "list[str] | None" = None,
                     limit: int = profiles.DEFAULT_MODULE_BUDGET
                     ) -> list[KnowledgeModule]:
        """Primary entrypoint: modules relevant to a role working on a task.

        Combines role applicability, keyword relevance (feature description,
        task title, tags — anything worth matching against), and a category
        boost derived from the project's detected tech stack. Always returns
        at most `limit` modules, ranked most-relevant first.
        """
        keywords = keywords or []
        k_role = profiles.resolve_knowledge_role(role)
        role_modules = self.manifest.by_role(k_role)

        preferred = list(profiles.CATEGORY_WEIGHTS_BY_ROLE.get(k_role, []))
        if tech_stacks:
            stack_categories = profiles.stack_languages_to_categories(tech_stacks)
            preferred = stack_categories + preferred

        if keywords:
            candidate_ids = {m.id for m in role_modules}
            keyword_hits: dict[str, KnowledgeModule] = {}
            for kw in keywords:
                for m in self.manifest.search(kw):
                    if m.id in candidate_ids:
                        keyword_hits[m.id] = m
            pool = list(keyword_hits.values()) or role_modules
        else:
            pool = role_modules

        ranked = _rank(pool, k_role, keywords, preferred)
        return ranked[:limit]

    def budget_summary(self, modules: list[KnowledgeModule]) -> dict:
        """Describe a selection for CLI/agent visibility into what was loaded."""
        return {
            "count": len(modules),
            "ids": [m.id for m in modules],
            "categories": sorted({m.category for m in modules}),
            "total_content_chars": sum(len(m.content) for m in modules),
        }
