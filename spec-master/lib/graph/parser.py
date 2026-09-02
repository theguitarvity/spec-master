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

    return _parse_simple_yaml(fm_text), body


def _strip_scalar(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        value = value[1:-1]
    return value


def _parse_simple_yaml(fm_text: str) -> dict:
    """Minimal indent-based parser for the frontmatter subset this repo uses:
    scalar values, block lists (`- item`), and one level of nested mapping
    (e.g. `depth:` -> `role: L4` lines). Used only when PyYAML is absent.
    """
    lines = [line for line in fm_text.splitlines() if line.strip() != "" and not line.strip().startswith("#")]
    fm: dict = {}
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        indent = len(line) - len(line.lstrip(" "))
        if indent != 0 or ":" not in line or line.lstrip().startswith("-"):
            i += 1
            continue
        key, _, rest = line.partition(":")
        key = key.strip()
        rest = rest.strip()
        i += 1
        if rest:
            fm[key] = _strip_scalar(rest)
            continue

        # Look ahead for an indented block (list or nested mapping).
        block: list[str] = []
        while i < n:
            nxt = lines[i]
            nxt_indent = len(nxt) - len(nxt.lstrip(" "))
            if nxt_indent <= indent:
                break
            block.append(nxt)
            i += 1

        if not block:
            fm[key] = ""
        elif block[0].lstrip().startswith("- "):
            fm[key] = [_strip_scalar(entry.lstrip()[2:]) for entry in block]
        else:
            nested: dict = {}
            for entry in block:
                if ":" not in entry:
                    continue
                nkey, _, nval = entry.strip().partition(":")
                nested[nkey.strip()] = _strip_scalar(nval)
            fm[key] = nested
    return fm


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
