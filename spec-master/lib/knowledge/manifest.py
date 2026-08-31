"""Knowledge module manifest — index of all concept knowledge modules.

Scans the knowledge/ directory tree for .md files with valid frontmatter,
builds an in-memory index, and provides query methods by role, tag,
category, and topic.

This is the entry point for the Knowledge Router to discover available
concept knowledge without loading all module content.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from .model import KnowledgeModule


def _find_knowledge_root(start: "Path | None" = None) -> "Path | None":
    """Search for the knowledge/ directory relative to spec-master package.

    Excludes this module's own directory (lib/knowledge/, the Python package)
    from matching, since it shares its name with the real content root
    (spec-master/knowledge/) and would otherwise shadow it.
    """
    self_dir = Path(__file__).resolve().parent
    here = start or self_dir
    for ancestor in [here, here.parent, here.parent.parent, here.parent.parent.parent]:
        candidate = ancestor / "knowledge"
        if candidate.is_dir() and candidate != self_dir:
            return candidate
    return None


class KnowledgeManifest:
    """Index of all knowledge modules available in the knowledge base."""

    def __init__(self, knowledge_root: "str | Path | None" = None) -> None:
        if knowledge_root:
            self._root = Path(knowledge_root)
        else:
            found = _find_knowledge_root()
            self._root = found if found else Path("knowledge")
        self._modules: dict[str, KnowledgeModule] = {}
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._modules.clear()
        if not self._root.exists():
            self._loaded = True
            return
        for md_file in sorted(self._root.rglob("*.md")):
            # Skip map and index files
            if md_file.parent.name in ("maps", "indexes"):
                continue
            module = KnowledgeModule.from_file(md_file)
            if module:
                self._modules[module.id] = module
        self._loaded = True

    def all_modules(self) -> list[KnowledgeModule]:
        self._ensure_loaded()
        return list(self._modules.values())

    def get(self, module_id: str) -> "KnowledgeModule | None":
        self._ensure_loaded()
        return self._modules.get(module_id)

    def by_role(self, role: str) -> list[KnowledgeModule]:
        self._ensure_loaded()
        return [m for m in self._modules.values() if m.is_applicable_to(role)]

    def by_tag(self, tag: str) -> list[KnowledgeModule]:
        self._ensure_loaded()
        return [m for m in self._modules.values() if tag in m.tags]

    def by_category(self, category: str) -> list[KnowledgeModule]:
        self._ensure_loaded()
        return [m for m in self._modules.values() if m.category == category]

    def by_ids(self, ids: list[str]) -> list[KnowledgeModule]:
        self._ensure_loaded()
        return [self._modules[mid] for mid in ids if mid in self._modules]

    def search(self, query: str) -> list[KnowledgeModule]:
        """Simple text search over ids, names, tags, and content."""
        self._ensure_loaded()
        q = query.lower()
        results = []
        for m in self._modules.values():
            if (q in m.id.lower() or q in m.name.lower()
                    or any(q in t.lower() for t in m.tags)
                    or q in m.content.lower()):
                results.append(m)
        return results

    def stats(self) -> dict:
        self._ensure_loaded()
        from collections import Counter
        cats = Counter(m.category for m in self._modules.values())
        types = Counter(m.type for m in self._modules.values())
        return {
            "total_modules": len(self._modules),
            "by_category": dict(cats),
            "by_type": dict(types),
        }
