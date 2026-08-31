"""Graph mutation event log for the Spec Master Knowledge Graph.

Appends JSONL events to .spec-master/knowledge/graph-events.jsonl.
Provides an audit trail of all graph mutations without requiring a database.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

# Event types
NODE_CREATED = "NODE_CREATED"
NODE_UPDATED = "NODE_UPDATED"
NODE_DEPRECATED = "NODE_DEPRECATED"
EDGE_CREATED = "EDGE_CREATED"
EDGE_UPDATED = "EDGE_UPDATED"
EDGE_REMOVED = "EDGE_REMOVED"
EVIDENCE_ADDED = "EVIDENCE_ADDED"
CONFIDENCE_CHANGED = "ARCHITECTURE_DRIFT_DETECTED"
ARCHITECTURE_DRIFT_DETECTED = "ARCHITECTURE_DRIFT_DETECTED"
STALE_NODE_DETECTED = "STALE_NODE_DETECTED"

CONFIDENCE_CHANGED = "CONFIDENCE_CHANGED" # Fix previous line override

ALL_EVENT_TYPES = {
    NODE_CREATED, NODE_UPDATED, NODE_DEPRECATED,
    EDGE_CREATED, EDGE_UPDATED, EDGE_REMOVED,
    EVIDENCE_ADDED, CONFIDENCE_CHANGED,
    ARCHITECTURE_DRIFT_DETECTED, STALE_NODE_DETECTED,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_event(events_path: str | Path, event_type: str,
                 payload: dict) -> dict:
    """Append a graph event to the JSONL event log."""
    if event_type not in ALL_EVENT_TYPES:
        raise ValueError(f"Unknown event type: {event_type}")

    event = {
        "event": event_type,
        "timestamp": _now_iso(),
        **payload,
    }
    path = Path(events_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def read_events(events_path: str | Path) -> list[dict]:
    """Read all events from the JSONL log."""
    path = Path(events_path)
    if not path.exists():
        return []
    events = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return events
