"""Readable ADDED/MODIFIED/REMOVED delta between runs (roadmap item 7).

fingerprint.py already decides *whether* a context doc changed (whole-file
hash -> stale phases). This module keeps the same data source — sha256 of the
files on disk — but at a finer grain, so a resume can show the user *what*
changed, in the same vocabulary as `constitution diff`:

- per artifact (context docs, constitution, each feature's spec/plan/tasks):
  ADDED / MODIFIED / REMOVED;
- per heading section inside a modified artifact (constitution_diff's own
  section parser);
- per Spec Kit task id (`T001`...) inside a modified tasks.md, including
  checkbox flips.

The snapshot lives at `.spec-master/delta/snapshot.json` and is refreshed
with `delta snapshot` at the end of each run. Pure stdlib; no diffing library
and no LLM involved.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re

import constitution_diff
import fingerprint

SNAPSHOT_VERSION = 1
SNAPSHOT_RELPATH = os.path.join(".spec-master", "delta", "snapshot.json")
CONTEXT_DIR = os.path.join(".spec-master", "context")
CONSTITUTION_PATH = os.path.join(".specify", "memory", "constitution.md")

# Spec Kit artifact -> downstream phases it may invalidate (mirrors
# fingerprint.DOC_TO_STALE_PHASES; implement is never auto-invalidated).
ARTIFACT_STALE_PHASES = {
    "spec": ["clarify", "plan", "tasks", "analyze"],
    "plan": ["tasks", "analyze"],
    "tasks": ["analyze"],
    "constitution": ["plan", "tasks", "analyze"],
}
_FEATURE_ARTIFACTS = (("spec", "spec.md"), ("plan", "plan.md"), ("tasks", "tasks.md"))
_PHASE_ORDER = ["specify", "clarify", "plan", "tasks", "analyze", "implement", "validate"]

_TASK_RE = re.compile(r"^\s*[-*]\s*\[(?P<done>[ xX])\]\s*(?P<id>T\d+)\b(?P<rest>.*)$", re.MULTILINE)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read(path: str) -> str | None:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def parse_tasks(text: str) -> dict:
    """{task_id: {"hash", "done", "title"}} for checklist lines like `- [ ] T001 ...`."""
    tasks = {}
    for m in _TASK_RE.finditer(text):
        title = m.group("rest").strip()
        tasks[m.group("id")] = {"hash": _sha(title), "done": m.group("done") != " ", "title": title[:160]}
    return tasks


def describe_artifact(text: str, kind: str) -> dict:
    sections = {h: _sha(body) for h, body in constitution_diff._parse_sections(text).items()}
    entry = {"kind": kind, "hash": _sha(text), "sections": sections}
    if kind == "tasks":
        entry["tasks"] = parse_tasks(text)
    return entry


def collect_artifacts(root: str, state: dict | None) -> dict:
    """{relpath: (kind, feature_id|None)} of every artifact worth diffing."""
    root = os.path.abspath(root)
    artifacts: dict[str, tuple] = {}
    context_dir = os.path.join(root, CONTEXT_DIR)
    if os.path.isdir(context_dir):
        for name in sorted(os.listdir(context_dir)):
            if name.endswith(".md"):
                artifacts[os.path.join(CONTEXT_DIR, name)] = ("context", None)
    if state and state.get("context"):
        artifacts.setdefault(os.path.normpath(state["context"]), ("context", None))
    artifacts[CONSTITUTION_PATH] = ("constitution", None)
    for feature in (state or {}).get("features", []):
        spec_dir = feature.get("spec_directory")
        if not spec_dir:
            continue
        for kind, filename in _FEATURE_ARTIFACTS:
            artifacts[os.path.join(os.path.normpath(spec_dir), filename)] = (kind, feature.get("id"))
    return artifacts


def snapshot(root: str, state: dict | None) -> dict:
    root = os.path.abspath(root)
    entries = {}
    for rel, (kind, feature_id) in collect_artifacts(root, state).items():
        text = _read(os.path.join(root, rel))
        if text is None:
            continue
        entry = describe_artifact(text, kind)
        entry["feature"] = feature_id
        entries[rel] = entry
    return {
        "version": SNAPSHOT_VERSION,
        "taken_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "artifacts": entries,
    }


def _diff_keys(prev: dict, cur: dict) -> list[dict]:
    changes = []
    for key, value in cur.items():
        if key not in prev:
            changes.append({"name": key, "change": "ADDED"})
        elif prev[key] != value:
            changes.append({"name": key, "change": "MODIFIED"})
    for key in prev:
        if key not in cur:
            changes.append({"name": key, "change": "REMOVED"})
    return changes


def _diff_tasks(prev: dict, cur: dict) -> list[dict]:
    changes = []
    for task_id, task in cur.items():
        old = prev.get(task_id)
        if old is None:
            changes.append({"id": task_id, "change": "ADDED", "title": task["title"]})
            continue
        detail = []
        if old["hash"] != task["hash"]:
            detail.append("text")
        if old["done"] != task["done"]:
            detail.append("checked" if task["done"] else "unchecked")
        if detail:
            changes.append({"id": task_id, "change": "MODIFIED", "detail": detail, "title": task["title"]})
    for task_id, task in prev.items():
        if task_id not in cur:
            changes.append({"id": task_id, "change": "REMOVED", "title": task.get("title", "")})
    return changes


def _stale_for(entry_kind: str, rel: str) -> list[str]:
    if entry_kind == "context":
        return fingerprint.DOC_TO_STALE_PHASES.get(os.path.basename(rel), [])
    return ARTIFACT_STALE_PHASES.get(entry_kind, [])


def delta(previous: dict | None, current: dict) -> dict:
    """Compare two snapshots. `previous=None` means first run (nothing to report)."""
    if not previous:
        return {"baseline": False, "artifacts": [], "stale_phases": {}, "summary": {}}
    prev_art = previous.get("artifacts", {})
    cur_art = current.get("artifacts", {})
    artifacts = []
    stale: dict[str, list[str]] = {}

    def _mark(scope: str, phases: list[str]) -> None:
        bucket = stale.setdefault(scope, [])
        for phase in phases:
            if phase not in bucket:
                bucket.append(phase)

    for rel in sorted(set(prev_art) | set(cur_art)):
        old, new = prev_art.get(rel), cur_art.get(rel)
        if old and new and old["hash"] == new["hash"]:
            continue
        ref = new or old
        entry = {"artifact": rel, "kind": ref["kind"], "feature": ref.get("feature")}
        if old is None:
            entry["change"] = "ADDED"
        elif new is None:
            entry["change"] = "REMOVED"
        else:
            entry["change"] = "MODIFIED"
            entry["sections"] = _diff_keys(old.get("sections", {}), new.get("sections", {}))
            if ref["kind"] == "tasks":
                entry["tasks"] = _diff_tasks(old.get("tasks", {}), new.get("tasks", {}))
        phases = _stale_for(ref["kind"], rel)
        entry["stale_phases"] = phases
        _mark(ref.get("feature") or "*", phases)
        artifacts.append(entry)

    for scope, phases in stale.items():
        phases.sort(key=_PHASE_ORDER.index)

    summary = {"ADDED": 0, "MODIFIED": 0, "REMOVED": 0}
    for entry in artifacts:
        summary[entry["change"]] += 1
    return {
        "baseline": True,
        "since": previous.get("taken_at"),
        "artifacts": artifacts,
        "stale_phases": stale,
        "summary": summary,
    }


def render(result: dict) -> str:
    lines = ["# Context Delta", ""]
    if not result.get("baseline"):
        lines += ["No previous snapshot — this run becomes the baseline.", ""]
        return "\n".join(lines)
    counts = result["summary"]
    lines.append(f"Since {result.get('since') or 'last snapshot'}: "
                 f"{counts.get('ADDED', 0)} added, {counts.get('MODIFIED', 0)} modified, "
                 f"{counts.get('REMOVED', 0)} removed.")
    lines.append("")
    if not result["artifacts"]:
        lines += ["No spec/plan/tasks/context changes since the last run.", ""]
        return "\n".join(lines)
    for entry in result["artifacts"]:
        scope = f" — feature `{entry['feature']}`" if entry.get("feature") else ""
        lines.append(f"## {entry['change']} `{entry['artifact']}`{scope}")
        for section in entry.get("sections", []):
            lines.append(f"- {section['change']} section: {section['name']}")
        for task in entry.get("tasks", []):
            detail = f" ({', '.join(task['detail'])})" if task.get("detail") else ""
            lines.append(f"- {task['change']} task {task['id']}{detail}: {task['title']}")
        if entry.get("stale_phases"):
            lines.append(f"- Potentially stale: {', '.join(entry['stale_phases'])}")
        lines.append("")
    if result["stale_phases"]:
        lines.append("## Stale phases by scope")
        for scope, phases in result["stale_phases"].items():
            label = "all features" if scope == "*" else scope
            lines.append(f"- {label}: {', '.join(phases) or '—'}")
        lines.append("")
    lines.append("`implement` is never auto-invalidated — assess impact before redoing it.")
    lines.append("")
    return "\n".join(lines)


def load_snapshot(root: str) -> dict | None:
    path = os.path.join(os.path.abspath(root), SNAPSHOT_RELPATH)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def save_snapshot(root: str, snap: dict) -> str:
    path = os.path.join(os.path.abspath(root), SNAPSHOT_RELPATH)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(snap, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)
    return path


def report(root: str, state: dict | None) -> dict:
    """Delta between the stored snapshot and the working tree (read-only)."""
    return delta(load_snapshot(root), snapshot(root, state))
