# Data Model: Guarded No-op Phase Validation

Extends the `PhaseAttempt` and phase-contract shapes defined in
`specs/001-guarded-mode-controller/data-model.md` — nothing here replaces
those; this document only lists what's added or changed.

## Phase Policy (new, static — code constant in `phase_contracts.py`)

```python
PHASE_POLICY = {
    "constitution": "produce-or-update",
    "specify": "produce-or-update",
    "clarify": "inspect-or-update",
    "plan": "produce-or-update",
    "tasks": "produce-or-update",
    "analyze": "inspect-or-update",
    "implement": "execute",
    "validate": "produce-or-update",
}
```

| Policy | Meaning | Phases |
|---|---|---|
| `produce-or-update` | Must create/modify a required artifact on its first valid attempt; may pass without a new change on a retry only under the trust conditions in `research.md` item 2. | constitution, specify, plan, tasks, validate |
| `inspect-or-update` | May modify artifacts, or conclude validly with no change when the phase's deterministic no-op conditions hold. | clarify, analyze |
| `execute` | Validated against task/quality-gate completion, not the generic "did a file change" rule (unchanged from Feature 1 — `implement`'s existing checks already work this way). | implement |

## PhaseAttempt (extended)

```json
{
  "number": 3,
  "status": "PASSED",
  "reason": "valid_noop",
  "outcome": "no_changes_required",
  "contract_version": 2,
  "policy": "inspect-or-update",
  "active_artifacts": ["specs/002-guarded-noop-phase-validation/spec.md"],
  "structured_result": {"phase_result": "no_changes_required", "checks": {"needs_clarification_markers": 0, "user_decision_required": false}},
  "source": "contract_revalidation",
  "events": [],
  "transcript": ".spec-master/logs/20260818T090000Z-clarify.jsonl",
  "changed_paths": [],
  "forbidden_writes": [],
  "started_at": "2026-08-18T09:00:00Z",
  "finished_at": "2026-08-18T09:00:12Z",
  "context_hash": "..."
}
```

New/changed fields relative to Feature 1's `PhaseAttempt`:

| Field | Type | Notes |
|---|---|---|
| `outcome` | `"artifact_updated" \| "no_changes_required" \| "user_decision_required" \| "failed" \| null` | Mirrors the `phase_result` vocabulary (§6); `null` when no structured result was found (`phase_result_missing`). Distinct from `status` (`PASSED`/`FAILED`) — see `contracts/attempt-outcome.md`. |
| `contract_version` | `int` | `PHASE_CONTRACT_VERSION` at the time this attempt ran (research.md item 1). Absent on any attempt written before this feature (implicitly version 1). |
| `policy` | `"produce-or-update" \| "inspect-or-update" \| "execute"` | `PHASE_POLICY[phase]` at attempt time; stored per-attempt (not just derived from the phase name) so a future contract change is auditable per attempt. |
| `active_artifacts` | `list[str]` | The specific, feature-resolved paths this attempt validated (via `resolve_active_feature_dir`, not a raw glob) — populated for `clarify`/`analyze`; `[]` for phases still using the plain glob-based check. |
| `structured_result` | `dict \| null` | The last valid `phase_result` block `phase_result.py` extracted from the transcript, verbatim. `null` if none was found or none parsed. Evidence only — never substitutes the filesystem checks. |
| `source` | `"attempt" \| "contract_revalidation"` | `"contract_revalidation"` marks an entry created by `resume` re-evaluating a previously `BLOCKED`/`FAILED` attempt under a newer contract (§11) rather than by actually re-running the phase. |
| `reason` | (extended enum) | Now one of the eleven values in §10's table: `missing_artifact`, `placeholder_artifact`, `unchanged_artifact`, `valid_noop`, `phase_result_missing`, `phase_result_invalid`, `user_decision_required`, `forbidden_write`, `fake_tool_marker`, `timeout`, `tool_error`. `null` only alongside `status: "PASSED"` with a genuine artifact change this attempt (the pre-existing Feature 1 case). |

## Attempt budget accounting (extended)

`controller.py`'s attempt loop now counts **consumed** attempts as
`len([a for a in attempts if a["reason"] != "user_decision_required"])`,
not raw `len(attempts)`. A `user_decision_required` record is still
appended (transcript preserved, FR-011) but never counts against
`max_attempts_per_phase` — see `contracts/attempt-outcome.md`.

## Workflow status (extended)

`user_decision_required` introduces a new phase-level state distinct from
`PASSED`/`FAILED`/`BLOCKED`: **`PAUSED`**. `state.py`'s existing
`ALTERNATIVE_STATES` already includes `"PAUSED"` at the workflow level
(Feature 1 never used it) — this feature is its first real producer.
`controller.py`'s attempt loop stops immediately (does not consume a
retry) and sets the workflow status to `PAUSED` when a `clarify`/`analyze`
attempt's structured result reports `user_decision_required`, surfacing
the questions from `structured_result` to the operator.

## Active feature resolution (new — `phase_contracts.resolve_active_feature_dir`)

Input: project root. Reads `.specify/feature.json`, extracts
`feature_directory`. Rejects (raises `ActiveFeatureUnresolved`) when:

- the file is missing, unreadable, or not valid JSON;
- `feature_directory` is absent, empty, an absolute path, or contains
  `..`;
- the resolved path (`project / feature_directory`, `.resolve()`'d) is
  not contained within the resolved project root (catches a symlink
  escape the same way `phase_runner._symlink_escapes_project` does for
  Feature 1's write-detection path).

Output on success: the resolved, project-relative feature directory
(`Path`), from which `spec.md`/`plan.md`/`tasks.md` are addressed
directly (`<feature_directory>/spec.md`, etc.) instead of via
`specs/*/spec.md`.

## `phase_result` (new — `phase_result.py`)

```json
{"phase_result": "no_changes_required", "artifact": "specs/001-greeting-api/spec.md", "checks": {"needs_clarification_markers": 0, "user_decision_required": false}}
```

| Field | Type | Notes |
|---|---|---|
| `phase_result` | `"artifact_updated" \| "no_changes_required" \| "user_decision_required" \| "failed"` | Required; any other value makes the whole block invalid (ignored, not an error by itself — parsing just moves on to look for another block). |
| `artifact` | `str` | Optional, informational; never trusted as a path to operate on. |
| `checks` | `dict` | Optional, phase-specific (e.g. `needs_clarification_markers`, `user_decision_required` for `clarify`; `critical_findings`, `high_findings`, `spec_drift`, `user_decision_required` for `analyze`). Read only for the specific keys each phase's no-op predicate needs — extra/missing keys don't invalidate the block. |

`parse_last_phase_result(text: str) -> dict | None` is the only public
function — returns the dict described above, or `None` if no valid block
was found anywhere in `text`.
