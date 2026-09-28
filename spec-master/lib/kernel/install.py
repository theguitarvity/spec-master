"""Wire a project's host to the kernel: merge the hookd entries into
`.claude/settings.json` (the same hooks the plugin's `hooks/hooks.json`
declares), without touching anything else the file holds.

Idempotent: previous Spec Master entries (any command running
`kernel/hookd.py`) are replaced, never duplicated. `mode` also records
`hooks_mode` in `.spec-master/policy.json` — the file the hooks read;
`set_mode` does only that, for projects that get the hooks from the plugin.
"""
from __future__ import annotations

import json
import os
import shlex
from pathlib import Path

import state as state_mod

ENGINE = Path(__file__).resolve().parents[2]
MARKER = "kernel/hookd.py"
WRITE_MATCHER = "Edit|Write|MultiEdit|NotebookEdit"

# host event -> (matcher or None, hookd event, timeout seconds)
EVENTS = {
    "PreToolUse": ("Bash|" + WRITE_MATCHER, "pre-tool-use", 10),
    "PostToolUse": (WRITE_MATCHER, "post-tool-use", 30),
    "Stop": (None, "stop", 10),
    "SessionStart": ("startup|resume|compact", "session-start", 10),
}


def hook_command(engine: str, event: str) -> str:
    script = os.path.join(engine, "lib", "kernel", "hookd.py")
    return f"python3 {shlex.quote(script)} {event}"


def hooks_block(engine: str) -> dict:
    block = {}
    for host_event, (matcher, event, timeout) in EVENTS.items():
        entry = {"hooks": [{"type": "command", "command": hook_command(engine, event), "timeout": timeout}]}
        if matcher:
            entry = {"matcher": matcher, **entry}
        block[host_event] = [entry]
    return block


def _without_ours(entries: list) -> list:
    kept = []
    for entry in entries or []:
        hooks = [h for h in (entry.get("hooks") or []) if MARKER not in str(h.get("command", ""))]
        if hooks:
            kept.append({**entry, "hooks": hooks})
    return kept


def merge(settings: dict, engine: str) -> dict:
    merged = dict(settings)
    hooks = {event: _without_ours(entries) for event, entries in (settings.get("hooks") or {}).items()}
    for event, entries in hooks_block(engine).items():
        hooks[event] = hooks.get(event, []) + entries
    merged["hooks"] = {event: entries for event, entries in hooks.items() if entries}
    return merged


def _policy_with_mode(project: str, mode: str) -> tuple[str, dict]:
    if mode not in ("audit", "block"):
        raise ValueError(f"hooks mode must be audit or block, not {mode!r}")
    policy_path = os.path.join(project, ".spec-master", "policy.json")
    policy = {}
    if os.path.isfile(policy_path):
        with open(policy_path, "r", encoding="utf-8") as fh:
            policy = json.load(fh)
        if not isinstance(policy, dict):
            raise ValueError(f"{policy_path} is not a JSON object")
    return policy_path, {**policy, "hooks_mode": mode}


def set_mode(project: str, mode: str, *, dry_run: bool = False) -> dict:
    """Record `hooks_mode` without touching `.claude/settings.json`."""
    project = os.path.abspath(project)
    policy_path, policy = _policy_with_mode(project, mode)
    if not dry_run:
        os.makedirs(os.path.join(project, ".spec-master", "hooks"), exist_ok=True)
        state_mod.save(policy_path, policy)
    return {"policy": policy_path, "hooks_mode": mode, "dry_run": dry_run}


def install_hooks(project: str, *, engine: str | None = None, mode: str | None = None,
                  dry_run: bool = False) -> dict:
    project = os.path.abspath(project)
    engine = os.path.abspath(engine) if engine else str(ENGINE)
    if not os.path.isfile(os.path.join(engine, "lib", "kernel", "hookd.py")):
        raise ValueError(f"not a Spec Master engine (no lib/kernel/hookd.py): {engine}")
    settings_path = os.path.join(project, ".claude", "settings.json")
    current = {}
    if os.path.isfile(settings_path):
        with open(settings_path, "r", encoding="utf-8") as fh:
            current = json.load(fh)
        if not isinstance(current, dict):
            raise ValueError(f"{settings_path} is not a JSON object")
    merged = merge(current, engine)
    policy_path, policy = _policy_with_mode(project, mode) if mode else (None, None)
    if not dry_run:
        state_mod.save(settings_path, merged)
        # hookd logs its decisions only where `.spec-master/` exists.
        os.makedirs(os.path.join(project, ".spec-master", "hooks"), exist_ok=True)
        if policy is not None:
            state_mod.save(policy_path, policy)
    return {"settings": settings_path, "events": sorted(EVENTS), "engine": engine,
            "hooks_mode": (policy or {}).get("hooks_mode"), "dry_run": dry_run}
