"""Wire a project's host to the kernel: merge the hookd entries into
`.claude/settings.json` (the same hooks the plugin's `hooks/hooks.json`
declares), without touching anything else the file holds. Two hosts get
their hooks this way even when Spec Master came as a plugin:

- qwen: the same entries in `.qwen/settings.json` (Qwen Code reads Claude's
  hook format, but loads a repository that carries an Agent Plugins
  manifest as skills and MCP only);
- kiro: `.kiro/hooks/spec-master.json` (a Kiro power cannot carry hooks).

Idempotent: previous Spec Master entries (any command running
`kernel/hookd.py`) are replaced, never duplicated. `mode` also records
`hooks_mode` in `.spec-master/policy.json` — the file the hooks read;
`set_mode` does only that, for projects that get the hooks from the plugin.
Entering audit mode records `audit_started_at` (kept if already set): the
start of the audit period `harness audit` measures.

An engine inside the project is referenced through the host's project
variable (`$CLAUDE_PROJECT_DIR`, `$QWEN_PROJECT_DIR`), so the settings can be
committed. Every command ends in `|| true`: a missing
engine or interpreter must never become a blocking hook error (exit 2).
Kiro blocks through exit code 2 itself, so its commands check that hookd
exists first instead (python3 also exits 2 when it cannot open a script).
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


HOSTS = ("claude", "qwen", "kiro")
SETTINGS = {"claude": os.path.join(".claude", "settings.json"), "qwen": os.path.join(".qwen", "settings.json")}
PROJECT_DIR_VARIABLE = {"claude": "$CLAUDE_PROJECT_DIR", "qwen": "$QWEN_PROJECT_DIR"}
KIRO_HOOKS = os.path.join(".kiro", "hooks", "spec-master.json")
KIRO_WRITES = "fs_write|write|str_replace|delete_file"
# Kiro trigger -> (matcher or None, hookd event, timeout seconds)
KIRO_EVENTS = {
    "PreToolUse": ("execute_bash|shell|" + KIRO_WRITES, "pre-tool-use", 10),
    "PostToolUse": (KIRO_WRITES, "post-tool-use", 30),
    "Stop": (None, "stop", 10),
    "SessionStart": (None, "session-start", 10),
}


def _hookd(engine: str, project: str | None) -> tuple[str, bool]:
    """hookd's path, relative (POSIX) when the engine is inside the project."""
    script = os.path.join(os.path.abspath(engine), "lib", "kernel", "hookd.py")
    try:
        relative = os.path.relpath(script, os.path.abspath(project)) if project else os.pardir
    except ValueError:  # another drive (Windows): keep the absolute path
        relative = os.pardir
    if relative.split(os.sep)[0] != os.pardir and not os.path.isabs(relative):
        return Path(relative).as_posix(), True
    return script, False


def hook_command(engine: str, event: str, project: str | None = None, host: str = "claude") -> str:
    script, inside = _hookd(engine, project)
    target = f'"{PROJECT_DIR_VARIABLE[host]}"/' + shlex.quote(script) if inside else shlex.quote(script)
    flag = "" if host == "claude" else f" --host {host}"
    return f"python3 {target} {event}{flag} || true"


def kiro_command(engine: str, event: str, project: str | None = None) -> str:
    target = shlex.quote(_hookd(engine, project)[0])  # Kiro runs hooks from the project root
    return f"test -f {target} && python3 {target} {event} --host kiro"


def kiro_hooks(engine: str, project: str | None = None) -> dict:
    hooks = []
    for trigger, (matcher, event, timeout) in KIRO_EVENTS.items():
        hook = {"name": f"spec-master {event}", "trigger": trigger}
        if matcher:
            hook["matcher"] = matcher
        hook["action"] = {"type": "command", "command": kiro_command(engine, event, project)}
        hook["timeout"] = timeout
        hooks.append(hook)
    return {"version": "v1", "hooks": hooks}


def hooks_block(engine: str, project: str | None = None, host: str = "claude") -> dict:
    block = {}
    for host_event, (matcher, event, timeout) in EVENTS.items():
        command = hook_command(engine, event, project, host)
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


def merge(settings: dict, engine: str, project: str | None = None, host: str = "claude") -> dict:
    merged = dict(settings)
    hooks = {event: _without_ours(entries) for event, entries in (settings.get("hooks") or {}).items()}
    for event, entries in hooks_block(engine, project, host).items():
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
                  dry_run: bool = False, host: str = "claude") -> dict:
    if host not in HOSTS:
        raise ValueError(f"host must be one of {', '.join(HOSTS)}, not {host!r}")
    project = os.path.abspath(project)
    engine = os.path.abspath(engine) if engine else str(ENGINE)
    if not os.path.isfile(os.path.join(engine, "lib", "kernel", "hookd.py")):
        raise ValueError(f"not a Spec Master engine (no lib/kernel/hookd.py): {engine}")
    if host == "kiro":  # the whole file is ours: rewrite it
        settings_path, events = os.path.join(project, KIRO_HOOKS), KIRO_EVENTS
        content = kiro_hooks(engine, project)
    else:
        settings_path, events = os.path.join(project, SETTINGS[host]), EVENTS
        current = {}
        if os.path.isfile(settings_path):
            with open(settings_path, "r", encoding="utf-8") as fh:
                current = json.load(fh)
            if not isinstance(current, dict):
                raise ValueError(f"{settings_path} is not a JSON object")
        content = merge(current, engine, project, host)
    policy_path, policy = _policy_with_mode(project, mode) if mode else (None, None)
    if not dry_run:
        state_mod.save(settings_path, content)
        _prepare(project)
        if policy is not None:
            state_mod.save(policy_path, policy)
    return {"host": host, "settings": settings_path, "events": sorted(events), "engine": engine,
            "hooks_mode": (policy or {}).get("hooks_mode"),
            "audit_started_at": (policy or {}).get("audit_started_at"), "dry_run": dry_run}
