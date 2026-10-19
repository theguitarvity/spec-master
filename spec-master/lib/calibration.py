"""Per-tier metrics calibration for the risk-adaptive ceremony (roadmap item 16).

`risk_profile.py` sizes features with scope thresholds that start as guesses.
This module closes the loop with what delivery actually cost:

1. Rounds in `.spec-master/metrics/rounds.json` that carry `feature_id` and
   `tier` (`metrics record-round --feature-id --tier`) are grouped per
   feature. Rounds without that attribution are ignored and counted.
   Rounds with no measured usage never feed the calibration either: they are
   ignored and counted under reason "unverified" (`ignored_by_reason`):
   - `source == "manual-unverified"`, or any other `source` with 0 tokens
     (e.g. a hand-edited host row): always;
   - no `source` and 0 tokens (a v1 row nobody measured): whenever the input
     carries provenance (any row has a `source`) or `require_measured=True`.
     A purely v1 input (no row has a `source`) keeps the v1 behaviour below —
     such rows still feed the duration / round-count fallback — and the
     result flags them in `unverified_rounds_used` and `notes`.
2. Each completed feature's cost is compared with its tier's budget
   (`TIER_BUDGETS`, data): **under** = the tier underestimated the work (cost
   above the tier's budget), **over** = it overestimated it (cost well under the
   budget of the tier below), otherwise **ok**. A user override that raised a
   tier (`.spec-master/risk/overrides.jsonl`) counts as an **under** signal for
   the tier that was computed.
3. Drift = the last `window` (default 3) features of a tier all went the same
   way, e.g. "XS está custando como S há 3 features seguidas".
4. `apply` turns drift into new scope thresholds in
   `.spec-master/risk/thresholds.json` (tighten the drifting tier x0.8 when it
   is underestimated; loosen the tier below x1.25 when it is overestimated),
   keeping every limit >= 1 and the tiers monotonic, and logs the change to
   `.spec-master/risk/calibration-log.jsonl`.

Token accounting is often unavailable (adapters record 0 tokens), so each
feature falls back to wall-clock duration, then to its round count — the
result says which basis was used. This is a local feedback loop, separate from
the OpenTelemetry export (item 12). Pure stdlib; `calibrate` is read-only.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import os

import metrics
import risk_profile

TIER_ORDER = risk_profile.TIER_ORDER
LIMITED_TIERS = risk_profile.LIMITED_TIERS

# Expected cost of ONE feature per tier, per basis (upper bound). A feature
# whose cost exceeds its tier's budget was underestimated.
TIER_BUDGETS = {
    "XS": {"rounds": 7, "duration_seconds": 1800, "total_tokens": 150_000},
    "S": {"rounds": 9, "duration_seconds": 5400, "total_tokens": 400_000},
    "M": {"rounds": 12, "duration_seconds": 14400, "total_tokens": 1_000_000},
    "L": {"rounds": 16, "duration_seconds": 36000, "total_tokens": 2_500_000},
    "XL": {"rounds": 24, "duration_seconds": 86400, "total_tokens": 6_000_000},
}
BASES = ("total_tokens", "duration_seconds", "rounds")

DEFAULT_WINDOW = 3
TIGHTEN_FACTOR = 0.8   # underestimated tier: shrink its limits
LOOSEN_FACTOR = 1.25   # overestimated tier: grow the limits of the tier below
OVER_MARGIN = 0.75     # "over" = cost below 75% of the budget of the tier below
MIN_DURATION_SECONDS = 60  # below this, recorded durations are bookkeeping noise

CALIBRATION_LOG_RELPATH = os.path.join(".spec-master", "risk", "calibration-log.jsonl")
DEFAULT_ROUNDS_RELPATH = os.path.join(".spec-master", "metrics", "rounds.json")

_EPOCH = dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(value) -> dt.datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return metrics._parse_iso(value)
    except ValueError:
        return None


def _rank(tier: str) -> int:
    return TIER_ORDER.index(tier)


def _tier_or_none(value) -> str | None:
    tier = str(value or "").strip().upper()
    return tier if tier in TIER_ORDER else None


# --------------------------------------------------------------------------- I/O helpers

def load_rounds(path: str) -> list[dict]:
    """rounds.json as a list (accepts a bare list or {"rounds": [...]}); [] if absent."""
    if not os.path.isfile(path):
        return []
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict):
        data = data.get("rounds", [])
    if not isinstance(data, list):
        raise ValueError(f"{path}: expected a list of rounds")
    return [r for r in data if isinstance(r, dict)]


def log_path(root: str) -> str:
    return os.path.join(os.path.abspath(root), CALIBRATION_LOG_RELPATH)


def read_log(root: str) -> list[dict]:
    path = log_path(root)
    if not os.path.isfile(path):
        return []
    entries = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def consumed_until(root: str) -> dict:
    """{tier: timestamp} of the newest observation each past `apply` consumed,
    so drift that was already acted on does not fire again."""
    merged: dict = {}
    for entry in read_log(root):
        for tier, at in (entry.get("consumed_until") or {}).items():
            parsed = _parse(at)
            if parsed and (tier not in merged or parsed > _parse(merged[tier])):
                merged[tier] = at
    return merged


def risk_from_state(state: dict | None) -> dict:
    """{feature_id: feature["risk"]} for features already classified."""
    if not state:
        return {}
    return {f["id"]: f["risk"] for f in state.get("features", []) if f.get("id") and f.get("risk")}


# --------------------------------------------------------------------------- observations

def _costs_like(cost: float, basis: str, budgets: dict) -> str:
    for tier in TIER_ORDER:
        if cost <= budgets[tier][basis]:
            return tier
    return TIER_ORDER[-1]


def _row_tokens(row: dict) -> int:
    """total_tokens of a row (input + output when total is absent); 0 if unreadable."""
    def _count(value) -> int:
        return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0
    if "total_tokens" in row:
        return _count(row.get("total_tokens"))
    return _count(row.get("input_tokens")) + _count(row.get("output_tokens"))


def _unsourced_zero_tokens(row: dict) -> bool:
    return row.get("source") is None and _row_tokens(row) == 0


def _unverified(row: dict, require_measured: bool) -> bool:
    """True when the row carries no measured usage and must not feed calibration."""
    source = row.get("source")
    if source == metrics.UNVERIFIED_SOURCE:
        return True
    if _row_tokens(row) > 0:
        return False
    return source is not None or require_measured


def _feature_observations(rounds: list[dict], budgets: dict, risk: dict,
                          require_measured: bool) -> tuple[list[dict], dict, dict, int]:
    grouped: dict[str, list[tuple[int, dict]]] = {}
    ignored = {"unattributed": 0, "unverified": 0}
    legacy_unverified_used = 0
    for index, row in enumerate(rounds):
        if _unverified(row, require_measured):
            ignored["unverified"] += 1
            continue
        feature_id = row.get("feature_id")
        tier = _tier_or_none(row.get("tier"))
        if not feature_id or not tier:
            ignored["unattributed"] += 1
            continue
        if _unsourced_zero_tokens(row):
            legacy_unverified_used += 1
        grouped.setdefault(feature_id, []).append((index, row))

    observations = []
    basis_counts = {basis: 0 for basis in BASES}
    for feature_id, items in grouped.items():
        items.sort(key=lambda item: (_parse(item[1].get("ended_at") or item[1].get("started_at")) or _EPOCH, item[0]))
        rows = [row for _, row in items]
        tier = _tier_or_none(rows[-1].get("tier"))
        tokens = sum(int(r.get("total_tokens") or 0) for r in rows)
        duration = sum(float(r.get("duration_seconds") or 0.0) for r in rows)
        if tokens > 0:
            basis, cost = "total_tokens", float(tokens)
        elif duration >= MIN_DURATION_SECONDS:
            basis, cost = "duration_seconds", round(duration, 3)
        else:
            basis, cost = "rounds", float(len(rows))
        basis_counts[basis] += 1
        completed = any(int(r.get("features_completed") or 0) > 0 or r.get("phase") == "validate" for r in rows)
        budget = budgets[tier][basis]
        costs_like = _costs_like(cost, basis, budgets)
        note = None
        if not completed:
            direction = "pending"
        elif cost > budget:
            direction = "under"
        elif tier != TIER_ORDER[0] and cost < OVER_MARGIN * budgets[TIER_ORDER[_rank(tier) - 1]][basis]:
            direction = "over"
            scope_tier = _tier_or_none((risk.get(feature_id) or {}).get("scope_tier"))
            if scope_tier and _rank(scope_tier) < _rank(tier):
                direction = "ok"
                note = f"tier {tier} set by sensitivity/override (scope {scope_tier}); cheap delivery is expected"
        else:
            direction = "ok"
        observation = {
            "feature": feature_id,
            "tier": tier,
            "source": "rounds",
            "basis": basis,
            "cost": cost,
            "budget": budget,
            "ratio": round(cost / budget, 3) if budget else None,
            "costs_like": costs_like,
            "direction": direction,
            "completed": completed,
            "rounds": len(rows),
            "at": rows[-1].get("ended_at") or rows[-1].get("started_at"),
        }
        if note:
            observation["note"] = note
        observations.append(observation)
    return observations, ignored, basis_counts, legacy_unverified_used


def _override_observations(overrides: list[dict]) -> list[dict]:
    observations = []
    for entry in overrides or []:
        computed = _tier_or_none(entry.get("computed_tier"))
        forced = _tier_or_none(entry.get("forced_tier"))
        if entry.get("accepted") is False:
            continue  # rejected downward attempt: logged for audit, not a cost signal
        if not entry.get("feature") or not computed or not forced or _rank(forced) <= _rank(computed):
            continue
        observations.append({
            "feature": entry["feature"],
            "tier": computed,
            "source": "override",
            "costs_like": forced,
            "direction": "under",
            "completed": True,
            "reason": entry.get("reason"),
            "at": entry.get("at"),
        })
    return observations


# --------------------------------------------------------------------------- threshold scaling

def scale_tier(thresholds: dict, tier: str, factor: float) -> dict:
    """New limits for `tier` scaled by `factor`: rounded, moved by at least 1,
    never below 1 and clamped between the neighbouring tiers (monotonic)."""
    index = LIMITED_TIERS.index(tier)
    lower_tier = LIMITED_TIERS[index - 1] if index > 0 else None
    upper_tier = LIMITED_TIERS[index + 1] if index + 1 < len(LIMITED_TIERS) else None
    scaled = {}
    for signal, value in thresholds[tier].items():
        new = int(round(value * factor))
        if new == value:
            new = value + (1 if factor > 1 else -1)
        lower = max(1, thresholds[lower_tier][signal]) if lower_tier and signal in thresholds[lower_tier] else 1
        upper = thresholds[upper_tier][signal] if upper_tier and signal in thresholds[upper_tier] else None
        new = max(lower, new)
        if upper is not None:
            new = min(upper, new)
        scaled[signal] = max(1, new)
    return scaled


# --------------------------------------------------------------------------- calibrate / apply

def calibrate(rounds: list[dict], overrides: list[dict] | None = None, thresholds: dict | None = None,
              window: int = DEFAULT_WINDOW, *, budgets: dict | None = None, risk: dict | None = None,
              since: dict | None = None, require_measured: bool | None = None) -> dict:
    """Compare estimated vs actual cost per tier, flag drift, propose thresholds.

    rounds      rows of rounds.json (only rows with feature_id + tier count)
    overrides   entries of overrides.jsonl (raised tiers = "under" signals)
    thresholds  current scope thresholds (default: risk_profile defaults)
    window      consecutive same-direction features that make a drift
    risk        {feature_id: feature["risk"]} — skips "over" when the tier came
                from a sensitivity floor or override instead of scope
    since       {tier: timestamp} — ignore observations already consumed
    require_measured
                True: rows without `source` and with 0 tokens are ignored as
                unverified. False: they feed the v1 duration / round-count
                fallback. None (default): True as soon as any row carries a
                `source`, else False. `manual-unverified` rows, and sourced
                rows with 0 tokens, are ignored in every mode.
    """
    if isinstance(window, bool) or not isinstance(window, int) or window < 1:
        raise ValueError("window must be an integer >= 1")
    budgets = copy.deepcopy(budgets or TIER_BUDGETS)
    current = risk_profile.merge_thresholds(thresholds)
    risk = risk or {}
    since = since or {}
    rounds = rounds or []
    if require_measured is None:
        require_measured = any(row.get("source") is not None for row in rounds)

    feature_obs, ignored_by_reason, basis_counts, legacy_unverified_used = _feature_observations(
        rounds, budgets, risk, bool(require_measured))
    ignored = sum(ignored_by_reason.values())
    all_obs = feature_obs + _override_observations(overrides or [])

    # one observation per (tier, feature): the latest wins
    latest: dict[tuple[str, str], dict] = {}
    for obs in sorted(all_obs, key=lambda o: _parse(o.get("at")) or _EPOCH):
        latest[(obs["tier"], obs["feature"])] = obs
    observations = sorted(latest.values(), key=lambda o: (_parse(o.get("at")) or _EPOCH, _rank(o["tier"])))

    tiers: dict = {}
    drift: list[dict] = []
    recommendations: list[dict] = []
    proposed = copy.deepcopy(current)
    for tier in TIER_ORDER:
        mine = [o for o in observations if o["tier"] == tier]
        cutoff = _parse(since.get(tier))
        fresh = [o for o in mine if not cutoff or (_parse(o.get("at")) or _EPOCH) > cutoff]
        ratios = [o["ratio"] for o in mine if o.get("ratio") is not None and o["direction"] != "pending"]
        tiers[tier] = {
            "features": len(mine),
            "under": sum(o["direction"] == "under" for o in mine),
            "over": sum(o["direction"] == "over" for o in mine),
            "ok": sum(o["direction"] == "ok" for o in mine),
            "pending": sum(o["direction"] == "pending" for o in mine),
            "overrides": sum(o["source"] == "override" for o in mine),
            "mean_ratio": round(sum(ratios) / len(ratios), 3) if ratios else None,
            "budget": budgets[tier],
        }
        decided = [o for o in fresh if o["direction"] != "pending"]
        if len(decided) < window:
            continue
        tail = decided[-window:]
        direction = tail[0]["direction"]
        if direction not in ("under", "over") or any(o["direction"] != direction for o in tail):
            continue
        likes = [o["costs_like"] for o in tail]
        like = min(likes, key=_rank) if direction == "under" else max(likes, key=_rank)
        entry = {
            "tier": tier,
            "direction": direction,
            "count": window,
            "costs_like": like,
            "features": [o["feature"] for o in tail],
            "until": max((o.get("at") for o in tail if _parse(o.get("at"))), key=_parse, default=None),
            "message": f"{tier} está custando como {like} há {window} features seguidas",
        }
        if direction == "under":
            target, factor = (tier if tier in LIMITED_TIERS else None), TIGHTEN_FACTOR
            entry["suggestion"] = (f"apertar os limites de {tier} (x{TIGHTEN_FACTOR})" if target
                                   else "XL não tem limites; revise TIER_BUDGETS")
        else:
            target = TIER_ORDER[_rank(tier) - 1] if _rank(tier) > 0 else None
            factor = LOOSEN_FACTOR
            entry["suggestion"] = (f"afrouxar os limites de {target} (x{LOOSEN_FACTOR})" if target
                                   else "XS já é o menor tier; revise TIER_BUDGETS")
        drift.append(entry)
        recommendation = {"tier": tier, "direction": direction, "target_tier": target, "factor": factor,
                          "features": entry["features"], "until": entry["until"]}
        if target:
            recommendation["previous_thresholds"] = dict(proposed[target])
            proposed[target] = scale_tier(proposed, target, factor)
            recommendation["new_thresholds"] = dict(proposed[target])
        else:
            recommendation["new_thresholds"] = None
        recommendations.append(recommendation)

    errors = risk_profile.validate_thresholds(proposed)
    if errors:  # defensive: scale_tier clamps, so this should never trigger
        raise ValueError("calibration produced invalid thresholds: " + "; ".join(errors))

    notes = []
    if ignored_by_reason["unattributed"]:
        notes.append(f"{ignored_by_reason['unattributed']} round(s) sem feature_id/tier ignorados — registre com "
                     "`metrics record-round --feature-id ID --tier T`")
    if ignored_by_reason["unverified"]:
        notes.append(f"{ignored_by_reason['unverified']} round(s) sem usage medido ignorados "
                     f"(source {metrics.UNVERIFIED_SOURCE} ou 0 tokens) — não alimentam a "
                     "calibração; registre rounds com a telemetria do host")
    if legacy_unverified_used:
        notes.append(f"{legacy_unverified_used} round(s) v1 sem source e com 0 tokens usados como fallback "
                     "(duração / nº de rounds): dado não verificado; use require_measured=True para ignorá-los")
    if basis_counts["duration_seconds"]:
        notes.append(f"{basis_counts['duration_seconds']} feature(s) sem contagem de tokens: custo medido pela "
                     "duração dos rounds")
    if basis_counts["rounds"]:
        notes.append(f"{basis_counts['rounds']} feature(s) sem tokens nem duração significativa "
                     f"(< {MIN_DURATION_SECONDS}s): custo medido pelo nº de rounds")
    if not observations:
        notes.append("nenhuma feature atribuída a um tier ainda — nada para calibrar")

    return {
        "window": window,
        "rounds_used": sum(o.get("rounds", 0) for o in feature_obs),
        "ignored_rounds": ignored,
        "ignored_by_reason": ignored_by_reason,
        "require_measured": bool(require_measured),
        "unverified_rounds_used": legacy_unverified_used,
        "basis_counts": basis_counts,
        "features": observations,
        "tiers": tiers,
        "drift": drift,
        "recommendations": recommendations,
        "thresholds": current,
        "proposed_thresholds": proposed,
        "notes": notes,
    }


def apply(root: str, result: dict) -> dict:
    """Write the proposed thresholds and log the calibration. No-op when no
    recommendation has an adjustable target tier."""
    recommendations = [r for r in result.get("recommendations") or [] if r.get("target_tier")]
    if not recommendations:
        return {"applied": False, "reason": "no drift with an adjustable tier — thresholds unchanged"}
    proposed = result["proposed_thresholds"]
    errors = risk_profile.validate_thresholds(proposed)
    if errors:
        raise ValueError("refusing to apply invalid thresholds: " + "; ".join(errors))
    root = os.path.abspath(root)
    previous = risk_profile.load_thresholds(root)
    at = _now()
    consumed = {}
    for rec in result.get("recommendations") or []:
        if rec.get("until"):
            consumed[rec["tier"]] = rec["until"]

    path = risk_profile.thresholds_path(root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"version": 1, "source": "calibration", "updated_at": at, "tiers": proposed}, fh,
                  indent=2, ensure_ascii=False)
        fh.write("\n")
    entry = {
        "at": at,
        "previous": previous,
        "thresholds": proposed,
        "drift": [{k: d[k] for k in ("tier", "direction", "costs_like", "features", "message")}
                  for d in result.get("drift") or []],
        "recommendations": recommendations,
        "consumed_until": consumed,
    }
    log = log_path(root)
    with open(log, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return {"applied": True, "path": path, "log": log, "previous": previous, "thresholds": proposed,
            "recommendations": recommendations, "consumed_until": consumed}
