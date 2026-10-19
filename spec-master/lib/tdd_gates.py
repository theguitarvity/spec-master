"""TDD RED/GREEN gates for the Standard lane, with evidence.

RED: the test command must FAIL, and the change must already contain a test.
GREEN: after a RED, the same command must PASS. Both runs are recorded in the
change record (`tdd.runs`: command, exit code, digest of the tests behind the
run) through `kernel/verify.run_gate`, so `step end` can prove the order.

`guard` is the PreToolUse check: it is cheap and import-light (the hook daemon
calls it on every write of a running Standard change) and the host only
enforces it when `hooks_mode` is `block`.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from kernel import changes, paths as paths_mod


def runs(record: dict) -> list[dict]:
    return (record.get("tdd") or {}).get("runs") or []


def guard(record: dict, relative: str) -> dict | None:
    """A deny verdict when `relative` is production code written before the
    spec passed verify:pre or before a RED run was recorded."""
    if record.get("lane") != "standard" or not paths_mod.production_files([relative]):
        return None
    if record.get("step") == "spec":
        return {"decision": "deny", "reason": f"{relative} is production code: finish the spec and run "
                "`standard verify-pre` first (verify:pre blocks implement)"}
    if not any(r.get("phase") == "red" and r.get("result") == "FAILED" for r in runs(record)):
        return {"decision": "deny", "reason": f"{relative} is production code: write the failing test first and "
                "record it with `standard red` (TDD RED before GREEN)"}
    return None


def _test_digests(root: str, files: list[str]) -> dict:
    import evidence  # heavy import, never on the hook path
    return {p: evidence._sha256(Path(root) / p) for p in files if (Path(root) / p).is_file()}


def record_run(root: str, record: dict, phase: str, *, command=None, runner=subprocess.run) -> dict:
    """Run the test command as `phase` (red|green) and append the evidence.
    Returns {ok, detail, run}; a rejected run is not recorded."""
    from kernel import verify
    command = command or (record.get("tdd") or {}).get("command")
    if not command:
        return {"ok": False, "detail": "no test command: pass --test-command (or declare a test gate in .spec-master/gates.json)"}
    changed = changes.changed_since(root, record.get("base") or {}, runner=runner)
    tests = [p for p in changed if paths_mod.is_test_path(p)]
    previous = runs(record)
    if phase == "red" and not tests:
        return {"ok": False, "detail": "RED needs a test in the change: write the failing test first"}
    if phase == "green" and not any(r["phase"] == "red" for r in previous):
        return {"ok": False, "detail": "GREEN needs a recorded RED first (`standard red`)"}
    gate = verify.run_gate(root, {"name": f"tdd:{phase}", "command": command}, runner=runner)
    run = {"phase": phase, "result": gate["result"], "exit_code": gate["exit_code"], "command": command,
           "at": changes.now(), "tests": _test_digests(root, tests), "output_tail": gate["output_tail"][-400:]}
    if phase == "red" and (gate["result"] != "FAILED" or gate["exit_code"] is None):
        return {"ok": False, "run": run, "detail": "a RED run must fail (exit code != 0) on the new test: "
                "the test does not prove the missing behavior yet"}
    if phase == "green" and gate["result"] != "PASSED":
        return {"ok": False, "run": run, "detail": "GREEN run failed: make the tests pass"}
    record.setdefault("tdd", {}).setdefault("runs", []).append(run)
    changes.save(root, record)
    return {"ok": True, "run": run, "detail": f"{phase.upper()} recorded"}


def check(record: dict, production_changed: bool) -> dict:
    """The `tdd` check of `step end`: a RED, then a last GREEN. A change with
    no production file (tests/docs only) needs no RED."""
    phases = [(r["phase"], r["result"]) for r in runs(record)]
    if not production_changed:
        return {"name": "tdd", "ok": True, "detail": "no production file changed"}
    red = next((i for i, p in enumerate(phases) if p == ("red", "FAILED")), None)
    ok = red is not None and phases[-1] == ("green", "PASSED") and len(phases) > red + 1
    return {"name": "tdd", "ok": ok, "detail": f"RED then GREEN recorded ({len(phases)} run(s))" if ok else
            "missing evidence: record a failing test (`standard red`), then make it pass (`standard green`)"}
