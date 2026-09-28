#!/usr/bin/env python3
"""Hook daemon: the host calls this on its lifecycle events and it answers
with the kernel's decisions (Claude Code hook protocol; stdin JSON in, JSON
or exit code out).

    python3 hookd.py pre-tool-use | post-tool-use | stop | subagent-stop | session-start

- pre-tool-use  — `Bash` commands through the argv policy; file writes against
                  the core-owned files, the running change's envelope and,
                  in the legacy flow, the RUNNING phase's write allowlist.
- post-tool-use — tells the agent when the diff has outgrown its patch lane.
- stop          — a patch change still RUNNING must go through `step end`
                  (at most 2 re-entries, then the change is PAUSED).
- session-start — re-injects the current card after a restart or compaction.

`.spec-master/policy.json` `hooks_mode` picks `audit` (default: decide, log
and never interfere) or `block` (enforce). Every decision is appended to
`.spec-master/hooks/decisions.jsonl` so the audit period measures the false
positive rate before blocking is switched on — only in projects that already
have a `.spec-master/` directory, so a plugin enabled everywhere never litters
other repositories. Imports stay light: this runs on every tool call.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import state as state_mod  # noqa: E402
from kernel import changes, paths, policy  # noqa: E402

DECISIONS_RELPATH = os.path.join(".spec-master", "hooks", "decisions.jsonl")
WRITE_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
MAX_STOP_REENTRIES = 2
PATCH_LIMITS = {"files": 3, "modules": 1, "loc": 50}
PRE_IMPLEMENT_PHASES = ("specify", "clarify", "plan", "tasks", "analyze")


def project_root(payload: dict) -> str:
    return os.path.abspath(os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd())


def _read_json(path: str):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def mode(root: str) -> str:
    data = _read_json(os.path.join(root, ".spec-master", "policy.json")) or {}
    return data.get("hooks_mode") if data.get("hooks_mode") in ("audit", "block") else "audit"


def log_decision(root: str, entry: dict) -> None:
    if not os.path.isdir(os.path.join(root, ".spec-master")):
        return  # not a Spec Master project: decide, but leave no trace
    state_mod.ensure_gitignore(os.path.join(root, ".spec-master"))
    path = os.path.join(root, DECISIONS_RELPATH)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
    except OSError:
        pass  # logging never breaks the host


def _running_phase(root: str) -> tuple[dict, str] | None:
    """(feature, phase) when exactly one legacy feature phase is RUNNING."""
    state = _read_json(os.path.join(root, ".spec-master", "state.json"))
    if not isinstance(state, dict):
        return None
    running = [(f, phase) for f in state.get("features") or [] if isinstance(f, dict)
               for phase, status in (f.get("phases") or {}).items() if status == "RUNNING"]
    return running[0] if len(running) == 1 else None


def _phase_write(root: str, target: str) -> dict | None:
    found = _running_phase(root)
    if not found:
        return None
    feature, phase = found
    if phase not in PRE_IMPLEMENT_PHASES:
        return None
    import phase_contracts  # noqa: E402  (only needed on this path)
    relative = paths.norm(os.path.relpath(os.path.realpath(target), os.path.realpath(root))
                          if os.path.isabs(target) else target)
    try:
        forbidden = phase_contracts.forbidden_writes([relative], phase, feature.get("spec_directory"))
    except ValueError:
        return None
    if forbidden:
        return {"decision": policy.DENY,
                "reason": f"{relative} is outside what `{phase}` may write for feature {feature.get('id')} "
                          f"— implementation starts only after analyze PASSED"}
    return None


def _relative(root: str, target: str) -> str:
    if os.path.isabs(target):
        return paths.norm(os.path.relpath(os.path.realpath(target), os.path.realpath(root)))
    return paths.norm(target)


def pre_tool_use(root: str, payload: dict, enforce: bool) -> dict:
    tool = payload.get("tool_name") or ""
    tool_input = payload.get("tool_input") or {}
    if tool == "Bash":
        verdict = policy.decide_command(tool_input.get("command") or "", root=root)
        return {**verdict, "target": (tool_input.get("command") or "")[:200]}
    if tool in WRITE_TOOLS:
        target = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
        record = changes.active(root)
        running = bool(record and record.get("status") == "RUNNING")
        envelope = None
        if running and not paths.is_test_path(_relative(root, target)):  # tests are always part of a change
            envelope = list(record.get("envelope") or []) + [changes.note_relpath(record["id"])]
        verdict = policy.decide_write(target, root=root, envelope=envelope)
        if verdict["decision"] == policy.ALLOW and not running:
            verdict = _phase_write(root, target) or verdict
        return {**verdict, "target": target}
    return {"decision": policy.ALLOW, "reason": "tool not governed", "target": ""}


def post_tool_use(root: str, payload: dict, enforce: bool) -> dict:
    if (payload.get("tool_name") or "") not in WRITE_TOOLS:
        return {"decision": policy.ALLOW, "reason": "not a write"}
    record = changes.active(root)
    if not record or record.get("status") != "RUNNING" or record.get("lane") != "patch":
        return {"decision": policy.ALLOW, "reason": "no running patch change"}
    changed = [p for p in changes.changed_since(root, record.get("base") or {}) if not paths.is_harness(p)]
    production = paths.production_files(changed)
    modules = {paths.module_of(p) for p in production}
    loc = changes.diff_loc(root, record.get("base") or {}, production)
    over = []
    if len(production) > PATCH_LIMITS["files"]:
        over.append(f"{len(production)} production files")
    if len(modules) > PATCH_LIMITS["modules"]:
        over.append(f"{len(modules)} modules")
    if loc > PATCH_LIMITS["loc"]:
        over.append(f"{loc} changed lines")
    if not over:
        return {"decision": policy.ALLOW, "reason": "within the patch envelope"}
    return {"decision": "escalate", "reason": "this change no longer fits the patch lane (" + ", ".join(over) +
            "). Run `python3 spec-master/lib/cli.py step end --path .` — it escalates the change — "
            "or undo the extra scope."}


def stop(root: str, payload: dict, enforce: bool) -> dict:
    """In audit mode this only reports what it would do: the record is
    touched (re-entries, PAUSED) only when the hook actually enforces."""
    record = changes.active(root)
    if not record or record.get("status") != "RUNNING":
        return {"decision": policy.ALLOW, "reason": "no running change"}
    if payload.get("stop_hook_active") or record.get("stop_reentries", 0) >= MAX_STOP_REENTRIES:
        if enforce:
            record["status"] = "PAUSED"
            record["paused"] = {"at": changes.now(), "reason": "stopped without `step end`"}
            changes.save(root, record)
        return {"decision": policy.ALLOW, "reason": f"change {record['id']} PAUSED (stopped before verification)"}
    if enforce:
        record["stop_reentries"] = record.get("stop_reentries", 0) + 1
        changes.save(root, record)
    return {"decision": "block", "reason": f"Change {record['id']} is still RUNNING: run "
            "`python3 spec-master/lib/cli.py step end --path .` and act on its result, or "
            "`step pause --path .` to stop here on purpose."}


def session_start(root: str, payload: dict, enforce: bool) -> dict:
    record = changes.active(root)
    if record and record.get("status") == "RUNNING":
        from kernel import step  # noqa: E402
        card = step.next_step(root)["card"]
        return {"decision": policy.ALLOW, "reason": "resume the running change",
                "context": f"[Spec Master] Change {record['id']} is RUNNING (lane patch). Current card:\n\n{card}"}
    found = _running_phase(root)
    if found:
        feature, phase = found
        return {"decision": policy.ALLOW, "reason": "resume the legacy flow",
                "context": f"[Spec Master] Feature {feature.get('id')} has `{phase}` RUNNING. Resume with "
                           "PROTOCOL.md Step 0 (`state show --summary`)."}
    return {"decision": policy.ALLOW, "reason": "nothing to resume"}


HANDLERS = {
    "pre-tool-use": pre_tool_use,
    "post-tool-use": post_tool_use,
    "stop": stop,
    "subagent-stop": lambda root, payload, enforce: {"decision": policy.ALLOW,
                                                     "reason": "subagents are not governed yet"},
    "session-start": session_start,
}


def respond(event: str, verdict: dict, enforce: bool) -> tuple[int, str]:
    """(exit code, stdout) in the host's hook protocol."""
    decision, reason = verdict["decision"], verdict["reason"]
    if event == "session-start" and verdict.get("context"):
        return 0, json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                                     "additionalContext": verdict["context"]}})
    if not enforce or decision == policy.ALLOW:
        return 0, ""
    if event == "pre-tool-use" and decision in (policy.DENY, policy.ASK):
        return 0, json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                                     "permissionDecision": decision,
                                                     "permissionDecisionReason": f"[Spec Master] {reason}"}})
    if event in ("post-tool-use", "stop") and decision in ("block", "escalate"):
        return 0, json.dumps({"decision": "block", "reason": f"[Spec Master] {reason}"})
    return 0, ""


def main(argv: list[str] | None = None, stdin=None) -> int:
    started = time.perf_counter()
    argv = sys.argv[1:] if argv is None else argv
    event = argv[0] if argv else ""
    handler = HANDLERS.get(event)
    if handler is None:
        print(f"unknown hook event: {event!r} (known: {', '.join(HANDLERS)})", file=sys.stderr)
        return 1
    try:
        payload = json.load(stdin or sys.stdin)
    except ValueError:
        payload = {}
    payload = payload if isinstance(payload, dict) else {}
    root = project_root(payload)
    current_mode = mode(root)
    enforce = current_mode == "block"
    try:
        verdict = handler(root, payload, enforce)
    except Exception as exc:  # noqa: BLE001 - a hook failure must never break the host
        verdict = {"decision": policy.ALLOW, "reason": f"hookd error: {type(exc).__name__}: {exc}"}
    code, out = respond(event, verdict, enforce)
    log_decision(root, {
        "at": changes.now(), "event": event, "tool": (payload or {}).get("tool_name"),
        "target": verdict.get("target", ""), "decision": verdict["decision"], "reason": verdict["reason"],
        "mode": current_mode, "enforced": bool(out) and verdict["decision"] != policy.ALLOW,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
    })
    if out:
        print(out)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
