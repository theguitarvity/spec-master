"""Attribution event stream: `.spec-master/events.jsonl` (docs/contracts/token-ledger-v1.md §1).

Append-only JSONL, one `spec-master.event/v1` object per line. Writers are the
Claude Code subagent hooks (via kernel/hookd.py) and `state transition`;
the token ledger reads the stream to attribute usage to feature / phase /
agent. Import-light (stdlib only): the hook daemon imports it on subagent
events. Nothing here ever raises into its caller.
"""
from __future__ import annotations

import datetime as dt
import json
import os

SCHEMA = "spec-master.event/v1"
RELPATH = os.path.join(".spec-master", "events.jsonl")
FINISHED = ("PASSED", "FAILED", "BLOCKED", "SKIPPED")


def events_path(root: str) -> str:
    return os.path.join(root, RELPATH)


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_ts(value) -> dt.datetime | None:
    """ISO-8601 -> aware UTC datetime (naive = UTC); None when unparseable."""
    if not isinstance(value, str) or not value:
        return None
    try:
        moment = dt.datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=dt.timezone.utc)


def append(root: str, type: str, *, ts: str | None = None, session_id=None, feature_id=None, phase=None,
           **extra) -> bool:
    """Append one event; False (and no file) outside a Spec Master project or on I/O errors."""
    directory = os.path.join(root, ".spec-master")
    if not os.path.isdir(directory):
        return False
    line = {"schema": SCHEMA, "ts": ts or _now(), "type": type, "session_id": session_id,
            "feature_id": feature_id, "phase": phase, **extra}
    try:
        with open(events_path(root), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(line, ensure_ascii=False, separators=(",", ":")) + "\n")
        return True
    except OSError:
        return False


def read(root: str) -> list[dict]:
    """Every well-formed event, in file order (corrupt lines are skipped)."""
    found = []
    try:
        with open(events_path(root), "r", encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                try:
                    obj = json.loads(raw)
                except ValueError:
                    continue
                if isinstance(obj, dict) and isinstance(obj.get("type"), str):
                    found.append(obj)
    except OSError:
        pass
    return found


def on_phase(root: str, feature_id: str, phase: str, status: str) -> bool:
    if status == "RUNNING":
        return append(root, "phase.started", feature_id=feature_id, phase=phase, status=status)
    if status in FINISHED:
        return append(root, "phase.finished", feature_id=feature_id, phase=phase, status=status)
    return False


def active_window(evs: list[dict], session_id, ts) -> tuple[str | None, str | None]:
    """(feature_id, phase) of the latest phase window open at `ts` for the session.

    Phase events with a null session (written by the CLI) match every session.
    Not attributable -> (None, None); never guessed.
    """
    moment = parse_ts(ts)
    if moment is None:
        return None, None
    last: dict[tuple, tuple[dt.datetime, str]] = {}
    for event in evs:
        kind = event.get("type")
        if kind not in ("phase.started", "phase.finished"):
            continue
        if event.get("session_id") not in (None, session_id):
            continue
        when = parse_ts(event.get("ts"))
        if when is None or when > moment:
            continue
        key = (event.get("feature_id"), event.get("phase"))
        if key not in last or when >= last[key][0]:
            last[key] = (when, kind)
    open_windows = [(when, key) for key, (when, kind) in last.items() if kind == "phase.started"]
    if not open_windows:
        return None, None
    return max(open_windows, key=lambda item: item[0])[1]


def on_agent(root: str, kind: str, payload: dict) -> bool:
    """`agent.started` (kind "start") / `agent.finished` ("stop") from a hook payload."""
    agent_id = payload.get("agent_id")
    if not isinstance(agent_id, str) or not agent_id:
        return False
    session = payload.get("session_id") if isinstance(payload.get("session_id"), str) else None
    path = payload.get("agent_transcript_path")  # the main session's transcript_path is not the agent's
    feature_id, phase = active_window(read(root), session, _now())
    worktree = payload.get("worktree") if isinstance(payload.get("worktree"), str) else None
    return append(root, "agent.started" if kind == "start" else "agent.finished", session_id=session,
                  feature_id=feature_id, phase=phase, agent_id=agent_id,
                  agent_type=payload.get("agent_type") if isinstance(payload.get("agent_type"), str) else None,
                  worktree=worktree, transcript_path=path if isinstance(path, str) else None)
