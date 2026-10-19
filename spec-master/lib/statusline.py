#!/usr/bin/env python3
"""Status line for Claude Code (`statusLine` setting): one line from the token ledger.

Reads the host's JSON on stdin (session_id, transcript_path, workspace, context_window),
ingests the session transcript incrementally into `.spec-master/metrics/tokens.jsonl`,
and prints `feature phase tier | tokens | cost | cache hit | context`. What is unknown
is omitted, never invented. Always exits 0 and never prints a traceback.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _project_root(payload: dict) -> str | None:
    workspace = payload.get("workspace") if isinstance(payload.get("workspace"), dict) else {}
    start = workspace.get("project_dir") or workspace.get("current_dir") or payload.get("cwd") or os.getcwd()
    here = os.path.abspath(str(start))
    while True:
        if os.path.isdir(os.path.join(here, ".spec-master")):
            return here
        parent = os.path.dirname(here)
        if parent == here:
            return None
        here = parent


def _active(root: str) -> tuple[str | None, str | None, str | None]:
    """(feature, phase, tier) of the first feature with a RUNNING phase."""
    try:
        with open(os.path.join(root, ".spec-master", "state.json"), "r", encoding="utf-8") as fh:
            features = json.load(fh).get("features") or []
    except (OSError, ValueError, AttributeError):
        return None, None, None
    for feature in features:
        running = [name for name, status in (feature.get("phases") or {}).items() if status == "RUNNING"]
        if running:
            return feature.get("id"), running[0], (feature.get("risk") or {}).get("tier")
    return None, None, None


def _human(count: int) -> str:
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    if count >= 1000:
        return f"{count / 1000:.1f}k"
    return str(count)


def render(payload: dict) -> str:
    root = _project_root(payload)
    parts: list[str] = []
    session = payload.get("session_id") if isinstance(payload.get("session_id"), str) else None
    transcript = payload.get("transcript_path") if isinstance(payload.get("transcript_path"), str) else None
    totals = None
    if root:
        import ledger
        if transcript:
            ledger.ingest(root, transcripts=[transcript])
        if session:
            totals = ledger.summary(root, session_id=session)["totals"]
        label = " ".join(x for x in _active(root) if x)
        if label:
            parts.append(label)
    if totals and totals["total_tokens"]:
        parts.append(f"{_human(totals['total_tokens'])} tok")
        if totals["cost_usd"] is not None:
            parts.append(f"~${totals['cost_usd']:.2f}")
        if totals["cache_hit_ratio"]:
            parts.append(f"cache {round(totals['cache_hit_ratio'] * 100)}%")
    window = payload.get("context_window") if isinstance(payload.get("context_window"), dict) else {}
    used = window.get("used_percentage")
    if isinstance(used, (int, float)) and not isinstance(used, bool):
        parts.append(f"ctx {round(used)}%")
    return " | ".join(parts)


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        line = render(payload if isinstance(payload, dict) else {})
    except Exception:  # a status line must never break the host
        line = ""
    print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
