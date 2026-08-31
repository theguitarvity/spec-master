"""Markdown frontmatter and wikilink parser for graph nodes.

Parses YAML frontmatter from Markdown files (no external YAML dependency
for basic cases — falls back to a minimal line-based parser).
Extracts [[wikilinks]] from content and converts them to GraphEdge objects.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .model import GraphNode, GraphEdge

try:
    import yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

# Matches [[target]] or [[target|label]]
_WIKILINK_RE = re.compile(r"\[\[([^\]|]+?)(?:\|[^\]]+)?\]\]")

# Frontmatter block: content between opening and closing ---
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Extract YAML frontmatter and body from markdown text.
    Returns (frontmatter_dict, body_without_frontmatter).
    """
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text

    fm_text = match.group(1)
    body = text[match.end():]

    if _HAS_YAML:
        try:
            fm = yaml.safe_load(fm_text)
            return (fm if isinstance(fm, dict) else {}), body
        except Exception:
            pass

    # Minimal fallback: parse simple key: value pairs
    fm: dict = {}
    for line in fm_text.splitlines():
        if ":" in line and not line.startswith(" ") and not line.startswith("-"):
            key, _, value = line.partition(":")
            fm[key.strip()] = value.strip()
    return fm, body


def extract_wikilinks(text: str) -> list[str]:
    """Return all wikilink targets found in text."""
    return _WIKILINK_RE.findall(text)


def parse_node_file(path: str | Path) -> "GraphNode | None":
    """Parse a Markdown node file into a GraphNode. Returns None on failure."""
    from .model import GraphNode
    from .ontology import coerce_relation_type, validate_entity_type

    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return None

    fm, body = parse_frontmatter(text)
    if not fm.get("id"):
        return None

    node_type = fm.get("type", "Component")
    if not validate_entity_type(node_type):
        node_type = "Component"  # fallback

    return GraphNode(
        id=str(fm["id"]),
        type=node_type,
        name=str(fm.get("name", fm["id"])),
        status=str(fm.get("status", "active")),
        source=str(fm.get("source", "UNRESOLVED")),
        confidence=float(fm.get("confidence", 1.0)),
        tags=list(fm.get("tags") or []),
        aliases=list(fm.get("aliases") or []),
        first_seen=dict(fm.get("first_seen") or {}),
        last_verified=dict(fm.get("last_verified") or {}),
        raw_frontmatter=fm,
        content=body.strip(),
    )


def wikilinks_to_edges(node_id: str, content: str, 
                        provenance: str = "EXPLICIT") -> list["GraphEdge"]:
    """Convert [[wikilink]] occurrences in content to GraphEdge objects."""
    from .model import GraphEdge
    from .ontology import coerce_relation_type

    edges = []
    for target_id in extract_wikilinks(content):
        target_id = target_id.strip()
        if target_id and target_id != node_id:
            edges.append(GraphEdge(
                source=node_id,
                relation="RELATED_TO",
                target=target_id,
                provenance=provenance,
                confidence=1.0,
            ))
    return edges
