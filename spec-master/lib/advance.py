"""Helpers for `state advance`: the composite phase-boundary command (roadmap P1).

One call moves a phase, optionally records the round and the traceability rows,
and answers with the next step (phase, status, model/effort hint). The state
transition itself stays in `cli._transition` (same evidence rules as `state
transition`); this module only validates the extra inputs and builds the answer.
The name is `advance` because the kernel already owns a lane API called `step`.

Pure stdlib, no subprocess.
"""
from __future__ import annotations

import json

import metrics
import metrics_export
import risk_profile
import state as state_mod

DEFAULT_TIER = "M"


def _loads(text: str, what: str):
    try:
        return json.loads(text)
    except ValueError as exc:
        raise ValueError(f"{what} is not valid JSON: {exc}") from exc


def parse_round(text: str) -> dict:
    """The `--round-json` object: round_id, started_at, ended_at (+ optional fields)."""
    data = _loads(text, "--round-json")
    if not isinstance(data, dict):
        raise ValueError("--round-json must be a JSON object")
    return data


def parse_rows(text: str) -> list[dict]:
    """The `--trace-json` list of traceability rows."""
    data = _loads(text, "--trace-json")
    if not isinstance(data, list) or not all(isinstance(row, dict) for row in data):
        raise ValueError("--trace-json must be a JSON list of objects")
    return data


def build_round(data: dict, *, phase: str, feature_id: str, tier: str | None) -> dict:
    """A validated metrics row for the phase being closed. Token usage is taken
    from the object only when given; source defaults to `manual` (stored as
    `manual-unverified` without tokens), never invented."""
    missing = [key for key in ("round_id", "started_at", "ended_at") if not data.get(key)]
    if missing:
        raise ValueError("--round-json needs " + ", ".join(missing))
    row = metrics.record_round(
        round_id=str(data["round_id"]),
        phase=str(data.get("phase") or phase),
        started_at=str(data["started_at"]),
        ended_at=str(data["ended_at"]),
        input_tokens=int(data.get("input_tokens", 0)),
        output_tokens=int(data.get("output_tokens", 0)),
        work_packages_completed=int(data.get("work_packages_completed", 0)),
        features_completed=int(data.get("features_completed", 0)),
        notes=data.get("notes"),
        feature_id=data.get("feature_id") or feature_id,
        tier=data.get("tier") or tier,
        source=data.get("source") or "manual",
    )
    report = metrics_export.validate_rounds([row])
    if not report["valid"]:
        raise ValueError("--round-json is not a valid round: "
                         + "; ".join(f"{e['path'] or '/'}: {e['message']}" for e in report["errors"]))
    return row


def feature_tier(feature: dict) -> str:
    risk = feature.get("risk")
    tier = risk.get("tier") if isinstance(risk, dict) else None
    try:
        return risk_profile.normalize_tier(tier)
    except ValueError:
        return DEFAULT_TIER


def next_block(feature: dict) -> dict | None:
    """What to do next for the feature, or None when every phase is done."""
    phase = state_mod.next_phase(feature)
    if phase is None:
        return None
    tier = feature_tier(feature)
    profile = risk_profile.profile_for(tier)
    block = {
        "phase": phase,
        "status": (feature.get("phases") or {}).get(phase, "PENDING"),
        "tier": tier,
        "hint": risk_profile.hint_for(tier, phase),
    }
    if phase in state_mod.SKIPPABLE_PHASES:
        block[phase] = profile.get(phase)
    return block
