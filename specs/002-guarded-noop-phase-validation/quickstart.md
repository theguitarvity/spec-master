# Quickstart: Validating Guarded No-op Phase Validation

## Prerequisites

Same as `specs/001-guarded-mode-controller/quickstart.md`: Python 3.14,
stdlib only, no real OpenCode/Ollama/network needed for the blocking
suite.

## 1. Run the full deterministic suite

```bash
python3 -m unittest discover -s spec-master/tests -v
```

Expected: the pre-existing 95 tests from Feature 1 still pass unchanged,
plus new tests covering `phase_result.py`, the `PHASE_POLICY`/
`resolve_active_feature_dir` additions to `phase_contracts.py`, the
`clarify`/`analyze` no-op paths in `phase_runner.py`, and the
`PAUSED`/`contract_revalidation` behavior in `controller.py` (spec.md
§16).

## 2. Exercise Cenário A (clarify passes without changing spec.md)

Against a fake agent scripted to leave `spec.md` untouched and emit a
`{"phase_result": "no_changes_required", "checks": {"needs_clarification_markers": 0, "user_decision_required": false}}`
block, with a complete, marker-free `spec.md` already in place: `clarify`
must reach `PASSED` / `reason: valid_noop` without any write.

## 3. Exercise Cenário B (false no-op claim is rejected)

Same fake agent script, but `spec.md` still contains
`[NEEDS CLARIFICATION]`: `clarify` must reach `FAILED` /
`reason: phase_result_invalid` — the structured claim never overrides the
filesystem check.

## 4. Exercise the regression case (Cenário G)

Simulate the real `qwen-greeting-api` sequence: `constitution` and
`specify` pass normally; `clarify`'s first attempt ends without changing
`spec.md` under the *old* (Feature-1-only) contract semantics (no
`contract_version` on that attempt record); `resume` is then invoked
under the *new* contract. Expected: `resume` re-evaluates that blocked
attempt, finds the spec already complete and marker-free, and promotes
`clarify` to `PASSED` with a new attempt entry
(`reason: valid_noop`, `source: contract_revalidation`) — without
deleting or rewriting the original blocked entry.

## 5. Inspect the final report's outcome differentiation

```bash
python3 spec-master/lib/controller.py status --project .
```

Confirm the per-attempt `outcome` field distinguishes `artifact_updated`
from `no_changes_required` in the JSON output, per acceptance criterion 9.

## Out of scope for this quickstart

The real `qwen-greeting-api` project (external to this repository) is not
run here — this quickstart validates the fix using the same
fake-agent-based test harness as Feature 1, per the NFR that tests never
depend on OpenCode/Ollama/network.
