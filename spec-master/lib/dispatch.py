"""Multi-agent dispatch (M1): a per-wave manifest the host's subagents execute.

The core never spawns processes. It (1) computes a manifest per wave from
`worktree.compute_waves` over work packages, (2) prepares isolated worktrees
plus a governance scope, (3) ingests each subagent's bounded `PhaseResult`,
(4) reports status joined with the F14 events/ledger and (5) aggregates for
the Tech Lead. Nothing here merges, rebases, pushes or removes a worktree.
Spec: specs/018-multi-agent-dispatch/. Lives outside `kernel/` (LOC budget).
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import phase_result
import team_model
import worktree

SCHEMA = "spec-master.dispatch/v1"
RESULT_SCHEMA = "spec-master.dispatch-result/v1"
DEFAULT_CAP, MIN_CAP, MAX_CAP = 4, 1, 8
RESULT_MAX_CHARS = 8000  # ~2k tokens at 4 chars per token
MANIFEST_MAX_TOKENS = 2000
ROLES = ("sm-spec", "sm-implement", "sm-review")
LANES = ("standard", "critical")
CARD = "cards/dispatch.md"
ENGINE = Path(__file__).resolve().parent.parent
_TASK = re.compile(r"^\s*[-*]\s*\[(?P<done>[ xX])\]\s*(?P<id>T\d+)\b(?P<rest>.*)$", re.MULTILINE)
_TAGS = re.compile(r"\[[^\]]*\]")


def _read_json(path: str):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _write_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------------ cap and packages

def resolve_cap(root: str, arg: int | None = None) -> int:
    """argument > `.spec-master/policy.json` `dispatch.max_agents` > 4; valid 1..8."""
    value, source = arg, "--max-agents"
    if value is None:
        policy = _read_json(os.path.join(root, ".spec-master", "policy.json")) or {}
        section = policy.get("dispatch") if isinstance(policy, dict) else None
        value = section.get("max_agents") if isinstance(section, dict) else None
        source = "policy dispatch.max_agents"
    if value is None:
        return DEFAULT_CAP
    if isinstance(value, bool) or not isinstance(value, int) or not MIN_CAP <= value <= MAX_CAP:
        raise ValueError(f"{source} must be an integer from {MIN_CAP} to {MAX_CAP}, got {value!r}")
    return value


def _reviewer(owner: str, reviewer: str | None = None) -> str:
    reviewer = reviewer or team_model.assign_peer_review(owner)
    return "architect" if reviewer == owner else reviewer


def _packages_from_tasks(root: str, feature_id: str) -> list[dict]:
    state = _read_json(os.path.join(root, ".spec-master", "state.json")) or {}
    feature = next((f for f in state.get("features") or [] if isinstance(f, dict) and f.get("id") == feature_id), None)
    if not feature or not feature.get("spec_directory"):
        return []
    try:
        with open(os.path.join(root, feature["spec_directory"], "tasks.md"), "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return []
    found = []
    for match in _TASK.finditer(text):
        if match.group("done") != " ":
            continue
        head, *fields = [part.strip() for part in match.group("rest").split("|")]
        meta = {key.strip(): value.strip() for key, _, value in (f.partition(":") for f in fields)}
        owner = meta.get("owner") or team_model._infer_owner(_TAGS.sub("", head))
        found.append({
            "id": match.group("id"), "feature_id": feature_id, "title": _TAGS.sub("", head).strip(" :"),
            "owner_agent": owner, "depends_on": re.findall(r"T\d+", meta.get("depends_on", "")),
            "owned_paths": [p.strip() for p in meta.get("owns", "").split(",") if p.strip()],
        })
    return found


def build_packages(root: str, feature_id: str) -> list[dict]:
    """Work packages of a feature: `.spec-master/workstreams.json`, else its open tasks.md tasks."""
    doc = _read_json(os.path.join(root, ".spec-master", "workstreams.json")) or {}
    raw = [p for p in doc.get("packages") or [] if isinstance(p, dict) and p.get("feature_id") == feature_id]
    raw = raw or _packages_from_tasks(root, feature_id)
    known = {p["id"] for p in raw}
    packages = []
    for package in raw:
        owner = package.get("owner_agent") or "fullstack-dev"
        packages.append({**package, "owner_agent": owner,
                         "reviewer_agent": _reviewer(owner, package.get("reviewer_agent")),
                         "depends_on": [d for d in package.get("depends_on") or [] if d in known],
                         "owned_paths": list(package.get("owned_paths") or [])})
    return packages


def _ordered(packages: list[dict]) -> list[dict]:
    placed, order = set(), []
    pending = list(packages)
    while pending:
        ready = [p for p in pending if all(d in placed for d in p["depends_on"])]
        if not ready:
            raise ValueError("work packages have a dependency cycle: " + ", ".join(p["id"] for p in pending))
        order.append(ready[0])
        placed.add(ready[0]["id"])
        pending.remove(ready[0])
    return order


def _wave_packages(root: str, feature_id: str, wave_index: int) -> tuple[list[dict], int]:
    packages = build_packages(root, feature_id)
    if not packages:
        raise ValueError(f"no work packages for feature {feature_id!r} (workstreams.json or tasks.md)")
    ordered = _ordered(packages)
    waves = worktree.compute_waves([{"id": p["id"], "dependencies": p["depends_on"]} for p in ordered])
    if not 0 <= wave_index < len(waves):
        raise ValueError(f"wave {wave_index} does not exist (feature has {len(waves)} wave(s))")
    by_id = {p["id"]: p for p in ordered}
    return [by_id[i] for i in waves[wave_index]["feature_ids"]], len(waves)


# ------------------------------------------------------------------ manifest

def _agent_key(feature_id: str, package_id: str, role: str) -> str:
    return f"{feature_id}:{package_id}:{role}"


def _result_rel(feature_id: str, wave_index: int, package_id: str, review: bool = False) -> str:
    suffix = ".review.json" if review else ".json"
    return f".spec-master/dispatch/{feature_id}/{wave_index}/{package_id}{suffix}"


def _playbook(agent: str) -> str | None:
    relative = f"knowledge/playbooks/{agent}.md"
    return relative if (ENGINE / relative).is_file() else None


def _model_hints(root: str, feature_id: str) -> tuple:
    """(model, effort) from the F15 ceremony profile when it provides them; else host default."""
    try:
        state = _read_json(os.path.join(root, ".spec-master", "state.json")) or {}
        feature = next(f for f in state.get("features") or [] if f.get("id") == feature_id)
        import risk_profile
        profile = risk_profile.profile_for(feature["risk"]["tier"])
        return profile.get("model"), profile.get("effort")
    except Exception:  # noqa: BLE001 - optional producer
        return None, None


def _batches(keys: list[str], cap: int) -> list[list[str]]:
    return [keys[i:i + cap] for i in range(0, len(keys), cap)]


def build_manifest(root: str, feature_id: str, wave_index: int, max_agents: int | None = None, *,
                   lane: str = "standard", force_lane: str | bool | None = None, strategy: str = "trunk") -> dict:
    """Pure and deterministic: the dispatch manifest of one wave (contracts/dispatch-manifest.md)."""
    forced = None
    if lane not in LANES:
        if not force_lane or force_lane is True:
            raise ValueError(f"dispatch needs the standard or critical lane, got {lane!r} "
                             "(Patch never uses subagents); use --force-lane with a reason to override")
        forced = str(force_lane)
    cap = resolve_cap(root, max_agents)
    packages, _ = _wave_packages(root, feature_id, wave_index)
    in_git = os.path.exists(os.path.join(root, ".git"))
    isolate = in_git and len(packages) > 1
    model, effort = _model_hints(root, feature_id)
    entries = []
    for package in packages:
        pid = package["id"]
        path = worktree._worktree_path(root, pid) if isolate else None
        branch = f"feature/{pid}" if isolate and strategy == "git-flow" else None
        common = {"package_id": pid, "feature_id": feature_id, "card": CARD, "model": model, "effort": effort,
                  "worktree": path, "branch": branch, "owner": package["owner_agent"],
                  "reviewer": package["reviewer_agent"], "owned_paths": package["owned_paths"],
                  "depends_on": package["depends_on"]}
        role = "sm-spec" if package.get("kind") == "spec" else "sm-implement"
        entries.append({"agent_key": _agent_key(feature_id, pid, role), "role": role,
                        "playbook": _playbook(package["owner_agent"]), **common,
                        "result_path": _result_rel(feature_id, wave_index, pid)})
        entries.append({"agent_key": _agent_key(feature_id, pid, "sm-review"), "role": "sm-review",
                        "playbook": _playbook(package["reviewer_agent"]), **common, "read_only": True,
                        "after": [_agent_key(feature_id, pid, role)],
                        "result_path": _result_rel(feature_id, wave_index, pid, review=True)})
    work = [e["agent_key"] for e in entries if e["role"] != "sm-review"]
    reviews = [e["agent_key"] for e in entries if e["role"] == "sm-review"]
    import packaging_agents
    manifest = {"schema": SCHEMA, "feature_id": feature_id, "wave_index": wave_index,
                "lane": lane, "max_agents": cap, "batches": _batches(work, cap),
                "review_batches": _batches(reviews, cap), "entries": entries,
                "fallback_instructions": packaging_agents.FALLBACK_INSTRUCTIONS,
                "integration": {"auto_merge": False,
                                "gate": "workstreams review -> integrate (Tech Lead) -> human"}}
    if forced:
        manifest["forced_lane_reason"] = forced
    manifest["estimated_tokens"] = len(json.dumps(manifest, separators=(",", ":"))) // 4
    return manifest


# ------------------------------------------------------------------ prepare

def scope_path(root: str, agent_key: str) -> str:
    return os.path.join(root, ".spec-master", "dispatch", "scope", agent_key.replace(":", "__") + ".json")


def prepare(root: str, feature_id: str, wave_index: int, phase: str = "implement", max_agents: int | None = None,
            **options) -> dict:
    """Create worktrees (through `worktree.plan_worktree`), scope records and markers. Idempotent."""
    if phase not in ("implement", "review"):
        raise ValueError("phase must be implement or review")
    manifest = build_manifest(root, feature_id, wave_index, max_agents, **options)
    wanted = [e for e in manifest["entries"] if (e["role"] == "sm-review") == (phase == "review")]
    size = len({e["package_id"] for e in manifest["entries"]})
    strategy = options.get("strategy", "trunk")
    prepared = []
    for entry in wanted:
        state, path = "in_place", None
        if entry["worktree"]:
            handle = worktree.plan_worktree(entry["package_id"], root, strategy, wave_size=size, is_git_repo=True)
            state, path = handle["state"], handle["path"]
        scope = {"main_root": root, "agent_key": entry["agent_key"], "package_id": entry["package_id"],
                 "role": entry["role"], "owned_paths": entry["owned_paths"],
                 "read_only": entry["role"] == "sm-review"}
        _write_json(scope_path(root, entry["agent_key"]), scope)
        if path:
            _write_json(os.path.join(path, ".spec-master", "worktree.json"), scope)
        prepared.append({"agent_key": entry["agent_key"], "package_id": entry["package_id"],
                         "role": entry["role"], "worktree": path, "state": state})
    return {"feature_id": feature_id, "wave_index": wave_index, "phase": phase, "prepared": prepared}


# ------------------------------------------------------------------ results

def _fit(record: dict) -> dict:
    """Shrink the largest fields until the serialized record fits RESULT_MAX_CHARS (flags `truncated`)."""
    def size():
        return len(json.dumps(record, ensure_ascii=False))

    def shrink(key, limit):
        value = record[key]
        if isinstance(value, str) and len(value) > limit:
            record[key], record["truncated"] = value[:limit], True
        elif isinstance(value, list):
            clipped = [v[:200] if isinstance(v, str) else v for v in value[:50]]
            if clipped != value:
                record[key], record["truncated"] = clipped, True

    if not isinstance(record["evidence"], (str, type(None))):
        record["evidence"] = json.dumps(record["evidence"], ensure_ascii=False)
    for key in ("summary", "evidence"):
        shrink(key, 1500)
    for key in ("files", "questions"):
        shrink(key, 0)
    budget = RESULT_MAX_CHARS - 400  # room for the `path` the caller adds
    while size() > budget:
        key = max(("summary", "evidence", "files", "questions"), key=lambda k: len(json.dumps(record[k])))
        value = record[key]
        record[key] = value[:len(value) // 2] if value else value
        record["truncated"] = True
    return record


def _load_result(root: str, feature_id: str, wave_index: int, package_id: str, review: bool = False):
    return _read_json(os.path.join(root, _result_rel(feature_id, wave_index, package_id, review)))


def record_result(root: str, feature_id: str, wave_index: int, package_id: str, text: str, *,
                  role: str = "sm-implement", agent_key: str | None = None, agent_id: str | None = None) -> dict:
    """Store the subagent's last PhaseResult (<= 8000 chars, allow-listed). Updates nothing else."""
    if role not in ROLES:
        raise ValueError(f"role must be one of {', '.join(ROLES)}")
    packages, _ = _wave_packages(root, feature_id, wave_index)
    if package_id not in {p["id"] for p in packages}:
        raise ValueError(f"package {package_id!r} is not in wave {wave_index} of {feature_id}")
    review = role == "sm-review"
    agent_key = agent_key or _agent_key(feature_id, package_id, role)
    if review:
        owner_result = _load_result(root, feature_id, wave_index, package_id)
        if owner_result is None:
            raise ValueError(f"package {package_id}: the owner's result must be recorded before its review")
        owner_keys = {_agent_key(feature_id, package_id, r) for r in ("sm-implement", "sm-spec")}
        if agent_key in owner_keys or owner_result.get("agent_key") == agent_key or \
                (agent_id and owner_result.get("agent_id") == agent_id):
            raise ValueError(f"package {package_id}: a review by the owner agent is refused (reviewer != owner)")
    parsed = phase_result.parse_last_phase_result(text or "")
    if parsed is None:
        parsed = {"phase_result": "failed", "summary": "no valid phase_result block in the subagent's final message"}
    record = {"schema": RESULT_SCHEMA, "package_id": package_id, "agent_key": agent_key, "role": role,
              "agent_id": agent_id, "phase_result": parsed["phase_result"], "summary": parsed.get("summary") or "",
              "files": parsed.get("files") if isinstance(parsed.get("files"), list) else [],
              "questions": parsed.get("questions") if isinstance(parsed.get("questions"), list) else [],
              "evidence": parsed.get("evidence"), "truncated": False, "recorded_at": _now()}
    if not isinstance(record["summary"], str):
        record["summary"] = json.dumps(record["summary"], ensure_ascii=False)
    _fit(record)
    relative = _result_rel(feature_id, wave_index, package_id, review)
    _write_json(os.path.join(root, relative), record)
    return {**record, "path": relative}


# ------------------------------------------------------------------ status

def status(root: str, feature_id: str, wave_index: int, ledger_summary=None) -> dict:
    """Read-only: manifest entries joined with results, `agent.*` events and `by_agent` tokens."""
    manifest = build_manifest(root, feature_id, wave_index)
    notes, started, finished = [], {}, {}
    events_file = os.path.join(root, ".spec-master", "events.jsonl")
    if os.path.isfile(events_file):
        import events
        for event in events.read(root):
            agent = event.get("agent_id")
            if event["type"] == "agent.started":
                started.setdefault(agent, event.get("ts"))
            elif event["type"] == "agent.finished":
                finished[agent] = event.get("ts")
    else:
        notes.append("events.jsonl absent: started_at/finished_at are null")
    by_agent = None
    if ledger_summary is None and os.path.isfile(os.path.join(root, ".spec-master", "tokens.jsonl")):
        import ledger
        ledger_summary = ledger.summary
    if ledger_summary is not None:
        by_agent = (ledger_summary(root) or {}).get("by_agent") or {}
    else:
        notes.append("token ledger absent: tokens are null")
    out = []
    for entry in manifest["entries"]:
        review = entry["role"] == "sm-review"
        result = _load_result(root, feature_id, wave_index, entry["package_id"], review)
        agent = (result or {}).get("agent_id")
        owner_done = _load_result(root, feature_id, wave_index, entry["package_id"]) is not None
        out.append({"agent_key": entry["agent_key"], "package_id": entry["package_id"], "role": entry["role"],
                    "result_recorded": result is not None, "phase_result": (result or {}).get("phase_result"),
                    "agent_id": agent, "started_at": started.get(agent) if agent else None,
                    "finished_at": finished.get(agent) if agent else None,
                    "tokens": (by_agent or {}).get(agent) if agent and by_agent is not None else None,
                    "eligible": owner_done if review else True})
    return {"feature_id": feature_id, "wave_index": wave_index, "entries": out, "notes": notes}


# ------------------------------------------------------------------ aggregate

def _changed(path: str, base: str) -> list[str]:
    found = set()
    result = worktree.run_git(["status", "--porcelain", "-uall"], cwd=path)
    for line in (result.stdout or "").splitlines():
        if len(line) > 3:
            found.add(line[3:].split(" -> ")[-1].strip())
    if base:
        diff = worktree.run_git(["diff", "--name-only", base, "HEAD"], cwd=path)
        found.update(x.strip() for x in (diff.stdout or "").splitlines() if x.strip())
    return sorted(f for f in found if not f.startswith(".spec-master/"))


def aggregate(root: str, feature_id: str, wave_index: int) -> dict:
    """Report only: changed files, pairwise conflicts, integration states. Never merges."""
    import team_workstreams
    manifest = build_manifest(root, feature_id, wave_index)
    packages = build_packages(root, feature_id)
    base = (worktree.run_git(["rev-parse", "HEAD"], cwd=root).stdout or "").strip()
    handles, notes = [], []
    for entry in manifest["entries"]:
        if entry["role"] == "sm-review":
            continue
        path = entry["worktree"] or root
        try:
            files = _changed(path, base if entry["worktree"] else "")
        except OSError as exc:
            files, _ = [], notes.append(f"{entry['package_id']}: {exc}")
        handles.append({"feature_id": entry["package_id"], "state": "created", "path": path,
                        "changed_files": files})
    result = team_workstreams.aggregate_with_verdicts(wave_index, handles, packages)
    overlaps = []
    isolated = [h for h in handles if h["path"] != root]
    for i, first in enumerate(isolated):
        for second in isolated[i + 1:]:
            try:
                files = worktree.conflicts(first["path"], second["path"])["files"]
            except OSError:
                files = []
            if files:
                overlaps.append({"a": first["feature_id"], "b": second["feature_id"], "files": files})
    result["conflicts"], result["auto_merge"], result["notes"] = overlaps, False, notes
    return result


def owns(patterns: list[str], relative: str) -> bool:
    return any(fnmatch.fnmatch(relative, pattern) for pattern in patterns)
