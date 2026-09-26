# Implementation Plan: Parallel Worktree Execution

**Branch**: `003-parallel-worktree-execution` (trunk-based: no dedicated branch) | **Date**: 2026-09-26 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/003-parallel-worktree-execution/spec.md`

## Summary

Add wave computation, isolated `git worktree` creation, and post-wave aggregation/conflict
reporting on top of the existing deterministic dependency ordering (`feature_model.py`), so
independent features in the same wave can run concurrently without touching each other's
files, while single-feature waves and non-git repos keep today's sequential behavior
byte-for-byte (FR-004, FR-005, SC-004).

## Technical Context

**Language/Version**: Python 3 (stdlib only), matching the rest of `spec-master/lib/`

**Primary Dependencies**: None — `git` binary invoked via `subprocess.run` through a single
mockable wrapper (research.md #3); no new Python package

**Storage**: Filesystem only — `.spec-master/worktrees/<feature-id>/` (research.md #2) and
`state.json`/report files already used by the rest of the core

**Testing**: `python3 -m unittest discover -s spec-master/tests -v`, mocking `subprocess.run`
for every git invocation (Principle III — no real git repo or concurrent process required)

**Target Platform**: Same as the rest of the repo — any host with Python 3 + git; no new
platform constraint

**Project Type**: Library/CLI (extends the existing `spec-master/lib/` + `cli.py`)

**Performance Goals**: SC-001 — wave wall-clock no worse than the slowest single feature in
the wave (validated via mocked timing in tests, not real benchmarking)

**Constraints**: No numeric concurrency cap in the core (research.md #1 — caller-bounded);
worktree handles for non-terminal features are never deleted (FR-008); `plan_worktree` is
idempotent — an existing worktree path is reused/resumed, never recreated (research.md #2
idempotency note, added during `/speckit-analyze` repair cycle 1); callers MUST use
`resolve_project_root()` as the phase loop's project root to satisfy FR-003 (research.md #5,
same repair cycle)

**Scale/Scope**: One new module (`worktree.py`) + one new `cli.py` subcommand group
(`worktree waves|plan|conflicts|aggregate`); no changes to `feature_model.py`'s ordering logic

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design below.*

| Principle | Check | Result |
|---|---|---|
| I. Deterministic Core | Wave computation, conflict detection, aggregation are pure/stdlib functions in `spec-master/lib/worktree.py`, exposed via `cli.py`; no semantic/LLM work added to the core | PASS |
| II. Stdlib-Only | No new dependency; `git` is an existing precondition (Assumption 4 in spec.md), not a new one | PASS |
| III. Test-First, Mockable Boundaries | Every git invocation goes through one `run_git()` wrapper (research.md #3), matching the precedent in `phase_runner.py`/`opencode_runner.py`; a mirrored `spec-master/tests/test_worktree.py` is required (Tasks phase) | PASS |
| IV. Atomic, Verifiable State Promotion | Aggregation results are write-once (data-model.md); no phase is promoted by exit code alone — the caller still validates artifacts before calling `state transition` | PASS |
| V. Non-Destructive Recovery | FR-008 (never delete non-terminal worktree) and the worktree path convention (research.md #2) directly implement this | PASS |
| VI. Backwards-Compatible Evolution | FR-004/FR-005 + SC-004 make single-feature and non-git-repo paths byte-identical to today; this feature is purely additive | PASS |
| IX. Scoped Dependency Exceptions | Not applicable — no new dependency introduced | N/A |

No violations; Complexity Tracking section below is empty.

## Project Structure

### Documentation (this feature)

```text
specs/003-parallel-worktree-execution/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md         # Phase 1 output
├── quickstart.md         # Phase 1 output
├── contracts/
│   └── cli-worktree.md   # Phase 1 output
└── tasks.md              # Phase 2 output (/speckit-tasks, not this command)
```

### Source Code (repository root)

```text
spec-master/
├── lib/
│   ├── feature_model.py   # existing — dependency graph + order_features() (unchanged)
│   ├── worktree.py        # NEW — compute_waves, plan_worktree, run_git, conflicts, aggregate
│   └── cli.py             # extended — new `worktree` subparser group (contracts/cli-worktree.md)
└── tests/
    └── test_worktree.py   # NEW — mirrors test_git_strategy.py / test_phase_runner.py mocking style
```

**Structure Decision**: Single project (Option 1 from the template) — this repository has no
frontend/backend or mobile split; the feature is one new module beside the existing
`spec-master/lib/` modules, following the codebase's established one-module-per-concern
convention exactly (no new top-level directory).

## Complexity Tracking

*No Constitution Check violations — this section intentionally left empty.*
