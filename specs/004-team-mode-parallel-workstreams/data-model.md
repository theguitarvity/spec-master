# Phase 1 Data Model: Team Mode Parallel Workstreams

## Review Verdict

Recorded on a package object at `package.review_verdict`.

| Field | Type | Notes |
|---|---|---|
| `status` | `"PENDING" \| "APPROVED" \| "REJECTED"` | Defaults to `PENDING` when absent (old `workstreams.json` files stay valid) |
| `reviewer_agent` | `str \| null` | MUST equal `package.reviewer_agent` — `record_review_verdict` rejects any other value (research.md #3) |
| `reason` | `str \| null` | Free text, required when `status == "REJECTED"` (Edge Case: rejection reason recorded, not just a boolean) |

## Integration Verdict

Recorded on a package object at `package.integration_verdict`.

| Field | Type | Notes |
|---|---|---|
| `status` | `"PENDING" \| "APPROVED" \| "REJECTED"` | Defaults to `PENDING` when absent |
| `reason` | `str \| null` | Free text, required when `status == "REJECTED"` |

No `agent` field — the approving role is always `"tech-lead"` (research.md #4), so it is not
data, it is implied by which verb the caller invokes.

## Package Integration State (derived, never stored)

`team_workstreams.integration_state(package: dict) -> str`, one of:

- `"rejected"` — either verdict's `status == "REJECTED"`
- `"review_pending"` — `review_verdict.status != "APPROVED"` (and not rejected)
- `"integration_pending"` — review is `APPROVED` but `integration_verdict.status != "APPROVED"`
- `"integration_ready"` — both verdicts are `APPROVED`

This is always computed fresh from the two verdict fields (FR-004/FR-005/SC-002) — there is no
separate `integration_state` field a caller could set directly and thereby bypass the gate.

## Workstream Aggregation Result

`worktree.aggregate()`'s existing `{wave_index, features: [...], conflicts: []}` shape
(data-model.md of `parallel-worktree-execution`), with each `features[i]` entry additionally
carrying:

| Field | Type | Notes |
|---|---|---|
| `integration_state` | `str` | One of the four values above, looked up by matching `features[i].feature_id` against the package id passed as `handle["feature_id"]` when the worktree was planned (research.md #2 — package id passed in `worktree.plan_worktree`'s `feature_id` slot) |

`aggregate_with_verdicts()` never mutates `worktree.aggregate()`'s own fields — it is a strict
read-only annotation pass (FR-008, Principle IV: derived, verifiable, no silent overwrite).
