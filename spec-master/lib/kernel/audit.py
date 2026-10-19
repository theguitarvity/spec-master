"""Hooks audit: what the hooks would have blocked while they only watch.

hookd appends every decision to `.spec-master/hooks/decisions.jsonl`, a
gitignored log that lives only as long as the machine or container that
wrote it. `report()` summarizes it per session. `save()` also keeps a
redacted summary per session in `.spec-master/hooks/audit.jsonl`, a
committed file, so an audit made of short-lived cloud sessions still adds
up.

The audit decides when the hooks may start blocking: after the period
(14 days by default) and with false blocks at or below 2% of decisions.
A block is a decision that stops the agent (deny, or a Stop/PostToolUse
block); an ask only prompts the user and is counted apart. A false block
needs a human to judge it: every flagged decision that should have been
allowed is one. When even the block rate is within 2%, the criterion holds
whatever the review finds.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import json
import os
import re
import tempfile

import state as state_mod

DECISIONS_RELPATH = os.path.join(".spec-master", "hooks", "decisions.jsonl")
SUMMARY_RELPATH = os.path.join(".spec-master", "hooks", "audit.jsonl")
POLICY_RELPATH = os.path.join(".spec-master", "policy.json")
PERIOD_DAYS = 14
FALSE_BLOCK_TARGET = 0.02
FLAGGED_PER_SESSION = 50
TARGET_CHARS = 160
UNKNOWN_SESSION = "unknown"
BLOCKING = ("deny", "block", "escalate")

# Credentials that may appear in a command line never reach the committed summary.
_REDACTIONS = (
    (re.compile(r"(://)[^/\s@]+@"), r"\1***@"),  # https://user:token@host, https://token@host
    (re.compile(r"(?i)(authorization\s*:\s*)(?:(?:bearer|token|basic)\s+)?[^\s\"']+"), r"\1***"),
    (re.compile(r"(?i)(--?[\w-]*(?:token|secret|password|passwd|api[-_]?key|access[-_]?key)(?:=|\s+))[^\s\"']+"),
     r"\1***"),
    (re.compile(r"(?i)\b([A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|PASSWD|API_KEY|ACCESS_KEY|PRIVATE_KEY)[A-Z0-9_]*=)"
                r"[^\s\"'&]+"), r"\1***"),
    (re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}|\bgithub_pat_[A-Za-z0-9_]{20,}|"
                r"\bsk-[A-Za-z0-9_-]{20,}|\bxox[abprs]-[A-Za-z0-9-]{10,}|\bAKIA[0-9A-Z]{16}\b"), "***"),
)


def redact(text: str) -> str:
    text = str(text or "")
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text if len(text) <= TARGET_CHARS else text[: TARGET_CHARS - 1] + "…"


def _read_lines(path: str) -> list[dict]:
    if not os.path.isfile(path):
        return []
    entries = []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                entry = json.loads(line)
            except ValueError:
                continue  # a torn write never hides the rest of the log
            if isinstance(entry, dict):
                entries.append(entry)
    return entries


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))]


def summarize_session(session: str, entries: list[dict]) -> dict:
    decisions: dict[str, int] = {}
    events: dict[str, int] = {}
    kinds: dict[str, int] = {}
    flagged = []
    elapsed = []
    modes = set()
    for entry in entries:
        decision = str(entry.get("decision") or "allow")
        decisions[decision] = decisions.get(decision, 0) + 1
        event = str(entry.get("event") or "")
        events[event] = events.get(event, 0) + 1
        modes.add(entry.get("mode"))
        if isinstance(entry.get("elapsed_ms"), (int, float)):
            elapsed.append(float(entry["elapsed_ms"]))
        if decision != "allow":
            kind = f"{decision} {entry.get('tool') or event}"
            kinds[kind] = kinds.get(kind, 0) + 1
            flagged.append({"at": entry.get("at"), "event": event, "tool": entry.get("tool"),
                            "decision": decision, "reason": redact(entry.get("reason")),
                            "target": redact(entry.get("target"))})
    stamps = sorted(str(entry["at"]) for entry in entries if entry.get("at"))
    return {
        "session": session,
        "from": stamps[0] if stamps else None,
        "to": stamps[-1] if stamps else None,
        "modes": sorted(m for m in modes if m),
        "decisions": decisions,
        "events": events,
        "flagged_kinds": kinds,
        "flagged_total": len(flagged),
        "flagged": flagged[-FLAGGED_PER_SESSION:],
        "elapsed_ms": {"p50": _percentile(elapsed, 0.5), "p95": _percentile(elapsed, 0.95),
                       "max": max(elapsed) if elapsed else None},
    }


def local_sessions(root: str) -> dict[str, dict]:
    """Per-session summaries of this machine's log. The host sends a
    session id with every hook call; entries without one come from manual
    runs (tests, experiments) and are not part of the audit."""
    grouped: dict[str, list[dict]] = {}
    for entry in _read_lines(os.path.join(root, DECISIONS_RELPATH)):
        grouped.setdefault(str(entry.get("session") or UNKNOWN_SESSION), []).append(entry)
    return {session: summarize_session(session, entries) for session, entries in grouped.items()}


def _audited(sessions: dict[str, dict]) -> dict[str, dict]:
    return {session: summary for session, summary in sessions.items() if session != UNKNOWN_SESSION}


def saved_sessions(root: str) -> dict[str, dict]:
    return {str(s.get("session")): s for s in _read_lines(os.path.join(root, SUMMARY_RELPATH)) if s.get("session")}


def _today(now: dt.datetime | None) -> dt.date:
    return (now or dt.datetime.now(dt.timezone.utc)).date()


def period(root: str, sessions: dict[str, dict], now: dt.datetime | None = None) -> dict:
    policy = {}
    with contextlib.suppress(OSError, ValueError):
        with open(os.path.join(root, POLICY_RELPATH), "r", encoding="utf-8") as fh:
            policy = json.load(fh)
    policy = policy if isinstance(policy, dict) else {}
    started = policy.get("audit_started_at")
    if not started:
        stamps = sorted(s["from"] for s in sessions.values() if s.get("from"))
        started = stamps[0][:10] if stamps else None
    days = None
    if started:
        with contextlib.suppress(ValueError):
            days = (_today(now) - dt.date.fromisoformat(str(started)[:10])).days
    return {"mode": policy.get("hooks_mode", "audit"), "started": started, "days": days,
            "period_days": PERIOD_DAYS, "period_complete": days is not None and days >= PERIOD_DAYS}


def _write_lines(path: str, rows: list[dict]) -> None:
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=os.path.basename(path) + ".", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n")
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def save(root: str) -> str:
    """Merge this machine's sessions into the committed summary (a session
    already saved is replaced by its newer summary). Returns the path."""
    path = os.path.join(root, SUMMARY_RELPATH)
    with state_mod.locked(path):
        merged = _audited({**saved_sessions(root), **local_sessions(root)})
        _write_lines(path, sorted(merged.values(), key=lambda s: (s.get("from") or "", s["session"])))
    return path


def report(root: str, *, save_summary: bool = False, flagged_limit: int = 20,
           now: dt.datetime | None = None) -> dict:
    root = os.path.abspath(root)
    saved_path = save(root) if save_summary else None
    local = local_sessions(root)
    ignored = (local.get(UNKNOWN_SESSION) or {}).get("decisions") or {}
    sessions = _audited({**saved_sessions(root), **local})
    totals: dict[str, int] = {}
    kinds: dict[str, int] = {}
    flagged = []
    p95s = []
    for summary in sessions.values():
        for decision, count in (summary.get("decisions") or {}).items():
            totals[decision] = totals.get(decision, 0) + int(count)
        for kind, count in (summary.get("flagged_kinds") or {}).items():
            kinds[kind] = kinds.get(kind, 0) + int(count)
        flagged.extend({**item, "session": summary["session"]} for item in summary.get("flagged") or [])
        if (summary.get("elapsed_ms") or {}).get("p95") is not None:
            p95s.append(summary["elapsed_ms"]["p95"])
    total = sum(totals.values())
    would_block = sum(totals.get(decision, 0) for decision in BLOCKING)
    would_ask = totals.get("ask", 0)
    rate = round(would_block / total, 4) if total else None
    window = period(root, sessions, now)
    within = rate is not None and rate <= FALSE_BLOCK_TARGET
    if window["mode"] == "block":
        advice = "hooks already block; keep reviewing flagged decisions for false blocks"
    elif not total:
        advice = "no decisions recorded yet: the hooks run on Bash and file-write tool calls"
    elif not window["period_complete"]:
        advice = f"keep auditing until day {PERIOD_DAYS}; save a summary before each session's last commit"
    elif within:
        advice = ("period complete and at most {:.1%} of decisions would have blocked: switch to blocking "
                  "with `harness mode --mode block`").format(rate)
    else:
        advice = ("period complete: review the denials in `flagged`; if the ones that should have been allowed "
                  f"stay within {FALSE_BLOCK_TARGET:.0%} of all decisions, switch to blocking with "
                  "`harness mode --mode block`")
    if would_ask and window["mode"] != "block":
        advice += (f". {would_ask} ask(s) would prompt the user instead (e.g. git push, publishing: "
                   "Principle X); they never count as blocks")
    return {
        **window,
        "sessions": len(sessions),
        "decisions": totals,
        "total": total,
        "would_block": would_block,
        "would_ask": would_ask,
        "would_block_rate": rate,
        "false_block_target": FALSE_BLOCK_TARGET,
        "criterion_met_without_review": within,
        "flagged_kinds": dict(sorted(kinds.items(), key=lambda item: -item[1])),
        "flagged": sorted(flagged, key=lambda item: str(item.get("at") or ""))[-flagged_limit:],
        "hook_p95_ms_worst_session": max(p95s) if p95s else None,
        "ignored_without_session": sum(ignored.values()),
        "saved": saved_path,
        "next": advice,
    }
