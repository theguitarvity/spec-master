"""Token ledger: `.spec-master/metrics/tokens.jsonl` (docs/contracts/token-ledger-v1.md §2-§3).

One `spec-master.tokens/v1` line per model response, read incrementally from
the host's transcripts (`telemetry.read_responses`: the only transcript parser)
and attributed to feature / phase / agent through `.spec-master/events.jsonl`.
Metadata only: no prompt or response content ever reaches the ledger. A
transcript in an unknown format yields nothing plus a note, never a guessed
count. Pure stdlib; the files are append-only and the offsets file is replaced
atomically under the state lock.

Public API
    ingest(root, transcripts=None, home=None, env=None) -> {"appended", "files", "notes"}
    read(root) -> [ledger line]
    summary(root, since=None, session_id=None) -> spec-master.tokens-summary/v1
    estimate_cost(model, tokens, prices=None) -> (usd | None, "estimated" | None)
"""
from __future__ import annotations

import json
import os

import events
import state as state_mod
import telemetry

SCHEMA = "spec-master.tokens/v1"
SUMMARY_SCHEMA = "spec-master.tokens-summary/v1"
LEDGER_RELPATH = os.path.join(".spec-master", "metrics", "tokens.jsonl")
OFFSETS_RELPATH = os.path.join(".spec-master", "metrics", "tokens.offsets.json")
PRICES_RELPATH = os.path.join(".spec-master", "metrics", "prices.json")
SEEN_LIMIT = 20000  # response keys remembered for de-duplication across files and offset resets

# Documented list-price snapshot, USD per million tokens (2026-10). Longest model-id prefix wins.
# Estimates only (`cost_basis: "estimated"`); a model not matched here has `cost_usd: null`.
# Override or extend per project in `.spec-master/metrics/prices.json` (same shape).
PRICES = {
    "claude-opus-4-1": {"input": 15.0, "output": 75.0, "cache_read": 1.5, "cache_write": 18.75},
    "claude-opus-4-0": {"input": 15.0, "output": 75.0, "cache_read": 1.5, "cache_write": 18.75},
    "claude-opus-4-2025": {"input": 15.0, "output": 75.0, "cache_read": 1.5, "cache_write": 18.75},
    "claude-opus": {"input": 5.0, "output": 25.0, "cache_read": 0.5, "cache_write": 6.25},
    "claude-sonnet": {"input": 3.0, "output": 15.0, "cache_read": 0.30, "cache_write": 3.75},
    "claude-haiku": {"input": 1.0, "output": 5.0, "cache_read": 0.10, "cache_write": 1.25},
}
_PRICE_KEYS = ("input", "output", "cache_read", "cache_write")


def ledger_path(root: str) -> str:
    return os.path.join(root, LEDGER_RELPATH)


def offsets_path(root: str) -> str:
    return os.path.join(root, OFFSETS_RELPATH)


def load_prices(root: str) -> dict:
    prices = dict(PRICES)
    try:
        with open(os.path.join(root, PRICES_RELPATH), "r", encoding="utf-8") as fh:
            extra = json.load(fh)
    except (OSError, ValueError):
        return prices
    for model, row in (extra.items() if isinstance(extra, dict) else ()):
        if isinstance(row, dict) and all(isinstance(row.get(k), (int, float)) for k in _PRICE_KEYS):
            prices[str(model)] = {k: float(row[k]) for k in _PRICE_KEYS}
    return prices


def estimate_cost(model, tokens: dict, prices: dict | None = None):
    """(usd, "estimated") from the price table, or (None, None) for an unknown model."""
    table = PRICES if prices is None else prices
    matches = [name for name in table if isinstance(model, str) and model.startswith(name)]
    if not matches:
        return None, None
    row = table[max(matches, key=len)]
    usd = (tokens.get("input_tokens", 0) * row["input"] + tokens.get("output_tokens", 0) * row["output"]
           + tokens.get("cache_read_input_tokens", 0) * row["cache_read"]
           + tokens.get("cache_creation_input_tokens", 0) * row["cache_write"]) / 1_000_000
    return round(usd, 6), "estimated"


def read(root: str) -> list[dict]:
    found = []
    try:
        with open(ledger_path(root), "r", encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                try:
                    obj = json.loads(raw)
                except ValueError:
                    continue
                if isinstance(obj, dict) and obj.get("schema") == SCHEMA:
                    found.append(obj)
    except OSError:
        pass
    return found


def _load_offsets(root: str) -> dict:
    try:
        with open(offsets_path(root), "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        data = None
    if not isinstance(data, dict):
        data = {}
    files = data.get("files") if isinstance(data.get("files"), dict) else {}
    seen = data.get("seen") if isinstance(data.get("seen"), list) else []
    return {"version": 1, "files": files, "seen": [k for k in seen if isinstance(k, str)]}


def _discover(root: str, home, env) -> list[str]:
    found: list[str] = []
    for path in telemetry.locate_transcripts(root, home=home, include_subagents=True, env=env):
        found.append(path)
    for event in events.read(root):
        path = event.get("transcript_path")
        if isinstance(path, str) and path not in found:
            found.append(path)
    return found


def _agent_types(evs: list[dict]) -> dict:
    types: dict[str, str] = {}
    for event in evs:
        if event.get("type") in ("agent.started", "agent.finished") and event.get("agent_id") \
                and isinstance(event.get("agent_type"), str):
            types[event["agent_id"]] = event["agent_type"]
    return types


def ingest(root: str, transcripts=None, home=None, env=None) -> dict:
    """Append the new responses of every transcript to the ledger (idempotent)."""
    root = os.path.abspath(root)
    paths = [os.fspath(p) for p in transcripts] if transcripts is not None else _discover(root, home, env)
    notes: list[str] = []
    appended = 0
    evs = events.read(root)
    agent_types = _agent_types(evs)
    prices = load_prices(root)
    os.makedirs(os.path.dirname(ledger_path(root)), exist_ok=True)
    with state_mod.locked(offsets_path(root)):
        saved = _load_offsets(root)
        seen = dict.fromkeys(saved["seen"])
        for line in read(root):
            if line.get("request_id"):
                seen[line["request_id"]] = None
        lines = []
        for path in paths:
            entry = saved["files"].get(path) if isinstance(saved["files"].get(path), dict) else {}
            offset = entry.get("offset") if isinstance(entry.get("offset"), int) else 0
            try:
                size = os.path.getsize(path)
                if size < offset:
                    offset = 0  # rotated or truncated: read again, the seen-keys prevent duplicates
                records, new_offset = telemetry.read_responses(path, offset)
            except OSError as exc:
                notes.append(f"{path}: unreadable ({exc.strerror or exc})")
                continue
            saved["files"][path] = {"offset": new_offset}
            fresh = 0
            usable = [r for r in records if any(r["tokens"].values())]
            for record in usable:
                keys = [record["key"]] + ([record["request_id"]] if record["request_id"] else [])
                if any(key in seen for key in keys):
                    continue
                for key in keys:
                    seen[key] = None
                lines.append(_ledger_line(record, evs, agent_types, prices))
                fresh += 1
            if not usable and new_offset > offset and offset == 0:
                notes.append(f"{path}: no usage found (unknown transcript format?); nothing recorded")
        if lines:
            with open(ledger_path(root), "a", encoding="utf-8") as fh:
                for line in lines:
                    fh.write(json.dumps(line, ensure_ascii=False, separators=(",", ":")) + "\n")
        appended = len(lines)
        saved["seen"] = list(seen)[-SEEN_LIMIT:]
        state_mod.save(offsets_path(root), saved)
    return {"appended": appended, "files": len(paths), "notes": notes}


def _ledger_line(record: dict, evs: list[dict], agent_types: dict, prices: dict) -> dict:
    feature_id, phase = events.active_window(evs, record["session_id"], record["ts"])
    cost, basis = estimate_cost(record["model"], record["tokens"], prices)
    agent_id = record["agent_id"]
    return {
        "schema": SCHEMA, "ts": record["ts"], "source": telemetry.SOURCE_TRANSCRIPT,
        "session_id": record["session_id"], "request_id": record["request_id"],
        "agent_id": agent_id, "agent_type": agent_types.get(agent_id) if agent_id else None,
        "feature_id": feature_id, "phase": phase, "model": record["model"],
        **{field: record["tokens"][field] for field in telemetry.TOKEN_FIELDS},
        "output_tokens_complete": bool(record["final"]),
        "cost_usd": cost, "cost_basis": basis,
    }


# ---------------------------------------------------------------------------- summary

def _blank() -> dict:
    return {**{field: 0 for field in telemetry.TOKEN_FIELDS}, "total_tokens": 0, "cost_usd": None, "cache_hit_ratio": 0.0}


def _add(group: dict, line: dict) -> None:
    for field in telemetry.TOKEN_FIELDS:
        group[field] += line.get(field) or 0
    if isinstance(line.get("cost_usd"), (int, float)):
        group["cost_usd"] = (group["cost_usd"] or 0.0) + line["cost_usd"]


def _finish(group: dict) -> dict:
    group["total_tokens"] = group["input_tokens"] + group["output_tokens"]
    denominator = group["input_tokens"] + group["cache_read_input_tokens"] + group["cache_creation_input_tokens"]
    group["cache_hit_ratio"] = group["cache_read_input_tokens"] / denominator if denominator else 0.0
    if group["cost_usd"] is not None:
        group["cost_usd"] = round(group["cost_usd"], 6)
    return group


RECENT_WINDOW_MIN = 60


def summary(root: str, since=None, session_id=None) -> dict:
    """Aggregate of the ledger (contract §3). Cost sums only lines with a known price (null if none)."""
    floor = events.parse_ts(since) if since else None
    totals, by_feature, by_phase, by_agent, by_model = _blank(), {}, {}, {}, {}
    first = last = None
    timed = []  # (moment, tokens) for the recent burn rate
    for line in read(root):
        moment = events.parse_ts(line.get("ts"))
        if floor is not None and (moment is None or moment < floor):
            continue
        if session_id is not None and line.get("session_id") != session_id:
            continue
        _add(totals, line)
        if line.get("feature_id"):
            _add(by_feature.setdefault(line["feature_id"], _blank()), line)
            if line.get("phase"):
                _add(by_phase.setdefault(f"{line['feature_id']}:{line['phase']}", _blank()), line)
        if line.get("agent_id"):
            group = by_agent.setdefault(line["agent_id"], {"agent_type": line.get("agent_type"), **_blank()})
            group["agent_type"] = group["agent_type"] or line.get("agent_type")
            _add(group, line)
        _add(by_model.setdefault(line.get("model") or "unknown", _blank()), line)
        if moment is not None:
            timed.append((moment, (line.get("input_tokens") or 0) + (line.get("output_tokens") or 0)))
            if first is None or moment < first[0]:
                first = (moment, line["ts"])
            if last is None or moment > last[0]:
                last = (moment, line["ts"])
    _finish(totals)
    minutes = (last[0] - first[0]).total_seconds() / 60 if first and last else 0.0
    # the whole-window rate dilutes over idle days; the recent rate is the last hour up to the newest line
    recent = sum(n for moment, n in timed if (last[0] - moment).total_seconds() <= RECENT_WINDOW_MIN * 60) if last else 0
    return {
        "schema": SUMMARY_SCHEMA,
        "totals": totals,
        "by_feature": {key: _finish(group) for key, group in by_feature.items()},
        "by_phase": {key: _finish(group) for key, group in by_phase.items()},
        "by_agent": {key: _finish(group) for key, group in by_agent.items()},
        "by_model": {key: _finish(group) for key, group in by_model.items()},
        "burn_rate_tokens_per_min": round(totals["total_tokens"] / minutes, 3) if minutes > 0 else 0.0,
        "recent_burn_rate_tokens_per_min": round(recent / RECENT_WINDOW_MIN, 3),
        "recent_window_minutes": RECENT_WINDOW_MIN,
        "window": {"first_ts": first[1] if first else None, "last_ts": last[1] if last else None},
    }
