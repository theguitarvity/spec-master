"""Change records for the lane flow (`.spec-master/changes/`).

One JSON record per change (`<id>.json`, written only by the kernel under a
lock), the agent-written change note (`<id>.md`), a pointer to the active
change (`active.json`) and an append-only log of finished changes
(`log.jsonl`). The legacy `state.json` is not touched by the lane flow.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess

import state as state_mod

CHANGES_RELDIR = os.path.join(".spec-master", "changes")
ACTIVE = "active.json"
LOG = "log.jsonl"
STATUSES = ("RUNNING", "PASSED", "ESCALATED", "PAUSED", "ABANDONED")


class ChangeError(ValueError):
    pass


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def changes_dir(root: str) -> str:
    return os.path.join(os.path.abspath(root), CHANGES_RELDIR)


def record_path(root: str, change_id: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9._-]+", change_id or ""):
        raise ChangeError(f"invalid change id: {change_id!r}")
    return os.path.join(changes_dir(root), f"{change_id}.json")


def note_relpath(change_id: str) -> str:
    return f"{CHANGES_RELDIR.replace(os.sep, '/')}/{change_id}.md"


def slug(text: str, limit: int = 40) -> str:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return "-".join(words)[:limit].strip("-") or "change"


def new_id(root: str, intent: str, today: str | None = None) -> str:
    day = (today or now())[:10].replace("-", "")
    existing = os.listdir(changes_dir(root)) if os.path.isdir(changes_dir(root)) else []
    sequence = 1 + sum(1 for name in existing if name.startswith(f"c{day}-") and name.endswith(".json"))
    return f"c{day}-{sequence:03d}-{slug(intent)}"


def load(root: str, change_id: str) -> dict:
    path = record_path(root, change_id)
    if not os.path.isfile(path):
        raise ChangeError(f"unknown change: {change_id}")
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def save(root: str, record: dict) -> None:
    record["updated_at"] = now()
    path = record_path(root, record["id"])
    with state_mod.locked(path):
        state_mod.save(path, record)


def active_id(root: str) -> str | None:
    path = os.path.join(changes_dir(root), ACTIVE)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh).get("id")
    except (OSError, ValueError, AttributeError):
        return None


def active(root: str) -> dict | None:
    change_id = active_id(root)
    if not change_id:
        return None
    try:
        return load(root, change_id)
    except ChangeError:
        return None


def set_active(root: str, change_id: str | None) -> None:
    path = os.path.join(changes_dir(root), ACTIVE)
    if change_id is None:
        if os.path.exists(path):
            os.unlink(path)
        return
    state_mod.save(path, {"id": change_id, "since": now()})


def append_log(root: str, entry: dict) -> None:
    os.makedirs(changes_dir(root), exist_ok=True)
    with open(os.path.join(changes_dir(root), LOG), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")


# --------------------------------------------------------------------------- git boundary

def git(root: str, *args: str, runner=subprocess.run) -> tuple[int, str]:
    try:
        proc = runner(["git", *args], cwd=root, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)
    return proc.returncode, proc.stdout


def is_git_repo(root: str, runner=subprocess.run) -> bool:
    code, out = git(root, "rev-parse", "--is-inside-work-tree", runner=runner)
    return code == 0 and out.strip() == "true"


def head(root: str, runner=subprocess.run) -> str | None:
    code, out = git(root, "rev-parse", "HEAD", runner=runner)
    return out.strip() if code == 0 and out.strip() else None


def dirty_paths(root: str, runner=subprocess.run) -> list[str]:
    """Tracked changes plus untracked files (not ignored), repo-relative."""
    code, out = git(root, "status", "--porcelain", "-z", "--untracked-files=all", runner=runner)
    if code != 0:
        return []
    entries = out.split("\0")
    paths, skip = [], False
    for entry in entries:
        if skip:
            skip = False
            continue
        if len(entry) < 4:
            continue
        status, path = entry[:2], entry[3:]
        if status[0] in "RC":
            skip = True  # the next NUL-separated field is the source of the rename/copy
        paths.append(path)
    return sorted(set(paths))


# Build and cache artifacts that running a gate creates; they are never part
# of a change even when the repository does not gitignore them.
_JUNK_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".nox",
              "node_modules", ".venv", "venv", ".eggs", ".coverage"}
_JUNK_SUFFIXES = (".pyc", ".pyo", ".coverage")


def is_junk(path: str) -> bool:
    parts = path.split("/")
    return any(part in _JUNK_DIRS or part.endswith(".egg-info") for part in parts[:-1]) \
        or parts[-1].endswith(_JUNK_SUFFIXES)


def file_digest(root: str, relative: str) -> str | None:
    import hashlib
    path = os.path.join(root, relative)
    if not os.path.isfile(path):
        return None
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def changed_since(root: str, base: dict, runner=subprocess.run) -> list[str]:
    """Paths changed by this change: everything differing from the base
    commit, minus files that were already dirty at `step begin` and have not
    changed since (pre-existing work is not this change's diff)."""
    changed = set()
    commit = base.get("commit")
    if commit:
        code, out = git(root, "diff", "--name-only", commit, runner=runner)
        if code == 0:
            changed.update(line.strip() for line in out.splitlines() if line.strip())
    changed.update(dirty_paths(root, runner=runner))
    pre_existing = base.get("dirty") or {}
    return sorted(p for p in changed if not is_junk(p)
                  and (p not in pre_existing or file_digest(root, p) != pre_existing[p]))


def diff_loc(root: str, base: dict, paths: list[str], runner=subprocess.run) -> int:
    """Added + removed lines over `paths` since the base (untracked files count
    their full length)."""
    if not paths:
        return 0
    total = 0
    tracked = set()
    commit = base.get("commit")
    if commit:
        code, out = git(root, "diff", "--numstat", commit, "--", *paths, runner=runner)
        if code == 0:
            for line in out.splitlines():
                parts = line.split("\t")
                if len(parts) == 3:
                    tracked.add(parts[2])
                    total += sum(int(n) for n in parts[:2] if n.isdigit())
    for path in paths:
        if path in tracked:
            continue
        full = os.path.join(root, path)
        if os.path.isfile(full):
            try:
                with open(full, "r", encoding="utf-8", errors="replace") as fh:
                    total += sum(1 for _ in fh)
            except OSError:
                pass
    return total
