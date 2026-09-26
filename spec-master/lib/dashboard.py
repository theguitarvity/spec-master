"""Static local dashboard for Spec Master (roadmap item 5).

One self-contained HTML file -- inline CSS, no CDN, no fonts, no network --
written to `.spec-master/reports/dashboard.html`. It is re-rendered by the
default `dashboard-refresh` hook on `phase.started`, `phase.transition` and
`workflow.status`, and on demand with `spec-master dashboard render`.

Contract
--------
* `build_model(root)` is read-only and JSON-serializable. Every data source is
  optional: a missing or corrupt source degrades to an empty section plus an
  entry in `model["errors"]`; it never raises. It creates nothing -- the graph
  store is only opened when `.spec-master/knowledge/graph` already exists,
  because `FileGraphStore.__init__` mkdirs it.
* `render_html(model, refresh=None)` is pure: model -> HTML string. Every
  dynamic string goes through `html.escape`.
* `write(root, output=None, refresh=None)` builds, renders and writes
  atomically (temp file in the target dir + `os.replace`). Default output is
  `<root>/.spec-master/reports/dashboard.html`; a relative `output` resolves
  against `root`. Returns the absolute path. It never touches state.json and
  writes only the output file (creating its parent dir if needed). A missing
  state.json renders a "not initialized" page instead of raising.

Completeness
------------
A phase is *done* when it is PASSED or SKIPPED. Per feature:
`percent = done / phases * 100` (one decimal). Global completeness is
phase-weighted: sum(done) / sum(phases) over all features, 0.0 with none.

Run state (the refresh rule)
----------------------------
The page is a static file, so it can only change when it is re-rendered, and
the controller releases `run.lock` *before* emitting `phase.transition`.
A lock-only rule would therefore write an "inactive" page between two phases
and a watching browser would stop reloading for the rest of the run. The rule:

* `running` (`active: true`): `.spec-master/run.lock` exists and is fresh
  (its `started_at` -- or its mtime -- is no older than
  `execution.phase_timeout_seconds`, default 600s), OR any feature phase is
  `RUNNING`. The page carries `<meta http-equiv="refresh" content="N">`
  (N = `refresh`, default 5s) and a spinner.
* `settling` (`active: false`): not running, the newest mtime of state.json /
  hooks/firings.jsonl is within `SETTLE_SECONDS` (120s) of render time, and
  either the workflow status is not terminal (COMPLETED/BLOCKED/FAILED/PAUSED)
  or the last logged lifecycle firing is `phase.started` (a resumed run whose
  status is still the previous terminal one). No meta refresh; a tiny inline
  script reloads every N seconds but only until generation time +
  `SETTLE_SECONDS`, so a browser keeps up across the gap between phases and
  then goes quiet by itself.
* `idle` (`active: false`): anything else. No refresh, no script.

`refresh=0` disables both the meta refresh and the settling script. This is a
heuristic over files on disk, not a process probe: a crashed agent that left
a phase `RUNNING` keeps the page in `running` until the state is fixed.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import tempfile
import time

import state as state_mod

SCHEMA = "spec-master.dashboard/v1"
DASHBOARD_RELPATH = os.path.join(".spec-master", "reports", "dashboard.html")
STATE_RELPATH = os.path.join(".spec-master", "state.json")
LOCK_RELPATH = os.path.join(".spec-master", "run.lock")
WORKSTREAMS_RELPATH = os.path.join(".spec-master", "workstreams.json")
ROUNDS_RELPATH = os.path.join(".spec-master", "metrics", "rounds.json")
FIRINGS_RELPATH = os.path.join(".spec-master", "hooks", "firings.jsonl")
GRAPH_RELPATH = os.path.join(".spec-master", "knowledge", "graph")

DEFAULT_REFRESH = 5
DEFAULT_PHASE_TIMEOUT = 600  # mirrors controller.DEFAULT_PHASE_TIMEOUT
SETTLE_SECONDS = 120
TERMINAL_STATUSES = ("COMPLETED", "BLOCKED", "FAILED", "PAUSED")
DONE_STATUSES = ("PASSED", "SKIPPED")
LIFECYCLE_EVENTS = ("phase.started", "phase.transition", "workflow.status")
TIERS = ("XS", "S", "M", "L", "XL")
MAX_DECISIONS = 10
MAX_FIRINGS = 20
MAX_MAP_CHARS = 60000
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

# status -> (css tone, glyph). Tone never travels alone: the glyph and a text
# label always accompany it.
_PHASE_STYLE = {
    "PASSED": ("good", "✓"),
    "SKIPPED": ("skip", "↷"),
    "RUNNING": ("info", "●"),
    "PENDING": ("neutral", "○"),
    "FAILED": ("crit", "✕"),
    "BLOCKED": ("serious", "!"),
}
_PHASE_ORDER = ("PASSED", "SKIPPED", "RUNNING", "BLOCKED", "FAILED", "PENDING")
_GOOD_WORDS = {"passed", "done", "completed", "complete", "merged", "approved", "applied",
               "integration_ready", "ready", "traced", "covered", "verified", "validated",
               "implemented", "tested", "accepted", "success", "succeeded", "ok"}
_BAD_WORDS = {"failed", "rejected", "error", "untraced", "missing"}
_WARN_WORDS = {"blocked", "paused", "review_pending", "integration_pending", "stale", "partial"}
_BUSY_WORDS = {"running", "in_progress", "in-progress", "active", "implementing", "validating",
               "specifying", "clarifying", "planning", "tasking", "analyzing", "discovering"}


# ---------------------------------------------------------------- helpers

def _now() -> float:
    return time.time()


def _iso(epoch: float) -> str:
    return dt.datetime.fromtimestamp(epoch, tz=dt.timezone.utc).strftime(TIMESTAMP_FORMAT)


def _parse_ts(value) -> float | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        return dt.datetime.strptime(text, TIMESTAMP_FORMAT).replace(tzinfo=dt.timezone.utc).timestamp()
    except ValueError:
        pass
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.timestamp()


def _text(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        return str(value)


def _pct(done: int, total: int) -> float:
    return round(done / total * 100, 1) if total else 0.0


def _read_json(path: str):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _mtime(path: str) -> float | None:
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


def _error(errors: list, source: str, exc: BaseException) -> None:
    errors.append({"source": source, "error": f"{type(exc).__name__}: {exc}"})


def _count(values) -> dict:
    counts: dict = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts


# ---------------------------------------------------------------- model

def _phase_status(value) -> str:
    if isinstance(value, dict):
        value = value.get("status")
    text = _text(value)
    if not text:
        return "PENDING"
    upper = text.strip().upper()
    return upper if upper in state_mod.PHASE_STATUSES else text.strip()


def _risk_tier(feature: dict) -> str | None:
    risk = feature.get("risk")
    tier = risk.get("tier") if isinstance(risk, dict) else risk
    tier = _text(tier)
    if not tier or not tier.strip():
        return None
    upper = tier.strip().upper()
    return upper if upper in TIERS else tier.strip()


def _feature_model(feature: dict, index: int) -> dict:
    raw = feature.get("phases") if isinstance(feature.get("phases"), dict) else {}
    names = list(state_mod.FEATURE_PHASES) + [p for p in raw if p not in state_mod.FEATURE_PHASES]
    phases = [{"phase": str(name), "status": _phase_status(raw.get(name))} for name in names]
    done = sum(1 for p in phases if p["status"] in DONE_STATUSES)
    running = next((p["phase"] for p in phases if p["status"] == "RUNNING"), None)
    current = running or next((p["phase"] for p in phases if p["status"] not in DONE_STATUSES), None)
    deps = feature.get("dependencies") if isinstance(feature.get("dependencies"), list) else []
    return {
        "id": _text(feature.get("id")) or f"feature-{index + 1}",
        "name": _text(feature.get("name")) or _text(feature.get("id")) or f"Feature {index + 1}",
        "status": _text(feature.get("status")),
        "dependencies": [_text(d) for d in deps if d is not None],
        "spec_directory": _text(feature.get("spec_directory")),
        "branch": _text(feature.get("branch")),
        "risk_tier": _risk_tier(feature),
        "analyze_repair_cycles": feature.get("analyze_repair_cycles")
        if isinstance(feature.get("analyze_repair_cycles"), int) else 0,
        "phases": phases,
        "current_phase": current,
        "done": done,
        "total": len(phases),
        "percent": _pct(done, len(phases)),
    }


def _attempts(state: dict) -> dict:
    raw = state.get("attempts") if isinstance(state.get("attempts"), dict) else {}
    out = {}
    for phase, attempts in raw.items():
        if not isinstance(attempts, list) or not attempts:
            continue
        last = attempts[-1] if isinstance(attempts[-1], dict) else {}
        out[str(phase)] = {
            "count": len(attempts),
            "last_status": _text(last.get("status")),
            "last_reason": _text(last.get("reason")),
        }
    return out


def _package_status(package: dict) -> str:
    status = package.get("status")
    if isinstance(status, str) and status.strip():
        return status.strip()
    try:
        import team_workstreams
        return team_workstreams.integration_state(package)
    except Exception:  # noqa: BLE001 -- optional helper, degrade to unknown
        return "unknown"


def _workstreams(root: str, errors: list) -> dict:
    empty = {"present": False, "packages": [], "by_status": {}, "by_owner": {},
             "mode": None, "technical_owner": None}
    path = os.path.join(root, WORKSTREAMS_RELPATH)
    if not os.path.isfile(path):
        return empty
    try:
        data = _read_json(path)
    except Exception as exc:  # noqa: BLE001
        _error(errors, "workstreams", exc)
        return {**empty, "present": True}
    meta = data if isinstance(data, dict) else {}
    if isinstance(data, list):
        raw = data
    elif isinstance(data.get("packages") if isinstance(data, dict) else None, list):
        raw = data["packages"]
    elif isinstance(data.get("work_packages") if isinstance(data, dict) else None, list):
        raw = data["work_packages"]
    else:
        raw = []
    packages = []
    for index, package in enumerate(raw):
        if not isinstance(package, dict):
            continue
        depends = package.get("depends_on") if isinstance(package.get("depends_on"), list) else []
        packages.append({
            "id": _text(package.get("id")) or f"package-{index + 1}",
            "title": _text(package.get("title")) or "",
            "feature_id": _text(package.get("feature_id") or package.get("feature")),
            "owner": _text(package.get("owner_agent") or package.get("owner")) or "unassigned",
            "reviewer": _text(package.get("reviewer_agent") or package.get("reviewer")),
            "status": _package_status(package),
            "depends_on": [_text(d) for d in depends if d is not None],
        })
    by_owner: dict = {}
    for package in packages:
        lane = by_owner.setdefault(package["owner"], {"total": 0, "by_status": {}, "packages": []})
        lane["total"] += 1
        lane["by_status"][package["status"]] = lane["by_status"].get(package["status"], 0) + 1
        lane["packages"].append(package["id"])
    return {
        "present": True,
        "packages": packages,
        "by_status": _count(p["status"] for p in packages),
        "by_owner": by_owner,
        "mode": _text(meta.get("mode")),
        "technical_owner": _text(meta.get("technical_owner")),
    }


def _traceability(state: dict, state_path: str, errors: list) -> dict:
    try:
        import traceability
        rows = traceability.load_rows(state, state_path)
    except Exception as exc:  # noqa: BLE001
        _error(errors, "traceability", exc)
        return {"rows": 0, "by_status": {}, "by_feature": {}}
    rows = [r for r in rows if isinstance(r, dict)]
    by_feature: dict = {}
    for row in rows:
        feature = _text(row.get("feature")) or "unassigned"
        status = _text(row.get("status")) or "unknown"
        bucket = by_feature.setdefault(feature, {"total": 0, "by_status": {}})
        bucket["total"] += 1
        bucket["by_status"][status] = bucket["by_status"].get(status, 0) + 1
    return {
        "rows": len(rows),
        "by_status": _count(_text(r.get("status")) or "unknown" for r in rows),
        "by_feature": by_feature,
    }


def _decisions(root: str, errors: list) -> tuple[list, int]:
    try:
        import decision_memory
        decisions = decision_memory.all_decisions(root)
    except Exception as exc:  # noqa: BLE001
        _error(errors, "decisions", exc)
        return [], 0
    keep = ("id", "title", "kind", "decided_by", "raised_by", "feature", "recorded_at", "adr")
    latest = [{k: _text(d.get(k)) for k in keep} for d in decisions[:MAX_DECISIONS] if isinstance(d, dict)]
    return latest, len(decisions)


def _firings(root: str, errors: list) -> list:
    try:
        import hooks
        records = hooks.read_firings(root, limit=MAX_FIRINGS)
    except Exception as exc:  # noqa: BLE001
        _error(errors, "hooks", exc)
        return []
    out = []
    for record in reversed(records):
        if not isinstance(record, dict):
            continue
        event = record.get("event") if isinstance(record.get("event"), dict) else {}
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        details = {str(k): _text(v) for k, v in payload.items()
                   if isinstance(v, (str, int, float, bool)) and v != ""}
        fired = []
        for entry in record.get("fired") or []:
            if not isinstance(entry, dict):
                continue
            result = entry.get("result") if isinstance(entry.get("result"), dict) else None
            fired.append({
                "hook": _text(entry.get("hook")),
                "action": _text(entry.get("action")),
                "error": _text(result.get("error")) if result else None,
            })
        out.append({
            "at": _text(event.get("at")),
            "type": _text(event.get("type")) or "unknown",
            "details": dict(list(details.items())[:6]),
            "fired": fired,
        })
    return out


def _metrics(root: str, errors: list) -> dict | None:
    path = os.path.join(root, ROUNDS_RELPATH)
    if not os.path.isfile(path):
        return None
    try:
        import metrics
        rounds = _read_json(path)
        if isinstance(rounds, dict) and isinstance(rounds.get("rounds"), list):
            rounds = rounds["rounds"]
        if not isinstance(rounds, list):
            raise ValueError("rounds.json is not a list of rounds")
        return metrics.summarize([r for r in rounds if isinstance(r, dict)])
    except Exception as exc:  # noqa: BLE001
        _error(errors, "metrics", exc)
        return None


def _graph(root: str, errors: list) -> dict:
    out = {"present": False, "nodes": 0, "edges": 0, "system_map": None, "truncated": False}
    if not os.path.isdir(os.path.join(root, GRAPH_RELPATH)):
        return out  # never instantiate FileGraphStore here: its constructor mkdirs
    out["present"] = True
    try:
        from graph.maps import render_system_map
        from graph.store import FileGraphStore
        graph = FileGraphStore(root).load()
        out["nodes"] = len(graph.nodes)
        out["edges"] = len(graph.edges)
        system_map = render_system_map(graph)
        if len(system_map) > MAX_MAP_CHARS:
            system_map = system_map[:MAX_MAP_CHARS]
            out["truncated"] = True
        out["system_map"] = system_map
    except Exception as exc:  # noqa: BLE001
        _error(errors, "graph", exc)
    return out


def _run_state(root: str, state: dict | None, features: list, firings: list, now: float) -> dict:
    execution = state.get("execution") if state and isinstance(state.get("execution"), dict) else {}
    timeout = execution.get("phase_timeout_seconds")
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0:
        timeout = DEFAULT_PHASE_TIMEOUT

    lock = None
    lock_path = os.path.join(root, LOCK_RELPATH)
    if os.path.isfile(lock_path):
        try:
            info = _read_json(lock_path)
        except Exception:  # noqa: BLE001 -- a torn/garbled lock still means "a run holds it"
            info = {}
        info = info if isinstance(info, dict) else {}
        started = _parse_ts(info.get("started_at"))
        if started is None:
            started = _mtime(lock_path) or now
        age = max(0.0, now - started)
        lock = {
            "phase": _text(info.get("phase")),
            "pid": info.get("pid") if isinstance(info.get("pid"), int) else None,
            "started_at": _text(info.get("started_at")),
            "age_seconds": round(age, 1),
            "stale": age > timeout,
        }

    running_phases = [f"{f['id']}:{p['phase']}" for f in features for p in f["phases"] if p["status"] == "RUNNING"]
    status = (_text(state.get("status")) or "").upper() if state else ""
    last_lifecycle = next((f["type"] for f in firings if f["type"] in LIFECYCLE_EVENTS), None)
    changes = [m for m in (_mtime(os.path.join(root, STATE_RELPATH)), _mtime(os.path.join(root, FIRINGS_RELPATH)))
               if m is not None]
    last_change = max(changes) if changes else None

    if lock and not lock["stale"]:
        run_state, reason = "running", f"run.lock held for phase {lock['phase'] or '?'}"
    elif running_phases:
        run_state, reason = "running", "phase RUNNING: " + ", ".join(running_phases)
    elif (last_change is not None and now - last_change <= SETTLE_SECONDS
          and (status not in TERMINAL_STATUSES or last_lifecycle == "phase.started")):
        run_state, reason = "settling", f"state changed {int(max(0, now - last_change))}s ago; no phase running"
    else:
        run_state = "idle"
        reason = "stale run.lock ignored" if lock else "no run.lock and no RUNNING phase"
    return {
        "state": run_state,
        "active": run_state == "running",
        "reason": reason,
        "lock": lock,
        "running_phases": running_phases,
        "phase_timeout_seconds": timeout,
        "settle_seconds": SETTLE_SECONDS,
        "last_change_at": _iso(last_change) if last_change is not None else None,
        "last_lifecycle_event": last_lifecycle,
    }


def _build(root: str) -> dict:
    root_abs = os.path.abspath(root)
    now = _now()
    errors: list = []
    state_path = os.path.join(root_abs, STATE_RELPATH)
    state = None
    state_present = os.path.isfile(state_path)
    if state_present:
        try:
            state = state_mod.load(state_path)
            if not isinstance(state, dict):
                raise ValueError("state.json is not a JSON object")
        except Exception as exc:  # noqa: BLE001
            _error(errors, "state", exc)
            state = None

    features = []
    if state:
        raw = state.get("features") if isinstance(state.get("features"), list) else []
        features = [_feature_model(f, i) for i, f in enumerate(raw) if isinstance(f, dict)]
    done = sum(f["done"] for f in features)
    total = sum(f["total"] for f in features)
    phase_totals = _count(p["status"] for f in features for p in f["phases"])
    constitution = state.get("constitution") if state and isinstance(state.get("constitution"), dict) else {}

    firings = _firings(root_abs, errors)
    decisions, decisions_total = _decisions(root_abs, errors)
    model = {
        "schema": SCHEMA,
        "generated_at": _iso(now),
        "generated_at_ms": int(now * 1000),
        "root": root_abs,
        "project": os.path.basename(root_abs.rstrip(os.sep)) or root_abs,
        "initialized": state is not None,
        "state_file": {"path": STATE_RELPATH, "present": state_present, "readable": state is not None},
        "workflow": {
            "status": _text(state.get("status")) if state else None,
            "strategy": _text(state.get("workflow")) if state else None,
            "context": _text(state.get("context")) if state else None,
            "constitution": _text(constitution.get("status")),
        },
        "completeness": {
            "done": done,
            "total": total,
            "percent": _pct(done, total),
            "features": len(features),
            "features_done": sum(1 for f in features if f["total"] and f["done"] == f["total"]),
        },
        "phase_totals": phase_totals,
        "features": features,
        "attempts": _attempts(state) if state else {},
        "workstreams": _workstreams(root_abs, errors),
        "traceability": _traceability(state, state_path, errors) if state else
        {"rows": 0, "by_status": {}, "by_feature": {}},
        "decisions": decisions,
        "decisions_total": decisions_total,
        "hooks": firings,
        "metrics": _metrics(root_abs, errors),
        "graph": _graph(root_abs, errors),
        "errors": errors,
    }
    model["run"] = _run_state(root_abs, state, features, firings, now)
    return model


def build_model(root: str) -> dict:
    """Read-only, JSON-serializable snapshot of everything the page shows. Never raises."""
    try:
        return _build(root)
    except Exception as exc:  # noqa: BLE001 -- last-resort guard; each source is guarded already
        now = _now()
        return {
            "schema": SCHEMA, "generated_at": _iso(now), "generated_at_ms": int(now * 1000),
            "root": os.path.abspath(root), "project": os.path.basename(os.path.abspath(root)),
            "initialized": False, "state_file": {"path": STATE_RELPATH, "present": False, "readable": False},
            "workflow": {"status": None, "strategy": None, "context": None, "constitution": None},
            "completeness": {"done": 0, "total": 0, "percent": 0.0, "features": 0, "features_done": 0},
            "phase_totals": {}, "features": [], "attempts": {},
            "workstreams": {"present": False, "packages": [], "by_status": {}, "by_owner": {},
                            "mode": None, "technical_owner": None},
            "traceability": {"rows": 0, "by_status": {}, "by_feature": {}},
            "decisions": [], "decisions_total": 0, "hooks": [], "metrics": None,
            "graph": {"present": False, "nodes": 0, "edges": 0, "system_map": None, "truncated": False},
            "errors": [{"source": "dashboard", "error": f"{type(exc).__name__}: {exc}"}],
            "run": {"state": "idle", "active": False, "reason": "model build failed", "lock": None,
                    "running_phases": [], "phase_timeout_seconds": DEFAULT_PHASE_TIMEOUT,
                    "settle_seconds": SETTLE_SECONDS, "last_change_at": None, "last_lifecycle_event": None},
        }


# ---------------------------------------------------------------- render

def _e(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _slug(value) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", str(value or "").lower()).strip("-") or "unknown"


def _tone(status) -> str:
    text = str(status or "")
    if text.upper() in _PHASE_STYLE:
        return _PHASE_STYLE[text.upper()][0]
    word = text.strip().lower()
    if word in _GOOD_WORDS:
        return "good"
    if word in _BAD_WORDS:
        return "crit"
    if word in _WARN_WORDS:
        return "warn"
    if word in _BUSY_WORDS:
        return "info"
    return "neutral"


def _glyph(status) -> str:
    text = str(status or "").upper()
    if text in _PHASE_STYLE:
        return _PHASE_STYLE[text][1]
    return {"good": "✓", "crit": "✕", "serious": "!", "warn": "△",
            "info": "●"}.get(_tone(status), "○")


def _badge(status, label=None) -> str:
    shown = status if label is None else label
    return (f'<span class="badge t-{_tone(status)}"><span class="g" aria-hidden="true">{_e(_glyph(status))}</span>'
            f'{_e(shown or "unknown")}</span>')


def _counts_inline(counts: dict) -> str:
    if not counts:
        return '<span class="muted">none</span>'
    items = sorted(counts.items(), key=lambda kv: (-kv[1], str(kv[0])))
    return " ".join(_badge(k, f"{k} · {v}") for k, v in items)


def _bar(segments: dict, total: int, label: str, percent: float) -> str:
    parts = []
    for status in ("PASSED", "SKIPPED", "RUNNING", "BLOCKED", "FAILED"):
        n = segments.get(status, 0)
        if n and total:
            parts.append(f'<span class="seg t-{_PHASE_STYLE[status][0]}" style="width:{n / total * 100:.3f}%" '
                         f'title="{_e(status)}: {n}"></span>')
    return (f'<div class="bar" role="progressbar" aria-valuemin="0" aria-valuemax="100" '
            f'aria-valuenow="{percent}" aria-label="{_e(label)}">{"".join(parts)}</div>')


def _section(title: str, body: str, count=None, section_id=None) -> str:
    tail = f' <span class="count">{_e(count)}</span>' if count is not None else ""
    sid = f' id="{_e(section_id)}"' if section_id else ""
    return f'<section class="panel"{sid}><h2>{_e(title)}{tail}</h2>{body}</section>'


def _empty(text: str) -> str:
    return f'<p class="muted">{_e(text)}</p>'


def _wrap(inner_html: str, cls: str, tag: str = "span") -> str:
    """`<tag class=cls>inner</tag>`, or "" when there is nothing to wrap. `inner_html` is already escaped."""
    return f'<{tag} class="{cls}">{inner_html}</{tag}>' if inner_html else ""


def _render_header(model: dict, refresh: int) -> str:
    run = model.get("run") or {}
    comp = model.get("completeness") or {}
    wf = model.get("workflow") or {}
    run_state = run.get("state", "idle")
    if run_state == "running":
        lock = run.get("lock") or {}
        what = lock.get("phase") if lock and not lock.get("stale") else ", ".join(run.get("running_phases") or [])
        indicator = (f'<span class="live"><span class="spin" aria-hidden="true"></span>'
                     f'Running{(": " + _e(what)) if what else ""}</span>')
        if refresh:
            indicator += f'<span class="muted small">auto-refresh every {refresh}s</span>'
    elif run_state == "settling":
        indicator = '<span class="live quiet"><span class="g" aria-hidden="true">◔</span>Between phases</span>'
    else:
        indicator = '<span class="live quiet"><span class="g" aria-hidden="true">○</span>Idle</span>'
    meta = []
    if wf.get("strategy"):
        meta.append(f'workflow <b>{_e(wf["strategy"])}</b>')
    if wf.get("constitution"):
        meta.append(f'constitution <b>{_e(wf["constitution"])}</b>')
    if wf.get("context"):
        meta.append(f'context <code>{_e(wf["context"])}</code>')
    status = wf.get("status")
    status_html = _badge(status) if status else _badge("unknown", "not initialized")
    return (
        '<header class="panel head">'
        '<div class="row between">'
        f'<div><p class="eyebrow">Spec Master</p><h1>{_e(model.get("project"))}</h1></div>'
        f'<div class="row gap">{status_html}{indicator}</div>'
        '</div>'
        f'<div class="progress"><div class="row between small"><span>Overall progress</span>'
        f'<span><b>{_e(comp.get("percent", 0.0))}%</b> · {_e(comp.get("done", 0))}/{_e(comp.get("total", 0))} phases'
        f' · {_e(comp.get("features_done", 0))}/{_e(comp.get("features", 0))} features</span></div>'
        f'{_bar(model.get("phase_totals") or {}, comp.get("total", 0), "Overall progress", comp.get("percent", 0.0))}</div>'
        f'<p class="muted small">{" · ".join(meta) + " · " if meta else ""}'
        f'{_e(run.get("reason"))} · generated <time datetime="{_e(model.get("generated_at"))}">'
        f'{_e(model.get("generated_at"))}</time> UTC</p>'
        '</header>'
    )


def _render_legend() -> str:
    items = "".join(
        f'<li class="badge t-{_PHASE_STYLE[s][0]}"><span class="g" aria-hidden="true">{_e(_PHASE_STYLE[s][1])}</span>'
        f'{_e(s.title())}</li>' for s in _PHASE_ORDER)
    return f'<ul class="legend" aria-label="Phase status legend">{items}</ul>'


def _render_features(model: dict) -> str:
    features = model.get("features") or []
    if not features:
        return _section("Features", _empty("No features identified yet."), 0, "features")
    cards = []
    for f in features:
        pills = "".join(
            f'<li class="pill t-{_PHASE_STYLE.get(p["status"], ("neutral", ""))[0]}" title="{_e(p["phase"])}: {_e(p["status"])}">'
            f'<span class="g" aria-hidden="true">{_e(_glyph(p["status"]))}</span>{_e(p["phase"])}'
            f'<span class="sr">: {_e(p["status"])}</span></li>'
            for p in f["phases"])
        segs = _count(p["status"] for p in f["phases"])
        tier = (f'<span class="tier" title="Risk tier">{_e(f["risk_tier"])}</span>' if f.get("risk_tier") else "")
        facts = []
        if f.get("current_phase") and f["done"] < f["total"]:
            facts.append(f'next <b>{_e(f["current_phase"])}</b>')
        if f.get("dependencies"):
            facts.append("depends on " + ", ".join(f"<code>{_e(d)}</code>" for d in f["dependencies"]))
        if f.get("analyze_repair_cycles"):
            facts.append(f'repair cycles {_e(f["analyze_repair_cycles"])}')
        if f.get("spec_directory"):
            facts.append(f'<code>{_e(f["spec_directory"])}</code>')
        cards.append(
            f'<article class="card" id="feature-{_e(_slug(f["id"]))}">'
            f'<div class="row between top"><h3>{_e(f["name"])}</h3><div class="row gap">{tier}'
            f'{_badge(f["status"]) if f.get("status") else ""}</div></div>'
            f'<p class="muted small"><code>{_e(f["id"])}</code></p>'
            f'<div class="row between small"><span>{_e(f["done"])}/{_e(f["total"])} phases</span>'
            f'<b>{_e(f["percent"])}%</b></div>'
            f'{_bar(segs, f["total"], "Progress of " + str(f["name"]), f["percent"])}'
            f'<ul class="pills">{pills}</ul>'
            f'{_wrap(" · ".join(facts), "muted small", "p")}'
            '</article>')
    body = _render_legend() + f'<div class="grid">{"".join(cards)}</div>'
    return _section("Features", body, len(features), "features")


def _render_workstreams(model: dict) -> str:
    ws = model.get("workstreams") or {}
    if not ws.get("present"):
        return _section("Workstreams", _empty("No .spec-master/workstreams.json yet (Team Mode not planned)."),
                        None, "workstreams")
    packages = ws.get("packages") or []
    if not packages:
        return _section("Workstreams", _empty("workstreams.json has no packages."), 0, "workstreams")
    by_owner: dict = {}
    for package in packages:
        by_owner.setdefault(package["owner"], []).append(package)
    lanes = []
    for owner in sorted(by_owner):
        items = "".join(
            f'<li class="pkg"><span class="row between gap"><code>{_e(p["id"])}</code>{_badge(p["status"])}</span>'
            f'{_wrap(_e(p.get("title")), "small")}'
            f'{_wrap(("after " + _e(", ".join(p["depends_on"]))) if p.get("depends_on") else "", "muted small")}'
            '</li>' for p in by_owner[owner])
        lanes.append(f'<article class="card"><div class="row between"><h3>{_e(owner)}</h3>'
                     f'<span class="count">{len(by_owner[owner])}</span></div><ul class="plain">{items}</ul></article>')
    head = f'<p class="small">{_counts_inline(ws.get("by_status") or {})}</p>'
    if ws.get("technical_owner") or ws.get("mode"):
        head += (f'<p class="muted small">mode {_e(ws.get("mode") or "?")} · technical owner '
                 f'{_e(ws.get("technical_owner") or "?")}</p>')
    return _section("Workstreams", head + f'<div class="grid">{"".join(lanes)}</div>', len(packages), "workstreams")


def _render_traceability(model: dict) -> str:
    tr = model.get("traceability") or {}
    if not tr.get("rows"):
        return _section("Traceability", _empty("No traceability rows recorded yet."), 0, "traceability")
    rows = "".join(
        f'<li class="kv"><code>{_e(feature)}</code><span>{_e(bucket["total"])} rows · '
        f'{_counts_inline(bucket["by_status"])}</span></li>'
        for feature, bucket in sorted((tr.get("by_feature") or {}).items()))
    body = f'<p class="small">{_counts_inline(tr.get("by_status") or {})}</p><ul class="plain">{rows}</ul>'
    return _section("Traceability", body, tr["rows"], "traceability")


def _render_decisions(model: dict) -> str:
    decisions = model.get("decisions") or []
    total = model.get("decisions_total") or 0
    if not decisions:
        return _section("Decisions", _empty("No decisions recorded in the knowledge graph."), 0, "decisions")
    items = []
    for d in decisions:
        meta = [x for x in (d.get("kind"), ("by " + d["decided_by"]) if d.get("decided_by") else None,
                            d.get("feature"), d.get("recorded_at")) if x]
        adr = f' · ADR <code>{_e(d["adr"])}</code>' if d.get("adr") else ""
        items.append(f'<li><b>{_e(d.get("title") or d.get("id"))}</b>'
                     f'<span class="muted small">{_e(" · ".join(meta))}{adr}</span></li>')
    note = f'<p class="muted small">latest {len(decisions)} of {total}</p>' if total > len(decisions) else ""
    return _section("Decisions", f'<ul class="plain list">{"".join(items)}</ul>{note}', total, "decisions")


def _render_hooks(model: dict) -> str:
    firings = model.get("hooks") or []
    if not firings:
        return _section("Hook activity", _empty("No hook firings logged yet."), 0, "hooks")
    items = []
    for f in firings:
        details = " ".join(f'<code>{_e(k)}={_e(v)}</code>' for k, v in (f.get("details") or {}).items())
        fired = ", ".join(
            f'{_e(x.get("hook"))}{(" " + _wrap("(failed)", "err")) if x.get("error") else ""}'
            for x in f.get("fired") or [])
        items.append(f'<li><span class="row between gap"><b>{_e(f.get("type"))}</b>'
                     f'<time class="muted small">{_e(f.get("at"))}</time></span>'
                     f'<span class="small">{details}</span>'
                     f'<span class="muted small">{("hooks: " + fired) if fired else ""}</span></li>')
    return _section("Hook activity", f'<ul class="plain list">{"".join(items)}</ul>', len(firings), "hooks")


def _render_metrics(model: dict) -> str:
    m = model.get("metrics")
    if not m:
        return _section("Delivery metrics", _empty("No metrics rounds recorded yet."), None, "metrics")
    labels = [("rounds", "Rounds"), ("features_completed", "Features completed"),
              ("work_packages_completed", "Packages completed"), ("total_tokens", "Tokens"),
              ("duration_seconds", "Duration (s)"), ("tokens_per_minute", "Tokens / min"),
              ("packages_per_hour", "Packages / h"), ("features_per_hour", "Features / h")]
    tiles = "".join(f'<div class="tile"><span class="muted small">{_e(label)}</span>'
                    f'<b>{_e(format(m.get(key, 0), ",") if isinstance(m.get(key), (int, float)) else m.get(key))}</b></div>'
                    for key, label in labels)
    return _section("Delivery metrics", f'<div class="tiles">{tiles}</div>', None, "metrics")


def _render_attempts(model: dict) -> str:
    attempts = model.get("attempts") or {}
    if not attempts:
        return ""
    items = "".join(
        f'<li class="kv"><code>{_e(phase)}</code><span>{_e(a["count"])} attempt(s) · '
        f'{_badge(a.get("last_status") or "unknown")}'
        f' {_wrap(_e(a.get("last_reason")), "muted small")}'
        '</span></li>' for phase, a in attempts.items())
    return _section("Controller attempts", f'<ul class="plain">{items}</ul>', len(attempts), "attempts")


def _render_graph(model: dict) -> str:
    g = model.get("graph") or {}
    if not g.get("present"):
        return _section("Dependency map", _empty("No knowledge graph at .spec-master/knowledge/graph."),
                        None, "graph")
    if g.get("system_map") is None:
        return _section("Dependency map", _empty("The knowledge graph could not be read."), None, "graph")
    note = '<p class="muted small">Map truncated for size.</p>' if g.get("truncated") else ""
    body = (f'<details><summary>{_e(g.get("nodes", 0))} nodes · {_e(g.get("edges", 0))} edges '
            f'— show system map</summary><pre>{_e(g["system_map"])}</pre>{note}</details>')
    return _section("Dependency map", body, None, "graph")


def _render_errors(model: dict) -> str:
    errors = model.get("errors") or []
    if not errors:
        return ""
    items = "".join(f'<li><code>{_e(e.get("source"))}</code> {_e(e.get("error"))}</li>' for e in errors)
    return (f'<section class="panel warnbox" role="status"><h2><span aria-hidden="true">△</span> '
            f'Some sources could not be read</h2><ul class="plain">{items}</ul></section>')


def _render_not_initialized(model: dict) -> str:
    sf = model.get("state_file") or {}
    if sf.get("present"):
        text = (f"{sf.get('path')} exists but could not be read, so there is no workflow to show. "
                "Fix or restore it and the next render picks it up.")
    else:
        text = (f"No {sf.get('path') or STATE_RELPATH} here yet. Initialize Spec Master for this project "
                "(`state init`) and this page fills in on the next render.")
    return _section("Not initialized", f'<p>{_e(text)}</p>', None, "not-initialized")


_CSS = """
:root{--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#6f6e69;--line:#e3e2dc;
--track:#ecebe6;--good:#0ca30c;--warn:#fab219;--serious:#ec835a;--crit:#d03b3b;--info:#2f6fd6;--neutral:#898781;
--skip:#7a9a7a;color-scheme:light dark}
@media (prefers-color-scheme:dark){:root{--page:#0d0d0d;--surface:#1a1a19;--ink:#fff;--ink2:#c3c2b7;
--muted:#9d9c95;--line:#2f2e2b;--track:#2a2a28;--info:#5b93ec;--skip:#8fae8f}}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--page);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
overflow-wrap:anywhere}
main{max-width:1120px;margin:0 auto;padding:16px;display:flex;flex-direction:column;gap:16px}
h1{font-size:1.6rem;line-height:1.2;margin:0}h2{font-size:1.05rem;margin:0 0 12px}h3{font-size:1rem;margin:0}
code{font:12.5px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--ink2)}
.panel{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:16px;min-width:0}
.head{display:flex;flex-direction:column;gap:12px}
.eyebrow{margin:0;font-size:.75rem;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.row{display:flex;align-items:center;flex-wrap:wrap}.between{justify-content:space-between;gap:8px}
.gap{gap:8px}.top{align-items:flex-start}
.muted{color:var(--muted)}.small{font-size:.85rem}.count{color:var(--muted);font-weight:400;font-size:.9rem}
p{margin:0}.panel>p+*{margin-top:8px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,280px),1fr));gap:12px;margin-top:12px}
.card{border:1px solid var(--line);border-radius:10px;padding:12px;display:flex;flex-direction:column;gap:8px;min-width:0}
.bar{display:flex;gap:2px;height:10px;border-radius:5px;background:var(--track);overflow:hidden}
.seg{display:block;height:100%;min-width:3px;background:var(--neutral)}
.seg.t-good{background:var(--good)}.seg.t-skip{background:var(--skip)}.seg.t-info{background:var(--info)}
.seg.t-serious{background:var(--serious)}.seg.t-crit{background:var(--crit)}
.progress{display:flex;flex-direction:column;gap:6px}
.pills,.legend,.plain{list-style:none;margin:0;padding:0}
.pills,.legend{display:flex;flex-wrap:wrap;gap:6px}
.pill,.badge{display:inline-flex;align-items:center;gap:5px;border-radius:999px;padding:2px 9px;font-size:.8rem;
border:1px solid var(--line);color:var(--ink);background:var(--surface);white-space:nowrap}
.badge{margin:2px 0}.g{font-weight:700;line-height:1}
.t-good{border-color:color-mix(in srgb,var(--good) 55%,transparent);background:color-mix(in srgb,var(--good) 12%,var(--surface))}
.t-good .g{color:var(--good)}
.t-skip{border-style:dashed;border-color:var(--skip)}.t-skip .g{color:var(--skip)}
.t-info{border-color:color-mix(in srgb,var(--info) 60%,transparent);background:color-mix(in srgb,var(--info) 12%,var(--surface))}
.t-info .g{color:var(--info)}
.t-warn{border-color:color-mix(in srgb,var(--warn) 70%,transparent);background:color-mix(in srgb,var(--warn) 14%,var(--surface))}
.t-warn .g{color:#b07a00}
.t-serious{border-color:color-mix(in srgb,var(--serious) 70%,transparent);background:color-mix(in srgb,var(--serious) 14%,var(--surface))}
.t-serious .g{color:var(--serious)}
.t-crit{border-color:color-mix(in srgb,var(--crit) 60%,transparent);background:color-mix(in srgb,var(--crit) 12%,var(--surface))}
.t-crit .g{color:var(--crit)}
.t-neutral .g{color:var(--neutral)}
@media (prefers-color-scheme:dark){.t-warn .g{color:var(--warn)}}
.tier{font:700 .75rem/1 ui-monospace,Menlo,monospace;padding:4px 7px;border-radius:6px;border:1px solid var(--ink2);color:var(--ink)}
.live{display:inline-flex;align-items:center;gap:8px;font-weight:600}.live.quiet{font-weight:500;color:var(--ink2)}
.spin{width:14px;height:14px;border-radius:50%;border:2px solid var(--track);border-top-color:var(--info);
animation:spin .9s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
@media (prefers-reduced-motion:reduce){.spin{animation:none;border-color:var(--info)}}
.list>li,.pkg{display:flex;flex-direction:column;gap:2px;padding:8px 0;border-top:1px solid var(--line)}
.list>li:first-child,.pkg:first-child{border-top:0;padding-top:0}
.kv{display:flex;flex-wrap:wrap;gap:4px 12px;align-items:baseline;padding:6px 0;border-top:1px solid var(--line)}
.kv:first-child{border-top:0}
.tiles{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,150px),1fr));gap:10px}
.tile{border:1px solid var(--line);border-radius:10px;padding:10px;display:flex;flex-direction:column;gap:2px}
.tile b{font-size:1.2rem;font-variant-numeric:tabular-nums}
time{white-space:nowrap}
details summary{cursor:pointer;color:var(--ink2)}
pre{margin:12px 0 0;padding:12px;border-radius:8px;background:var(--page);border:1px solid var(--line);
white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace;max-height:70vh;overflow-y:auto}
.warnbox{border-color:var(--warn)}.err{color:var(--crit)}
.sr{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);border:0}
.cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr));gap:16px}
footer{color:var(--muted);font-size:.8rem;text-align:center;padding-bottom:8px}
"""


def render_html(model: dict, refresh: int | None = None) -> str:
    """Render a model from `build_model` into one self-contained HTML page."""
    interval = DEFAULT_REFRESH if refresh is None else int(refresh)
    if interval < 0:
        raise ValueError("refresh must be >= 0 seconds")
    run = model.get("run") or {}
    head_extra = ""
    if run.get("active") and interval > 0:
        head_extra += f'<meta http-equiv="refresh" content="{interval}">'
    script = ""
    if run.get("state") == "settling" and interval > 0:
        until = int(model.get("generated_at_ms") or 0) + int(run.get("settle_seconds") or SETTLE_SECONDS) * 1000
        script = (f"<script>(function(){{if(Date.now()<{until}){{setTimeout(function(){{location.reload();}},"
                  f"{interval * 1000});}}}})();</script>")
    if model.get("initialized"):
        body = [_render_features(model), _render_workstreams(model),
                f'<div class="cols">{_render_traceability(model)}{_render_decisions(model)}</div>',
                f'<div class="cols">{_render_hooks(model)}{_render_metrics(model)}</div>',
                _render_attempts(model), _render_graph(model)]
    else:
        body = [_render_not_initialized(model),
                f'<div class="cols">{_render_hooks(model)}{_render_metrics(model)}</div>',
                _render_decisions(model), _render_graph(model)]
    return (
        "<!doctype html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<meta name="generator" content="spec-master dashboard">{head_extra}'
        f'<title>{_e(model.get("project"))} · Spec Master</title>'
        f"<style>{_CSS}</style></head>"
        f'<body data-run-state="{_e(_slug(run.get("state") or "idle"))}"><main>'
        f"{_render_header(model, interval if run.get('active') else 0)}"
        f"{_render_errors(model)}{''.join(body)}"
        f'<footer>Static snapshot of {_e(model.get("root"))} · generated {_e(model.get("generated_at"))} UTC'
        "</footer></main>"
        f"{script}</body></html>\n"
    )


# ---------------------------------------------------------------- write

def _resolve_output(root_abs: str, output: str | None) -> str:
    if not output:
        return os.path.join(root_abs, DASHBOARD_RELPATH)
    output = os.path.expanduser(output)
    return os.path.abspath(output if os.path.isabs(output) else os.path.join(root_abs, output))


def _write(root: str, output: str | None, refresh: int | None) -> tuple[str, dict]:
    root_abs = os.path.abspath(root)
    target = _resolve_output(root_abs, output)
    model = build_model(root_abs)
    page = render_html(model, refresh=refresh)
    parent = os.path.dirname(target)
    os.makedirs(parent, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=parent, prefix=".dashboard.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(page)
        os.chmod(tmp, 0o644)
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return target, model


def write(root: str, output: str | None = None, refresh: int | None = None) -> str:
    """Build, render and atomically write the dashboard. Returns its absolute path."""
    return _write(root, output, refresh)[0]


def write_summary(root: str, output: str | None = None, refresh: int | None = None) -> dict:
    """`write()` plus the one-line summary the CLI prints."""
    path, model = _write(root, output, refresh)
    return {
        "output": path,
        "features": model["completeness"]["features"],
        "completeness": model["completeness"]["percent"],
        "active": bool(model["run"]["active"]),
    }
