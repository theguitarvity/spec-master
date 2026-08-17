"""Safe parser for the structured `phase_result` block a guarded-mode
phase emits as plain transcript text (docs/spec-master/../../specs/002-
guarded-noop-phase-validation/spec.md §6).

Never evaluates or executes transcript content: only `json.loads` on
syntactically balanced `{...}` spans. Invalid JSON, objects missing the
`phase_result` key, or an unrecognized value are ignored, not raised.
"""
from __future__ import annotations

import json

ACCEPTED_VALUES = frozenset((
    "artifact_updated",
    "no_changes_required",
    "user_decision_required",
    "failed",
))


def _balanced_object_spans(text: str) -> list[str]:
    spans = []
    depth = 0
    start = None
    for index, char in enumerate(text):
        if char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    spans.append(text[start:index + 1])
                    start = None
    return spans


def parse_last_phase_result(text: str) -> dict | None:
    last_valid = None
    for span in _balanced_object_spans(text):
        try:
            candidate = json.loads(span)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(candidate, dict):
            continue
        if candidate.get("phase_result") not in ACCEPTED_VALUES:
            continue
        last_valid = candidate
    return last_valid
