"""`verify:pre`: the deterministic analyze of the Standard lane.

It replaces `/speckit.analyze` ONLY in the Standard lane (proposal §5.6); the
full cycle keeps the Spec Kit skill (constitution Principle VII). It blocks
`implement` when the spec-lite has an open question, an acceptance check with
neither a test nor a task, a claim without provenance, or more than 12 tasks.

Reuses the parsers of `kernel/verify.py` (acceptance lines, test refs,
file:line provenance) and `evidence.py` (task lines). Read-only, no LLM.

`light_analyze` is the same check under the name the XS/S ceremony profile
uses ("light" analyze, `risk_profile.CEREMONY_PROFILES`).
"""
from __future__ import annotations

import os
import re

from kernel import paths as paths_mod
from kernel import verify

SPEC_LITE_BYTES = 8192
SPEC_LITE_TASKS = 12
_OPEN_RE = re.compile(r"\bUNRESOLVED\b|NEEDS CLARIFICATION", re.IGNORECASE)
_TASK_REF_RE = re.compile(r"\(task:\s*(T\d+[a-z]?)\)")


def _read(path: str) -> str | None:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def _check(name: str, ok: bool, detail: str) -> dict:
    return {"name": name, "ok": ok, "detail": detail}


def run(root: str, spec_dir: str) -> dict:
    """{ok, checks, tasks, acceptance} for `spec_dir/spec.md` (+ `tasks.md`
    when the directory is a full-cycle set, which lifts the spec-lite caps)."""
    root = os.path.abspath(root)
    spec_path = os.path.join(root, spec_dir, "spec.md")
    spec = _read(spec_path)
    if spec is None:
        return {"ok": False, "tasks": 0, "acceptance": 0,
                "checks": [_check("spec", False, f"{spec_dir}/spec.md is missing")]}
    import evidence  # lazy: keeps the step API import graph small
    tasks_text = _read(os.path.join(root, spec_dir, "tasks.md"))
    lite = tasks_text is None
    checks = [_check("spec", True, f"{spec_dir}/spec.md")]
    size = len(spec.encode("utf-8"))
    if lite:
        checks.append(_check("size", size <= SPEC_LITE_BYTES, f"{size} bytes"
                             + ("" if size <= SPEC_LITE_BYTES else f" > {SPEC_LITE_BYTES} (not a spec-lite: use the full cycle)")))
    open_items = _OPEN_RE.findall(spec + (tasks_text or ""))
    checks.append(_check("unresolved", not open_items, "no UNRESOLVED / NEEDS CLARIFICATION item" if not open_items
                         else f"{len(open_items)} open item(s): resolve them (one batch of questions) before implement"))
    task_ids = [m.group(2) for m in map(evidence._TASK_LINE_RE.match, (tasks_text or spec).splitlines()) if m]
    task_ok = bool(task_ids) and (not lite or len(task_ids) <= SPEC_LITE_TASKS)
    checks.append(_check("tasks", task_ok, f"{len(task_ids)} task(s)" if task_ok else
                         ("no task line (`- [ ] T001 ...`)" if not task_ids
                          else f"{len(task_ids)} tasks > {SPEC_LITE_TASKS}: split the change or use the full cycle")))
    acceptance = verify._CHECK_RE.findall(spec)
    uncovered = []
    for _tag, text in acceptance:
        tests = [t for t in verify._TEST_REF_RE.findall(text) if paths_mod.is_test_path(t)]
        refs = _TASK_REF_RE.findall(text)
        if not tests and not (refs and all(r in task_ids for r in refs)):
            uncovered.append(text.strip()[:60])
    if not acceptance:
        checks.append(_check("coverage", False, "no acceptance check (`- [EXPLICIT] ... (test: path)`)"))
    else:
        checks.append(_check("coverage", not uncovered, f"{len(acceptance)} acceptance check(s), each with a test or a task"
                             if not uncovered else "acceptance checks with neither a test nor a task: " + "; ".join(uncovered[:5])))
    bad = []
    for tag, text in acceptance:
        if tag != "DISCOVERED_FROM_CODEBASE":
            continue
        cited = verify._FILE_LINE_RE.findall(text)
        if not cited:
            bad.append(f"no file:line for: {text.strip()[:50]}")
        for rel, line in cited:
            body = _read(os.path.join(root, rel))
            if body is None or not 1 <= int(line) <= len(body.splitlines()):
                bad.append(f"{rel}:{line} does not exist")
    if any(tag == "DISCOVERED_FROM_CODEBASE" for tag, _ in acceptance):
        checks.append(_check("provenance", not bad, "every DISCOVERED_FROM_CODEBASE claim cites an existing file:line"
                             if not bad else "; ".join(bad[:5])))
    return {"ok": all(c["ok"] for c in checks), "checks": checks, "tasks": len(task_ids), "acceptance": len(acceptance)}


light_analyze = run
