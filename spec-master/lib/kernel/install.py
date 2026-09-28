"""Wire a project's host to the kernel: merge the hookd entries into
`.claude/settings.json` (the same hooks the plugin's `hooks/hooks.json`
declares), without touching anything else the file holds.

Idempotent: previous Spec Master entries (any command running
`kernel/hookd.py`) are replaced, never duplicated. `mode` also records
`hooks_mode` in `.spec-master/policy.json` — the file the hooks read;
`set_mode` does only that, for projects that get the hooks from the plugin.
Entering audit mode records `audit_started_at` (kept if already set): the
start of the audit period `harness audit` measures.

An engine inside the project is referenced through `$CLAUDE_PROJECT_DIR`, so
the settings can be committed. Every command ends in `|| true`: a missing
engine or interpreter must never become a blocking hook error (exit 2).
"""
from __future__ import annotations

import datetime as dt
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


def hook_command(engine: str, event: str, project: str | None = None) -> str:
    script = os.path.join(os.path.abspath(engine), "lib", "kernel", "hookd.py")
    try:
        relative = os.path.relpath(script, os.path.abspath(project)) if project else os.pardir
    except ValueError:  # another drive (Windows): keep the absolute path
        relative = os.pardir
    if relative.split(os.sep)[0] != os.pardir and not os.path.isabs(relative):
        target = '"$CLAUDE_PROJECT_DIR"/' + shlex.quote(Path(relative).as_posix())
    else:
        target = shlex.quote(script)
    return f"python3 {target} {event} || true"


def hooks_block(engine: str, project: str | None = None) -> dict:
    block = {}
    for host_event, (matcher, event, timeout) in EVENTS.items():
        command = hook_command(engine, event, project)
        entry = {"hooks": [{"type": "command", "command": command, "timeout": timeout}]}
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


def merge(settings: dict, engine: str, project: str | None = None) -> dict:
    merged = dict(settings)
    hooks = {event: _without_ours(entries) for event, entries in (settings.get("hooks") or {}).items()}
    for event, entries in hooks_block(engine, project).items():
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
    policy = {**policy, "hooks_mode": mode}
    if mode == "audit" and not policy.get("audit_started_at"):
        policy["audit_started_at"] = dt.datetime.now(dt.timezone.utc).date().isoformat()
    return policy_path, policy


def set_mode(project: str, mode: str, *, dry_run: bool = False) -> dict:
    """Record `hooks_mode` without touching `.claude/settings.json`."""
    project = os.path.abspath(project)
    policy_path, policy = _policy_with_mode(project, mode)
    if not dry_run:
        _prepare(project)
        state_mod.save(policy_path, policy)
    return {"policy": policy_path, "hooks_mode": mode, "audit_started_at": policy.get("audit_started_at"),
            "dry_run": dry_run}


def _prepare(project: str) -> None:
    """hookd logs only where `.spec-master/` exists; its log stays out of git."""
    os.makedirs(os.path.join(project, ".spec-master", "hooks"), exist_ok=True)
    state_mod.ensure_gitignore(os.path.join(project, ".spec-master"))


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
    merged = merge(current, engine, project)
    policy_path, policy = _policy_with_mode(project, mode) if mode else (None, None)
    if not dry_run:
        state_mod.save(settings_path, merged)
        _prepare(project)
        if policy is not None:
            state_mod.save(policy_path, policy)
    return {"settings": settings_path, "events": sorted(EVENTS), "engine": engine,
            "hooks_mode": (policy or {}).get("hooks_mode"),
            "audit_started_at": (policy or {}).get("audit_started_at"), "dry_run": dry_run}
