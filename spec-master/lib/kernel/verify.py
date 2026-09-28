"""`verify:post` for the lane flow: a change is done only with evidence.

Fail-closed checks over the real diff (never over what the agent says it
did): the change note, provenance of its claims, the diff staying inside the
declared envelope, the change still fitting its lane, and the project's own
gates actually passing. The bugfix variant also proves the regression test
failed before the fix and passes after it. External processes go through an
injectable runner (constitution Principle III).
"""
from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import tempfile

import quality_gates

from kernel import changes, lanes

DEFAULT_GATE_TIMEOUT = 900
NOTE_SOFT_LIMIT = 1024
NOTE_HARD_LIMIT = 4096
OUTPUT_TAIL = 1500

TAGS = ("EXPLICIT", "INFERRED", "DISCOVERED_FROM_CODEBASE")
_INTENT_RE = re.compile(r"^\s*(?:[-*]\s*)?\**intent\**\s*:.*\[(EXPLICIT)\]", re.IGNORECASE | re.MULTILINE)
_CHECK_RE = re.compile(r"^\s*[-*]\s*\[(EXPLICIT|INFERRED|DISCOVERED_FROM_CODEBASE)\](.*)$", re.MULTILINE)
_TEST_REF_RE = re.compile(r"\(test:\s*([^)\s:]+)(?:::[^)]*)?\)")
_FILE_LINE_RE = re.compile(r"`?([\w./-]+\.[\w]+):(\d+)`?")


def _check(name: str, ok: bool, detail: str, **extra) -> dict:
    return {"name": name, "ok": ok, "detail": detail, **extra}


def read_note(root: str, change_id: str) -> str | None:
    path = os.path.join(root, changes.note_relpath(change_id))
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def note_checks(root: str, change_id: str, note: str | None) -> list[dict]:
    relative = changes.note_relpath(change_id)
    if note is None:
        return [_check("note", False, f"{relative} is missing")]
    results = []
    size = len(note.encode("utf-8"))
    if size > NOTE_HARD_LIMIT:
        results.append(_check("note", False, f"{relative} has {size} bytes (> {NOTE_HARD_LIMIT}); a change note is a few lines"))
    else:
        detail = relative + (f" ({size} bytes, above the {NOTE_SOFT_LIMIT}-byte target)" if size > NOTE_SOFT_LIMIT else "")
        results.append(_check("note", True, detail))
    results.append(_check("intent", bool(_INTENT_RE.search(note)),
                          "the intent line carries [EXPLICIT]" if _INTENT_RE.search(note)
                          else "missing `Intent: ... [EXPLICIT]` quoting the user's request"))
    if "UNRESOLVED" in note:
        results.append(_check("unresolved", False, "the note still has UNRESOLVED items — a patch cannot carry open questions"))
    checks = _CHECK_RE.findall(note)
    if not checks:
        results.append(_check("acceptance", False, "no acceptance check line (`- [EXPLICIT] ... (test: path)`)"))
        return results
    missing_tests, bad_provenance = [], []
    for tag, text in checks:
        refs = _TEST_REF_RE.findall(text)
        if not refs:
            missing_tests.append(text.strip()[:60])
        for ref in refs:
            if not os.path.isfile(os.path.join(root, ref)):
                missing_tests.append(f"{ref} (not found)")
        if tag == "DISCOVERED_FROM_CODEBASE":
            cited = _FILE_LINE_RE.findall(text)
            if not cited:
                bad_provenance.append(f"no file:line for: {text.strip()[:60]}")
            for path, line in cited:
                full = os.path.join(root, path)
                if not os.path.isfile(full):
                    bad_provenance.append(f"{path}:{line} does not exist")
                    continue
                with open(full, "r", encoding="utf-8", errors="replace") as fh:
                    if int(line) < 1 or int(line) > sum(1 for _ in fh):
                        bad_provenance.append(f"{path}:{line} is past the end of the file")
    results.append(_check("acceptance", not missing_tests,
                          f"{len(checks)} acceptance check(s), each linked to a test" if not missing_tests
                          else "acceptance checks without an existing test: " + "; ".join(missing_tests[:5])))
    if any(tag == "DISCOVERED_FROM_CODEBASE" for tag, _ in checks):
        results.append(_check("provenance", not bad_provenance,
                              "every DISCOVERED_FROM_CODEBASE claim cites an existing file:line" if not bad_provenance
                              else "; ".join(bad_provenance[:5])))
    return results


def gate_commands(root: str) -> list[dict]:
    return [gate for gate in quality_gates.detect(root) if gate.get("command")]


def _argv(command) -> list[str]:
    return list(command) if isinstance(command, (list, tuple)) else shlex.split(command)


def run_gate(root: str, gate: dict, runner=subprocess.run) -> dict:
    cwd = os.path.join(root, gate["cwd"]) if gate.get("cwd") else root
    timeout = gate.get("timeout_seconds") or DEFAULT_GATE_TIMEOUT
    try:
        proc = runner(_argv(gate["command"]), cwd=cwd, capture_output=True, text=True, timeout=timeout)
        output = (proc.stdout or "") + (proc.stderr or "")
        result = "PASSED" if proc.returncode == 0 else "FAILED"
        code = proc.returncode
    except subprocess.TimeoutExpired:
        output, result, code = f"timed out after {timeout}s", "FAILED", None
    except (OSError, ValueError) as exc:
        output, result, code = str(exc), "FAILED", None
    return {"name": gate.get("name"), "command": gate["command"], "blocking": gate.get("blocking", True),
            "result": result, "exit_code": code, "output_tail": output[-OUTPUT_TAIL:]}


def regression_check(root: str, record: dict, runner=subprocess.run) -> list[dict]:
    """Bugfix variant: the regression test fails on the base commit (with the
    new test copied in) and passes on the working tree."""
    bugfix = record.get("bugfix") or {}
    test_path, command = bugfix.get("test"), bugfix.get("command")
    commit = (record.get("base") or {}).get("commit")
    if not (test_path and command and commit):
        return [_check("regression", False, "bugfix changes need --regression-test, --test-command and a git base commit")]
    source = os.path.join(root, test_path)
    if not os.path.isfile(source):
        return [_check("regression", False, f"{test_path} does not exist")]
    temp = tempfile.mkdtemp(prefix="spec-master-regression-")
    worktree = os.path.join(temp, "base")
    try:
        code, out = changes.git(root, "worktree", "add", "--detach", worktree, commit, runner=runner)
        if code != 0:
            return [_check("regression", False, f"could not create a base worktree: {out.strip()[:200]}")]
        target = os.path.join(worktree, test_path)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(source, target)
        before = run_gate(worktree, {"name": "regression@base", "command": command}, runner=runner)
        after = run_gate(root, {"name": "regression@change", "command": command}, runner=runner)
    finally:
        changes.git(root, "worktree", "remove", "--force", worktree, runner=runner)
        shutil.rmtree(temp, ignore_errors=True)
    ok = before["result"] == "FAILED" and after["result"] == "PASSED"
    detail = (f"fails on the base ({before['exit_code']}) and passes with the fix" if ok else
              f"base: {before['result']}, change: {after['result']} — the test must fail before and pass after")
    return [_check("regression", ok, detail, runs=[before, after])]


def post(root: str, record: dict, *, runner=subprocess.run, run_gates: bool = True) -> dict:
    """Evaluate a patch change. Returns {ok, checks, gates, changed, loc,
    escalation}; `escalation` is set when the real diff no longer fits the
    change's lane (the caller moves the change to the next lane)."""
    root = os.path.abspath(root)
    change_id = record["id"]
    note_rel = changes.note_relpath(change_id)
    changed = [p for p in changes.changed_since(root, record.get("base") or {}, runner=runner)
               if not p.startswith(".spec-master/")]
    checks = note_checks(root, change_id, read_note(root, change_id))

    envelope = set(record.get("envelope") or [])
    outside = [p for p in changed if p not in envelope and not lanes.is_test_path(p) and p != note_rel]
    checks.append(_check("scope", not outside,
                         f"{len(changed)} changed file(s), all declared" if not outside
                         else "changed outside the declared envelope: " + ", ".join(outside[:8])))
    if not changed:
        checks.append(_check("diff", False, "nothing changed since `step begin`"))

    production = lanes.production_files(changed)
    loc = changes.diff_loc(root, record.get("base") or {}, production, runner=runner)
    retriage = lanes.triage(root, intent=record.get("intent", ""), paths=changed, loc=loc,
                            confirmed=record.get("confirmed") or (), denied=record.get("denied") or ())
    escalation = lanes.escalation(record["lane"], retriage)
    checks.append(_check("lane", escalation is None,
                         f"still a {record['lane']} change ({len(production)} file(s), {loc} line(s))"
                         if escalation is None else "the diff no longer fits the lane: " + "; ".join(escalation["because"])))

    gates = []
    if not run_gates:
        checks.append(_check("gates", False, "gates skipped (--no-gates): a change passes only after its gates run"))
    else:
        detected = gate_commands(root)
        if not detected:
            checks.append(_check("gates", False, "no executable gate detected or declared (.spec-master/gates.json)"))
        else:
            gates = [run_gate(root, gate, runner=runner) for gate in detected]
            failed = [g["name"] for g in gates if g["blocking"] and g["result"] != "PASSED"]
            checks.append(_check("gates", not failed,
                                 f"{len(gates)} gate(s) passed" if not failed else "failing gate(s): " + ", ".join(failed)))
    if record.get("kind") == "bugfix":
        checks.extend(regression_check(root, record, runner=runner))

    return {
        "ok": all(c["ok"] for c in checks),
        "checks": checks,
        "gates": gates,
        "changed": changed,
        "loc": loc,
        "escalation": escalation,
    }
