"""`step next|begin|end|widen|pause`: the lane flow as a transactional API.

The agent does not keep the workflow in its head: it asks the kernel for the
next step and gets a small card back (never a copy of files it can read),
declares what it will touch, and closes the step through `step end`, which
only promotes on evidence (verify.py). The same functions back the CLI, the
hooks and a self-hosted runner.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from kernel import changes, lanes, verify

CARDS_DIR = Path(__file__).resolve().parents[2] / "cards"


class _Blank(dict):
    def __missing__(self, key):
        return ""


def render(name: str, **values) -> str:
    text = (CARDS_DIR / f"{name}.md").read_text(encoding="utf-8")
    return text.format_map(_Blank(values)).rstrip() + "\n"


def _implement_card(record: dict) -> str:
    bugfix = record.get("bugfix") or {}
    block = render("patch-bugfix", regression_test=bugfix.get("test", ""),
                   test_command=bugfix.get("command", "")) if record.get("kind") == "bugfix" else ""
    return render("patch-implement", change_id=record["id"], intent=record["intent"],
                  envelope=", ".join(record["envelope"]) or "(none)",
                  note_path=changes.note_relpath(record["id"]), bugfix_block=block)


def next_step(root: str) -> dict:
    record = changes.active(root)
    if record is None or record.get("status") != "RUNNING":
        return {"step": "triage", "change": None, "card": render("router")}
    return {"step": record["step"], "change": record["id"], "lane": record["lane"], "card": _implement_card(record)}


def _normalize_paths(paths) -> list[str]:
    return sorted({lanes._norm(p) for p in paths or () if p and lanes._norm(p)})


def begin(root: str, *, intent: str, paths, lane: str = "patch", kind: str = "change", confirmed=(), denied=(),
          unresolved: int = 0, regression_test: str | None = None, test_command: str | None = None,
          runner=subprocess.run, triage_result: dict | None = None) -> dict:
    """Open a patch change. Standard and critical changes are sent to the full
    cycle (the legacy protocol) instead of being opened here."""
    root = os.path.abspath(root)
    if not (intent or "").strip():
        raise changes.ChangeError("--intent is required (the user's request, verbatim)")
    if lane not in lanes.LANES:
        raise changes.ChangeError(f"unknown lane: {lane}")
    running = changes.active(root)
    if running and running.get("status") == "RUNNING":
        raise changes.ChangeError(f"change {running['id']} is still running — end, pause or escalate it first")
    if kind == "bugfix" and not (regression_test and test_command):
        raise changes.ChangeError("a bugfix needs --regression-test and --test-command")
    paths = _normalize_paths(paths)
    result = triage_result or lanes.triage(root, intent=intent, paths=paths, confirmed=confirmed,
                                           denied=denied, unresolved=unresolved, requested=lane)
    if result["questions"]:
        return {"status": "QUESTIONS", "lane": result["lane"], "questions": result["questions"],
                "next": "ask the questions in one batch, then re-run with --confirm/--deny"}
    if result["lane"] != "patch":
        return {"status": "FULL_CYCLE", "lane": result["lane"], "reasons": result["reasons"],
                "next": "run the full cycle: /spec-master <context file> (PROTOCOL.md)"}
    if not changes.is_git_repo(root, runner=runner):
        return {"status": "FULL_CYCLE", "lane": "standard",
                "reasons": {"standard": [{"signal": "no_git", "detail": "the patch lane needs git to see the diff"}]},
                "next": "run the full cycle: /spec-master <context file> (PROTOCOL.md)"}

    os.makedirs(changes.changes_dir(root), exist_ok=True)
    change_id = changes.new_id(root, intent)
    dirty = {p: changes.file_digest(root, p) for p in changes.dirty_paths(root, runner=runner)}
    record = {
        "id": change_id,
        "lane": "patch",
        "kind": kind,
        "intent": intent.strip(),
        "status": "RUNNING",
        "step": "implement",
        "envelope": paths,
        "confirmed": sorted(confirmed),
        "denied": sorted(denied),
        "base": {"commit": changes.head(root, runner=runner), "dirty": dirty},
        "triage": {"lane": result["lane"], "signals": result["signals"]},
        "created_at": changes.now(),
        "attempts": [],
        "stop_reentries": 0,
    }
    if kind == "bugfix":
        record["bugfix"] = {"test": lanes._norm(regression_test), "command": test_command}
    changes.save(root, record)
    changes.set_active(root, change_id)
    return {"status": "RUNNING", "change": change_id, "lane": "patch", "step": "implement",
            "note": changes.note_relpath(change_id), "card": _implement_card(record)}


def _require_running(root: str, change_id: str | None) -> dict:
    record = changes.load(root, change_id) if change_id else changes.active(root)
    if record is None:
        raise changes.ChangeError("no active change — run `step begin` first")
    if record.get("status") != "RUNNING":
        raise changes.ChangeError(f"change {record['id']} is {record.get('status')}, not RUNNING")
    return record


def widen(root: str, *, paths, change_id: str | None = None) -> dict:
    """Add files to the envelope; re-triage, escalating when the lane rises."""
    root = os.path.abspath(root)
    record = _require_running(root, change_id)
    wider = sorted(set(record["envelope"]) | set(_normalize_paths(paths)))
    result = lanes.triage(root, intent=record["intent"], paths=wider, confirmed=record.get("confirmed") or (),
                          denied=record.get("denied") or ())
    escalation = lanes.escalation(record["lane"], result)
    if escalation:
        return _escalate(root, record, escalation)
    record["envelope"] = wider
    changes.save(root, record)
    return {"status": "RUNNING", "change": record["id"], "envelope": wider}


def _escalate(root: str, record: dict, escalation: dict) -> dict:
    record["status"] = "ESCALATED"
    record["escalation"] = escalation
    changes.save(root, record)
    changes.set_active(root, None)
    changes.append_log(root, {"id": record["id"], "status": "ESCALATED", "to": escalation["to"], "at": changes.now()})
    return {"status": "ESCALATED", "change": record["id"], "lane": escalation["to"],
            "because": escalation["because"],
            "card": render("escalated", change_id=record["id"], lane=escalation["to"],
                           because="; ".join(escalation["because"]), note_path=changes.note_relpath(record["id"]))}


def end(root: str, *, change_id: str | None = None, runner=subprocess.run, run_gates: bool = True,
        dry_run: bool = False) -> dict:
    """Verify the change; PASSED only with every check green (fail-closed)."""
    root = os.path.abspath(root)
    record = _require_running(root, change_id)
    result = verify.post(root, record, runner=runner, run_gates=run_gates)
    failed = [c for c in result["checks"] if not c["ok"]]
    if dry_run:
        return {"status": "DRY_RUN", "change": record["id"], "ok": result["ok"], "failed": failed,
                "checks": result["checks"]}
    if result["escalation"]:
        return _escalate(root, record, result["escalation"])
    attempt = {"at": changes.now(), "ok": result["ok"], "failed": [c["name"] for c in failed],
               "gates": [{k: g[k] for k in ("name", "result", "exit_code")} for g in result["gates"]],
               "changed": result["changed"], "loc": result["loc"]}
    record.setdefault("attempts", []).append(attempt)
    if not result["ok"]:
        changes.save(root, record)
        return {"status": "RUNNING", "change": record["id"], "ok": False,
                "failed": [{"name": c["name"], "detail": c["detail"]} for c in failed],
                "gates": [g for g in result["gates"] if g["result"] != "PASSED"],
                "next": "fix what failed and run `step end` again"}
    record["status"] = "PASSED"
    record["step"] = "done"
    record["evidence"] = {"verified": True, "at": attempt["at"], "checks": [c["name"] for c in result["checks"]],
                          "changed": result["changed"], "loc": result["loc"],
                          "gates": attempt["gates"]}
    changes.save(root, record)
    changes.set_active(root, None)
    changes.append_log(root, {"id": record["id"], "status": "PASSED", "lane": "patch", "kind": record["kind"],
                              "files": result["changed"], "loc": result["loc"], "at": attempt["at"]})
    return {"status": "PASSED", "change": record["id"], "files": result["changed"], "loc": result["loc"],
            "gates": attempt["gates"]}


def pause(root: str, *, change_id: str | None = None, reason: str = "") -> dict:
    root = os.path.abspath(root)
    record = _require_running(root, change_id)
    record["status"] = "PAUSED"
    record["paused"] = {"at": changes.now(), "reason": reason}
    changes.save(root, record)
    return {"status": "PAUSED", "change": record["id"], "reason": reason}


def resume(root: str, *, change_id: str) -> dict:
    root = os.path.abspath(root)
    record = changes.load(root, change_id)
    if record.get("status") != "PAUSED":
        raise changes.ChangeError(f"change {change_id} is {record.get('status')}, not PAUSED")
    running = changes.active(root)
    if running and running.get("status") == "RUNNING" and running["id"] != change_id:
        raise changes.ChangeError(f"change {running['id']} is running — end or pause it first")
    record["status"] = "RUNNING"
    record["stop_reentries"] = 0
    changes.save(root, record)
    changes.set_active(root, change_id)
    return {"status": "RUNNING", "change": change_id, "card": _implement_card(record)}
