"""Knowledge module model for the Spec Master Global Concept Knowledge Base.

Each knowledge module is a Markdown file with structured YAML frontmatter.
Modules represent reusable concepts (patterns, principles, laws, technologies)
that agents can selectively load based on their profile and the current task.

The key rule: MORE KNOWLEDGE must not mean MORE PROMPT.
Modules are loaded selectively, never dumped wholesale into agent context.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dataclasses import dataclass, field

from graph.parser import parse_frontmatter, extract_wikilinks

# Valid depth levels for skill proficiency
DEPTH_LEVELS = {"L0", "L1", "L2", "L3", "L4"}

# Valid agent roles that can be referenced in modules
AGENT_ROLES = {
    "architect", "tech-lead", "backend-dev", "frontend-dev",
    "fullstack-dev", "qa", "devops", "infrastructure", "security",
    "product-owner", "scrum-master", "ux", "spec-master",
}


@dataclass
class KnowledgeModule:
    """A single concept knowledge module loaded from a .md file."""

    id: str                          # Stable namespaced ID: "architecture.hexagonal"
    type: str                        # From ontology: Pattern, Principle, Technology, etc.
    name: str                        # Human-readable name
    category: str                    # Domain category: architecture, security, agile, etc.
    tags: list[str] = field(default_factory=list)
    applicable_roles: list[str] = field(default_factory=list)
    depth: dict[str, str] = field(default_factory=dict)   # role -> L0..L4
    related: list[str] = field(default_factory=list)       # wikilink targets
    content: str = ""               # Markdown body
    source_path: str = ""           # Absolute path to the .md file
    raw_frontmatter: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "name": self.name,
            "category": self.category,
            "tags": self.tags,
            "applicable_roles": self.applicable_roles,
            "depth": self.depth,
            "related": self.related,
            "source_path": self.source_path,
        }

    @classmethod
    def from_file(cls, path: "str | Path") -> "KnowledgeModule | None":
        """Parse a knowledge module from a Markdown file."""
        try:
            text = Path(path).read_text(encoding="utf-8")
        except OSError:
            return None

        fm, body = parse_frontmatter(text)
        if not fm.get("id"):
            return None

        return cls(
            id=str(fm["id"]),
            type=str(fm.get("type", "Pattern")),
            name=str(fm.get("name", fm["id"])),
            category=str(fm.get("category", "general")),
            tags=list(fm.get("tags") or []),
            applicable_roles=list(fm.get("applicable_roles") or []),
            depth=dict(fm.get("depth") or {}),
            related=extract_wikilinks(body),
            content=body.strip(),
            source_path=str(path),
            raw_frontmatter=fm,
        )

    def depth_for_role(self, role: str) -> str:
        """Return the depth level expected of a given role, or L0 if unspecified."""
        return self.depth.get(role, "L0")

    def is_applicable_to(self, role: str) -> bool:
        """Return True if this module is applicable to the given agent role."""
        if not self.applicable_roles:
            return True  # no restriction = applicable to all
        return role in self.applicable_roles
