"""Delivery metrics helpers for Spec Master rounds."""
from __future__ import annotations

from datetime import datetime, timezone


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
) -> dict:
    """Create a deterministic metrics row for one delivery round."""
    if input_tokens < 0 or output_tokens < 0:
        raise ValueError("token counts cannot be negative")
    if work_packages_completed < 0 or features_completed < 0:
        raise ValueError("completed counts cannot be negative")

    start = _parse_iso(started_at)
    end = _parse_iso(ended_at)
    duration_seconds = max(0.0, (end - start).total_seconds())
    total_tokens = input_tokens + output_tokens
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
