"""Delivery metrics helpers for Spec Master rounds.

Provenance (metrics schema v2): a row may carry `source`, saying where its
numbers came from:

- `host-transcript` / `host-headless`: measured by the host (Claude Code
  session transcript, or the `claude -p --output-format json` result), built
  by `telemetry.to_round()`;
- `manual`: typed in by a person or an agent, with non-zero tokens;
- `manual-unverified`: typed in with no token usage at all, i.e. nothing was
  measured. `record_round(source="manual")` downgrades to this automatically.

Rows without `source` are v1 rows: `metrics_export.validate_rounds` warns
about them, and `calibration` ignores the zero-token ones as unverified once
the input carries provenance (see `calibration.calibrate(require_measured=)`).
"""
from __future__ import annotations

from datetime import datetime, timezone

# Ceremony tiers (mirrors risk_profile / hooks.TIER_ORDER; kept local so this
# module stays dependency-free).
TIERS = ("XS", "S", "M", "L", "XL")

# Provenance of a round (schema v2 `source`). Order matches the schema enum.
SOURCES = ("host-transcript", "host-headless", "manual", "manual-unverified")
HOST_SOURCES = ("host-transcript", "host-headless")
UNVERIFIED_SOURCE = "manual-unverified"
# How a `cost_usd` value was obtained (schema v2 `cost_basis`).
COST_BASES = ("measured", "estimated")


def _parse_iso(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def record_round(
    *,
    round_id: str,
    phase: str,
    started_at: str,
    ended_at: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    work_packages_completed: int = 0,
    features_completed: int = 0,
    notes: str | None = None,
    feature_id: str | None = None,
    tier: str | None = None,
    source: str | None = None,
) -> dict:
    """Create a deterministic metrics row for one delivery round.

    `feature_id` / `tier` are optional attribution for per-tier calibration
    (`calibration.py`); the keys are only written when given, so rows without
    them are unchanged.

    `source` is the optional provenance (one of `SOURCES`). Like the other
    optional fields, the key is written ONLY when `source` is passed, so a
    call without it returns exactly the v1 row (existing callers and tests
    that compare whole rows are unaffected). Two rules keep rows honest:

    - `source="manual"` with input + output tokens == 0 is stored as
      `manual-unverified`: nothing was measured, so the row says so;
    - a host source (`host-transcript` / `host-headless`) with 0 tokens is
      rejected (ValueError): `metrics_export.validate_rounds` would flag
      such a row as an ERROR, so it is never produced here."""
    if tier:
        tier = str(tier).strip().upper()
        if tier not in TIERS:
            raise ValueError(f"unknown tier: {tier} (known: {', '.join(TIERS)})")
    if input_tokens < 0 or output_tokens < 0:
        raise ValueError("token counts cannot be negative")
    if work_packages_completed < 0 or features_completed < 0:
        raise ValueError("completed counts cannot be negative")

    start = _parse_iso(started_at)
    end = _parse_iso(ended_at)
    duration_seconds = max(0.0, (end - start).total_seconds())
    total_tokens = input_tokens + output_tokens

    if source is not None:
        source = str(source).strip()
        if source not in SOURCES:
            raise ValueError(f"unknown source: {source!r} (known: {', '.join(SOURCES)})")
        if source in HOST_SOURCES and total_tokens == 0:
            raise ValueError(f"source {source!r} requires measured tokens; got input + output == 0 "
                             f"(use source='manual' to record an unmeasured round as {UNVERIFIED_SOURCE!r})")
        if source == "manual" and total_tokens == 0:
            source = UNVERIFIED_SOURCE
    duration_minutes = duration_seconds / 60 if duration_seconds else 0.0

    payload = {
        "round_id": round_id,
        "phase": phase,
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_seconds": round(duration_seconds, 3),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "work_packages_completed": work_packages_completed,
        "features_completed": features_completed,
        "tokens_per_minute": round(total_tokens / duration_minutes, 3) if duration_minutes else 0.0,
        "packages_per_hour": round(work_packages_completed / (duration_seconds / 3600), 3)
        if duration_seconds
        else 0.0,
        "features_per_hour": round(features_completed / (duration_seconds / 3600), 3)
        if duration_seconds
        else 0.0,
    }
    if notes:
        payload["notes"] = notes
    if feature_id:
        payload["feature_id"] = feature_id
    if tier:
        payload["tier"] = tier
    if source is not None:
        payload["source"] = source
    return payload


def summarize(rounds: list[dict]) -> dict:
    """Summarize delivery speed and token usage across rounds."""
    total_seconds = sum(float(item.get("duration_seconds", 0)) for item in rounds)
    total_tokens = sum(int(item.get("total_tokens", 0)) for item in rounds)
    total_packages = sum(int(item.get("work_packages_completed", 0)) for item in rounds)
    total_features = sum(int(item.get("features_completed", 0)) for item in rounds)
    total_minutes = total_seconds / 60 if total_seconds else 0.0

    return {
        "rounds": len(rounds),
        "duration_seconds": round(total_seconds, 3),
        "total_tokens": total_tokens,
        "work_packages_completed": total_packages,
        "features_completed": total_features,
        "tokens_per_minute": round(total_tokens / total_minutes, 3) if total_minutes else 0.0,
        "packages_per_hour": round(total_packages / (total_seconds / 3600), 3)
        if total_seconds
        else 0.0,
        "features_per_hour": round(total_features / (total_seconds / 3600), 3)
        if total_seconds
        else 0.0,
    }
