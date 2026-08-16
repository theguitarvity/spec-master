"""Structural (heading-level) diff between constitutions (CLAUDE.md section 16).

Classifies each heading found in the existing vs. proposed constitution as
UNCHANGED / ADDITION / MODIFICATION / CONFLICT / REMOVAL_CANDIDATE.

This is a structural signal only (heading presence + body text equality) —
semantic judgement about whether a MODIFICATION is actually a destructive
CONFLICT is left to the agent; here, MODIFICATION vs CONFLICT is decided by
a simple heuristic: a modification under a heading tagged as normative
("MUST", "SHALL", "NUNCA", "NEVER") is reported as CONFLICT so a human/agent
double-checks it before overwriting, everything else is MODIFICATION.
"""
from __future__ import annotations

import os
import re

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)
_NORMATIVE_MARKERS = ("MUST", "SHALL", "NEVER", "NUNCA", "SEMPRE", "OBRIGAT")


def _parse_sections(text: str) -> dict:
    """Return {heading_text: body_text} for top-level matches, in document order."""
    matches = list(_HEADING_RE.finditer(text))
    sections = {}
    for i, m in enumerate(matches):
        heading = m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        sections[heading] = body
    return sections


def _is_normative(body: str) -> bool:
    upper = body.upper()
    return any(marker in upper for marker in _NORMATIVE_MARKERS)


def diff(existing_text: str, proposed_text: str) -> list[dict]:
    existing = _parse_sections(existing_text)
    proposed = _parse_sections(proposed_text)

    results = []
    for heading, body in proposed.items():
        if heading not in existing:
            results.append({"heading": heading, "classification": "ADDITION"})
        elif existing[heading].strip() == body.strip():
            results.append({"heading": heading, "classification": "UNCHANGED"})
        else:
            classification = "CONFLICT" if _is_normative(existing[heading]) else "MODIFICATION"
            results.append({"heading": heading, "classification": classification})

    for heading in existing:
        if heading not in proposed:
            results.append({"heading": heading, "classification": "REMOVAL_CANDIDATE"})

    return results


def diff_files(existing_path: str, proposed_path: str) -> list[dict]:
    existing_text = ""
    if existing_path and os.path.exists(existing_path):
        with open(existing_path, "r", encoding="utf-8") as fh:
            existing_text = fh.read()
    with open(proposed_path, "r", encoding="utf-8") as fh:
        proposed_text = fh.read()
    return diff(existing_text, proposed_text)
