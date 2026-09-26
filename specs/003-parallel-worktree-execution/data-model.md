# Phase 1 Data Model: Parallel Worktree Execution

**Input**: [spec.md](spec.md) Key Entities, [research.md](research.md)

## Execution Wave

| Field | Type | Notes |
|---|---|---|
| `wave_index` | int | 0-based position in the wave sequence |
| `feature_ids` | list[str] | Feature ids with no unresolved dependency at this point; order matches `features order` output for stable tie-breaking |

Derivation rule (FR-001): a feature enters wave *N* the first time every entry in its
`dependencies` list has reached `PASSED` status across waves `0..N-1`. Computed purely from
the already-ordered list returned by `feature_model.order_features()` plus each feature's own
`dependencies` — no new ordering logic, only grouping.

## Worktree Handle

| Field | Type | Notes |
|---|---|---|
| `feature_id` | str | Foreign key into `state.json.features[].id` |
| `path` | str | `.spec-master/worktrees/<feature-id>` (relative to project root) |
| `state` | enum | `created` \| `running` \| `finished` \| `conflict_pending` |
| `branch` | str \| null | Set only under `git-flow` strategy; `null` under `trunk` (Assumption: worktree still isolates the working directory even with no dedicated branch, via `git worktree add --detach`) |

Lifecycle (FR-008): a handle is only ever removed by the caller once `state` is `finished` AND
its feature's phase reached a terminal status (`PASSED`/`FAILED`/`BLOCKED`) AND aggregation has
recorded it. `created`/`running`/`conflict_pending` handles are never deleted.

Creation is idempotent (spec.md Edge Case 3, SC-003; research.md #2 idempotency note, added
during `/speckit-analyze` repair cycle 1): if `path` already exists on disk when a handle is
planned, the existing directory is reused/resumed as-is and `state` reflects its prior
progress — `plan_worktree` never recreates or deletes it first.

`resolve_project_root(handle) -> str` (research.md #5, same repair cycle) returns `handle.path`
and is the value every phase-loop call for `feature_id` MUST use as its project root, so FR-003
isolation is enforced by which path the caller passes rather than new sandboxing logic.

## Aggregation Result

| Field | Type | Notes |
|---|---|---|
| `wave_index` | int | Which wave this result covers |
| `features` | list[{feature_id, final_status, changed_files}] | Per-feature outcome (FR-006) |
| `conflicts` | list[{feature_a, feature_b, files}] | Empty list when no overlap detected (FR-007) |

No state transitions beyond the `Worktree Handle.state` enum above; `Aggregation Result` is a
write-once report row appended to `state.json` (or a dedicated report file), never mutated
after creation, consistent with Principle IV (atomic, verifiable state promotion).

## Relationships

```
Execution Wave 1..1 ──> 1..N Worktree Handle ──> 1..1 Feature (state.json)
Execution Wave 1..1 ──> 0..1 Aggregation Result
```
