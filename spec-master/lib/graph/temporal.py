"""Temporal metadata helpers for the Spec Master Knowledge Graph.

Nodes and edges can track when they were first seen, last verified,
and their valid time window (for historical edge tracking).
"""
from __future__ import annotations

from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_first_seen(commit: str | None = None,
                     phase: str | None = None) -> dict:
    entry: dict = {"timestamp": now_iso()}
    if commit:
        entry["commit"] = commit
    if phase:
        entry["phase"] = phase
    return entry


def make_last_verified(commit: str | None = None) -> dict:
    entry: dict = {"timestamp": now_iso()}
    if commit:
        entry["commit"] = commit
    return entry


def is_stale(last_verified: dict, max_age_days: int = 30) -> bool:
    """Return True if the node/edge hasn't been verified recently."""
    ts_str = last_verified.get("timestamp")
    if not ts_str:
        return True
    try:
        ts = datetime.fromisoformat(ts_str)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - ts).days
        return age > max_age_days
    except (ValueError, TypeError):
        return True


def temporal_edge(
    source: str,
    relation: str,
    target: str,
    valid_from: str,
    valid_to: str | None = None,
    **kwargs,
) -> dict:
    """Build a temporal edge dict for historical relationship tracking."""
    return {
        "source": source,
        "relation": relation,
        "target": target,
        "valid_from": valid_from,
        "valid_to": valid_to,
        **kwargs,
    }
