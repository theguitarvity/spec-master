# Implementation Plan: Team Mode Parallel Workstreams

**Branch**: `004-team-mode-parallel-workstreams` (trunk-based: no dedicated branch) | **Date**: 2026-09-26 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/004-team-mode-parallel-workstreams/spec.md`

## Summary

Let Team Mode's `workstreams.json` packages run concurrently by reusing `parallel-worktree-
execution`'s existing `worktree.py` primitives at package granularity (no new wave/worktree/
conflict code, research.md #2), and add the one genuinely new capability this feature exists for:
a coded gate — `spec-master/lib/team_workstreams.py` — that records peer-review and Tech Lead
integration verdicts per package and refuses to report a package as `integration_ready` until
both are `APPROVED` (FR-004..FR-006, turning `conflict_policy.rules`' prose into enforced state).

## Technical Context

**Language/Version**: Python 3 (stdlib only), matching the rest of `spec-master/lib/`

**Primary Dependencies**: None — reuses `spec-master/lib/worktree.py` (already merged) for all
wave/worktree/conflict/aggregation mechanics; no new Python package

**Storage**: Filesystem only — verdicts are new fields on existing package objects inside
`.spec-master/workstreams.json` (research.md #1); no new file

**Testing**: `python3 -m unittest discover -s spec-master/tests -v`; verdict-gating functions are
pure (take/return the packages list) so no mocking boundary is needed for them (Principle III is
already satisfied by `test_worktree.py` for every git-touching call this feature reuses)

**Target Platform**: Same as the rest of the repo — any host with Python 3 + git; no new
platform constraint

**Project Type**: Library/CLI (extends `spec-master/lib/` + `cli.py`; does not modify
`team_model.py` or `worktree.py`)

**Performance Goals**: SC-001 — N dependency-free packages (including packages sharing a
`feature_id`) land in the same wave 100% of the time in the deterministic test suite; no new
performance goal beyond what `parallel-worktree-execution` already established, since wave/
worktree mechanics are reused unchanged

**Constraints**: No new wave/worktree/conflict/aggregate logic (research.md #2 — reuse
`worktree.py` directly); a review verdict MUST be rejected if `reviewer_agent` does not match
the package's own assigned `reviewer_agent` (research.md #3); integration verdicts have no
`agent` parameter — Team Mode's `technical_owner` is always `"tech-lead"` (research.md #4)

**Scale/Scope**: One new module (`spec-master/lib/team_workstreams.py`) exposing
`record_review_verdict`, `record_integration_verdict`, `integration_state`, and
`aggregate_with_verdicts` (a thin annotation layer over `worktree.aggregate`, not a
reimplementation) + one new `cli.py` subcommand group (`workstreams review|integrate|aggregate`);
zero changes to `team_model.py`, `worktree.py`, or their existing tests

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design below.*

| Principle | Check | Result |
|---|---|---|
| I. Deterministic Core | Verdict recording and integration-state computation are pure stdlib functions in `spec-master/lib/team_workstreams.py`, exposed via `cli.py`; judging a code diff is semantic work the orchestrating agent performs before calling the CLI verb, not something the core decides | PASS |
| II. Stdlib-Only | No new dependency | PASS |
| III. Test-First, Mockable Boundaries | `team_workstreams.py` functions are pure (no I/O, no subprocess) — no mocking boundary required; every wave/worktree/conflict call this feature reuses is already covered by `test_worktree.py`'s existing mocks | PASS |
| IV. Atomic, Verifiable State Promotion | A package's `integration_state` is derived (never manually set) from its two verdict fields — no path exists to mark a package integration-ready without both recorded `APPROVED` verdicts | PASS |
| V. Non-Destructive Recovery | A `REJECTED` or missing verdict leaves the package's worktree untouched and un-deleted (spec.md Edge Case 2); this feature adds no new deletion path | PASS |
| VI. Backwards-Compatible Evolution | `team_model.py::build_workstreams` and `test_team_model.py` are unmodified (SC-004); old `workstreams.json` files without verdict fields default to `PENDING`, not an error | PASS |
| IX. Scoped Dependency Exceptions | Not applicable — no new dependency introduced | N/A |

No violations; Complexity Tracking section below is empty.

## Project Structure

### Documentation (this feature)

```text
specs/004-team-mode-parallel-workstreams/
├── plan.md                    # This file
├── research.md                # Phase 0 output
├── data-model.md              # Phase 1 output
├── quickstart.md              # Phase 1 output
├── contracts/
│   └── cli-workstreams.md     # Phase 1 output
└── tasks.md                   # Phase 2 output (/speckit-tasks, not this command)
```

### Source Code (repository root)

```text
spec-master/
├── lib/
│   ├── team_model.py         # existing — build_workstreams(), assign_peer_review() (unchanged)
│   ├── worktree.py           # existing — compute_waves, plan_worktree, conflicts, aggregate (unchanged, reused)
│   ├── team_workstreams.py   # NEW — record_review_verdict, record_integration_verdict, integration_state, aggregate_with_verdicts
│   └── cli.py                # extended — new `workstreams` subparser group (contracts/cli-workstreams.md)
└── tests/
    └── test_team_workstreams.py   # NEW
```

**Structure Decision**: Single project (Option 1 from the template) — one new module beside
`worktree.py` and `team_model.py`, following the codebase's established one-module-per-concern
convention; no new top-level directory, no change to either existing module it builds on.

## Complexity Tracking

*No Constitution Check violations — this section intentionally left empty.*
