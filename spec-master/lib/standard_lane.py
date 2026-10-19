"""The Standard lane (proposal §5.6, wave 2): spec-lite -> verify:pre ->
test-first implement (RED, GREEN) -> verify:post.

It lives outside `kernel/` (the kernel is at its LOC budget); the kernel only
delegates to it for records whose lane is `standard` (`step end`, cards).
Records, locks, git diff and gates all come from the kernel modules; the
analyze is `verify_pre` and the TDD evidence is `tdd_gates`. Triage decides
whether a change belongs here: critical signals still go to the full cycle,
which keeps `/speckit.analyze` (constitution Principle VII).
"""
from __future__ import annotations

import os
import re
import subprocess

import tdd_gates
import verify_pre
from kernel import changes, lanes, step, verify
from kernel import paths as paths_mod
from standard_lane_args import register  # noqa: F401 - re-exported for callers

SPECS_DIR = "specs"


def next_spec_dir(root: str, intent: str) -> str:
    numbers = [int(m.group(1)) for name in (os.listdir(os.path.join(root, SPECS_DIR))
                                            if os.path.isdir(os.path.join(root, SPECS_DIR)) else [])
               if (m := re.match(r"(\d{3})-", name))]
    return f"{SPECS_DIR}/{max(numbers, default=0) + 1:03d}-{changes.slug(intent, 32)}"


def default_test_command(root: str) -> list | str | None:
    try:
        gates = verify.gate_commands(root)
    except Exception:  # noqa: BLE001 - a broken manifest means no provable gate
        return None
    for gate in gates:
        if "test" in (gate.get("name") or "") or gate.get("category") == "test":
            return gate["command"]
    return gates[0]["command"] if gates else None


def card(record: dict) -> str:
    name = "standard-spec" if record.get("step") == "spec" else "standard-implement"
    return step.render(name, change_id=record["id"], intent=record["intent"], spec_dir=record["spec_dir"],
                       envelope=", ".join(record["envelope"]) or "(none)",
                       test_command=(record.get("tdd") or {}).get("command") or "(declare a test gate)")


def begin(root: str, *, intent: str, paths, kind: str = "change", confirmed=(), denied=(), unresolved: int = 0,
          test_command: str | None = None, spec_dir: str | None = None, runner=subprocess.run) -> dict:
    root = os.path.abspath(root)
    if not (intent or "").strip():
        raise changes.ChangeError("--intent is required (the user's request, verbatim)")
    running = changes.active(root)
    if running and running.get("status") == "RUNNING":
        raise changes.ChangeError(f"change {running['id']} is still running — end, pause or escalate it first")
    paths = step._normalize_paths(paths)
    result = lanes.triage(root, intent=intent, paths=paths, confirmed=confirmed, denied=denied,
                          unresolved=unresolved, requested="standard")
    if result["questions"]:
        return {"status": "QUESTIONS", "lane": result["lane"], "questions": result["questions"],
                "next": "ask the questions in one batch, then re-run with --confirm/--deny"}
    if result["lane"] != "standard":
        return {"status": "FULL_CYCLE", "lane": result["lane"], "reasons": result["reasons"],
                "next": "run the full cycle: /spec-master <context file> (PROTOCOL.md)"}
    if not changes.is_git_repo(root, runner=runner):
        return {"status": "FULL_CYCLE", "lane": "standard",
                "reasons": {"standard": [{"signal": "no_git", "detail": "the standard lane needs git to see the diff"}]},
                "next": "run the full cycle: /spec-master <context file> (PROTOCOL.md)"}
    spec_dir = lanes._norm(spec_dir) if spec_dir else next_spec_dir(root, intent)
    spec = f"{spec_dir}/spec.md"
    os.makedirs(changes.changes_dir(root), exist_ok=True)
    change_id = changes.new_id(root, intent)
    record = {
        "id": change_id, "lane": "standard", "kind": kind, "intent": intent.strip(), "status": "RUNNING",
        "step": "spec", "spec_dir": spec_dir, "envelope": sorted(set(paths) | {spec, f"{spec_dir}/tasks.md"}),
        "confirmed": sorted(confirmed), "denied": sorted(denied),
        "base": {"commit": changes.head(root, runner=runner),
                 "dirty": {p: changes.file_digest(root, p) for p in changes.dirty_paths(root, runner=runner)}},
        "triage": {"lane": result["lane"], "signals": result["signals"]},
        "tdd": {"command": test_command or default_test_command(root), "runs": []},
        "created_at": changes.now(), "attempts": [], "stop_reentries": 0,
    }
    changes.save(root, record)
    changes.set_active(root, change_id)
    return {"status": "RUNNING", "change": change_id, "lane": "standard", "step": "spec", "spec_dir": spec_dir,
            "spec": spec, "card": card(record)}


def verify_pre_step(root: str, *, change_id: str | None = None) -> dict:
    """Run verify:pre; on success the change moves from `spec` to `implement`."""
    root = os.path.abspath(root)
    record = step._require_running(root, change_id)
    result = verify_pre.run(root, record["spec_dir"])
    out = {"status": "RUNNING", "change": record["id"], "ok": result["ok"],
           "failed": [c for c in result["checks"] if not c["ok"]], "checks": result["checks"]}
    if result["ok"] and record["step"] == "spec":
        record["step"] = "implement"
        changes.save(root, record)
    out["step"] = record["step"]
    out["next"] = ("write the failing test, then `standard red`" if result["ok"]
                   else "fix the spec-lite and run `standard verify-pre` again")
    return out


def tdd_run(root: str, phase: str, *, change_id: str | None = None, test_command: str | None = None,
            runner=subprocess.run) -> dict:
    root = os.path.abspath(root)
    record = step._require_running(root, change_id)
    if record["step"] == "spec":
        return {"ok": False, "detail": "verify:pre has not passed yet: run `standard verify-pre`"}
    result = tdd_gates.record_run(root, record, phase, command=test_command, runner=runner)
    result.update(status="RUNNING", change=record["id"])
    return result


def _open_tasks(root: str, spec_dir: str) -> list[str]:
    import evidence
    texts = []
    for name in ("spec.md", "tasks.md"):
        body = verify_pre._read(os.path.join(root, spec_dir, name))
        if body:
            texts.append(body)
    return evidence.open_tasks("\n".join(texts))


def end(root: str, record: dict, *, runner=subprocess.run, run_gates: bool = True, dry_run: bool = False) -> dict:
    """`step end` for a Standard change: PASSED only with every check green."""
    spec_dir = record["spec_dir"]
    base = record.get("base") or {}
    changed = [p for p in changes.changed_since(root, base, runner=runner) if not p.startswith(".spec-master/")]
    envelope = set(record.get("envelope") or [])
    outside = [p for p in changed if p not in envelope and not paths_mod.is_test_path(p)
               and not p.startswith(spec_dir + "/")]
    pre = verify_pre.run(root, spec_dir)
    production = lanes.production_files(changed)
    checks = [{"name": "verify_pre", "ok": pre["ok"],
               "detail": "spec-lite passes verify:pre" if pre["ok"] else
               "; ".join(c["detail"] for c in pre["checks"] if not c["ok"])[:300]},
              tdd_gates.check(record, bool(production))]
    open_tasks = _open_tasks(root, spec_dir)
    checks.append({"name": "tasks", "ok": not open_tasks,
                   "detail": "every task is checked" if not open_tasks else "open task(s): " + ", ".join(open_tasks[:8])})
    checks.append({"name": "scope", "ok": not outside, "detail": f"{len(changed)} changed file(s), all declared"
                   if not outside else "changed outside the declared envelope: " + ", ".join(outside[:8])})
    if not changed:
        checks.append({"name": "diff", "ok": False, "detail": "nothing changed since `standard begin`"})
    loc = changes.diff_loc(root, base, production, runner=runner)
    escalation = lanes.escalation("standard", lanes.triage(
        root, intent=record["intent"], paths=changed, loc=loc, confirmed=record.get("confirmed") or (),
        denied=record.get("denied") or ()))
    checks.append({"name": "lane", "ok": escalation is None, "detail": f"still a standard change ({len(production)} file(s), {loc} line(s))"
                   if escalation is None else "the diff no longer fits the lane: " + "; ".join(escalation["because"])})
    gates = []
    if not run_gates:
        checks.append({"name": "gates", "ok": False, "detail": "gates skipped (--no-gates): a change passes only after its gates run"})
    else:
        detected = verify.gate_commands(root)
        if not detected:
            checks.append({"name": "gates", "ok": False, "detail": "no executable gate detected or declared (.spec-master/gates.json)"})
        else:
            gates = [verify.run_gate(root, gate, runner=runner) for gate in detected]
            failed = [g["name"] for g in gates if g["blocking"] and g["result"] != "PASSED"]
            checks.append({"name": "gates", "ok": not failed,
                           "detail": f"{len(gates)} gate(s) passed" if not failed else "failing gate(s): " + ", ".join(failed)})
    ok = all(c["ok"] for c in checks)
    failed_checks = [c for c in checks if not c["ok"]]
    if dry_run:
        return {"status": "DRY_RUN", "change": record["id"], "ok": ok, "failed": failed_checks, "checks": checks}
    if escalation:
        return step._escalate(root, record, escalation)
    attempt = {"at": changes.now(), "ok": ok, "failed": [c["name"] for c in failed_checks],
               "gates": [{k: g[k] for k in ("name", "result", "exit_code")} for g in gates],
               "changed": changed, "loc": loc}
    record.setdefault("attempts", []).append(attempt)
    if not ok:
        changes.save(root, record)
        return {"status": "RUNNING", "change": record["id"], "ok": False,
                "failed": [{"name": c["name"], "detail": c["detail"]} for c in failed_checks],
                "gates": [g for g in gates if g["result"] != "PASSED"],
                "next": "fix what failed and run `step end` again"}
    record["status"], record["step"] = "PASSED", "done"
    record["evidence"] = {"verified": True, "at": attempt["at"], "checks": [c["name"] for c in checks],
                          "changed": changed, "loc": loc, "gates": attempt["gates"],
                          "tdd": [{k: r[k] for k in ("phase", "result", "exit_code", "at")} for r in tdd_gates.runs(record)]}
    changes.save(root, record)
    changes.set_active(root, None)
    changes.append_log(root, {"id": record["id"], "status": "PASSED", "lane": "standard", "kind": record["kind"],
                              "files": changed, "loc": loc, "at": attempt["at"]})
    return {"status": "PASSED", "change": record["id"], "files": changed, "loc": loc, "gates": attempt["gates"]}


# --------------------------------------------------------------------------- CLI

def run(args, csv=lambda value: [p for p in (value or "").split(",") if p.strip()]) -> dict:
    try:
        if args.standard_action == "begin":
            return begin(args.path, intent=args.intent, paths=csv(args.paths), confirmed=args.confirm or (),
                         denied=args.deny or (), unresolved=args.unresolved, test_command=args.test_command,
                         spec_dir=args.spec_dir)
        if args.standard_action == "verify-pre":
            if args.spec_dir:
                return verify_pre.run(args.path, args.spec_dir)
            return verify_pre_step(args.path, change_id=args.change)
        return tdd_run(args.path, args.standard_action, change_id=args.change, test_command=args.test_command)
    except changes.ChangeError as exc:
        return {"status": "ERROR", "error": str(exc)}
