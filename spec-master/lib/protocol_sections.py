"""PROTOCOL.md sections on demand (roadmap P2).

The full-cycle entrypoint no longer asks the agent to read the whole protocol:
it reads the router (`cards/full-cycle.md`) and, for the step it is on, one
section, printed by `protocol show --section "<heading>"`. Sections are cut
from the real PROTOCOL.md by markdown heading (fenced code is skipped), so
there is no second copy of the text to drift.

Pure stdlib.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PROTOCOL_PATH = Path(__file__).resolve().parent.parent / "PROTOCOL.md"


@dataclass
class Section:
    title: str
    level: int
    start: int  # index of the heading line
    own_end: int  # index of the next heading of any level (exclusive)
    tree_end: int  # index of the next heading of the same or a higher level (exclusive)
    bytes: int = 0  # size of the section's own text


def parse(text: str) -> list[Section]:
    lines = text.splitlines()
    heads: list[tuple[int, int, str]] = []
    fenced = False
    for index, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced or not line.startswith("#"):
            continue
        level = len(line) - len(line.lstrip("#"))
        if 1 <= level <= 6 and line[level:level + 1] == " ":
            heads.append((index, level, line[level:].strip()))
    sections = []
    for pos, (index, level, title) in enumerate(heads):
        own_end = heads[pos + 1][0] if pos + 1 < len(heads) else len(lines)
        tree_end = len(lines)
        for later_index, later_level, _ in heads[pos + 1:]:
            if later_level <= level:
                tree_end = later_index
                break
        size = len(("\n".join(lines[index:own_end]) + "\n").encode("utf-8"))
        sections.append(Section(title, level, index, own_end, tree_end, size))
    return sections


def find(sections: list[Section], query: str) -> Section:
    """Exact title, else unique title prefix, else unique substring (case-insensitive)."""
    wanted = (query or "").strip().lower()
    if not wanted:
        raise ValueError("a section name is required")
    for matcher in (lambda t: t == wanted, lambda t: t.startswith(wanted), lambda t: wanted in t):
        hits = [s for s in sections if matcher(s.title.lower())]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            names = "; ".join(s.title for s in hits)
            raise ValueError(f"section '{query}' is ambiguous: {names}")
    raise ValueError(f"no section matches '{query}' (list them with `protocol sections`)")


def render(text: str, section: Section, tree: bool = False) -> str:
    lines = text.splitlines()
    end = section.tree_end if tree else section.own_end
    return "\n".join(lines[section.start:end]).rstrip("\n") + "\n"


def listing(sections: list[Section]) -> list[dict]:
    return [{"title": s.title, "level": s.level, "bytes": s.bytes} for s in sections]
