# Implementation Plan: Guarded No-op Phase Validation

**Branch**: `002-guarded-noop-phase-validation` (trunk-based, no dedicated branch) | **Date**: 2026-08-18 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/002-guarded-noop-phase-validation/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Fix a real false-block bug in the Feature-1 guarded controller: `clarify`
(and, by the same logic, `analyze`) currently requires a filesystem
change every attempt, so a legitimately complete spec with nothing left
to clarify gets rejected as `missing_artifact`. This plan classifies
every phase by result policy (`produce-or-update` / `inspect-or-update` /
`execute`), adds a safe structured-result parser (`phase_result.py`) and
a precise active-feature resolver, and rewires `phase_runner.py`'s
pass/fail decision to allow a validated no-op for `inspect-or-update`
phases — without weakening any Feature-1 protection (allowlists,
snapshots, fake-tool-call/placeholder detection, timeout-always-fails).

## Technical Context

**Language/Version**: Python 3.14 (matches Feature 1; stdlib only).

**Primary Dependencies**: None (Constitution Principle II). `json`
(stdlib) for `phase_result.py`'s safe parsing — never `eval`/`exec`.

**Storage**: `.spec-master/state.json`, same file/module as Feature 1
(`state.py`, atomic writes) — this feature only adds fields to the
existing `attempts`/`execution` shapes, no new file.

**Testing**: `unittest` (stdlib), same suite
(`python3 -m unittest discover -s spec-master/tests -v`); the existing
95 tests must keep passing unchanged (regression gate).

**Target Platform**: Same as Feature 1 — Linux/macOS CLI.

**Project Type**: Same single-package Python CLI extension.

**Performance Goals**: Not applicable (unchanged from Feature 1).

**Constraints**: Must not weaken any Feature-1 guarantee (allowlist,
snapshot, fake-tool-call detection, timeout-always-fails,
Non-Destructive Recovery); the structured-result parser must never
execute transcript content; must not change GitHub Spec Kit's own
commands.

**Scale/Scope**: Two new no-op-eligible phases (`clarify`, `analyze`);
one new module (`phase_result.py`); modifications confined to
`phase_contracts.py`, `phase_runner.py`, `controller.py`.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Status |
|---|---|---|
| I. Deterministic Core, Model-Agnostic Agent | All new logic (`phase_result.py`, `PHASE_POLICY`, `resolve_active_feature_dir`, the no-op predicates) is pure/stdlib Python; no LLM call anywhere in the core. | PASS |
| II. Stdlib-Only, Zero Dependencies | `json` only, already stdlib. | PASS |
| III. Test-First, Mockable Boundaries | Every new/changed module keeps its mirrored `test_*.py`; no new external-process boundary is introduced (still only `subprocess.run`, already mocked). | PASS |
| IV. Atomic, Verifiable State Promotion | No-op promotion still requires a real filesystem-grounded validation (`phase_contracts` checks) — the structured `phase_result` block is evidence, never a substitute (research.md item 5, spec.md §6). | PASS |
| V. Non-Destructive Recovery | `resume`'s contract-revalidation appends a new attempt record; it never deletes/rewrites the original blocked entry (§11, data-model.md). | PASS |
| VI. Backwards-Compatible Evolution | `--mode native` and every Feature-1 test keep passing unchanged; new fields (`outcome`, `contract_version`, `policy`, etc.) are additive, not replacing existing `PhaseAttempt` fields. | PASS |

No violations to justify — Complexity Tracking table below is empty.

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
spec-master/
├── lib/
│   ├── phase_result.py       # NEW — safe structured-result parser (json.loads only)
│   ├── phase_contracts.py    # MODIFIED — + PHASE_POLICY, resolve_active_feature_dir,
│   │                         #            ActiveFeatureUnresolved, PHASE_CONTRACT_VERSION,
│   │                         #            clarify_result_ok/analyze_result_ok predicates
│   ├── phase_runner.py       # MODIFIED — policy-aware pass/fail decision, no-op paths
│   ├── controller.py         # MODIFIED — PAUSED state, contract-revalidation on resume,
│   │                         #            attempt-budget accounting excludes user_decision_required
│   └── (execution_mode.py, opencode_runner.py, state.py, cli.py — unchanged)
└── tests/
    ├── test_phase_result.py      # NEW
    ├── test_phase_contracts.py   # MODIFIED — + policy/active-feature/no-op-predicate tests
    ├── test_phase_runner.py      # MODIFIED — + clarify/analyze no-op decision tests
    ├── test_controller.py        # MODIFIED — + PAUSED/resume-revalidation tests
    └── (test_execution_mode.py, test_opencode_runner.py — unchanged)
```

Same single-package layout as Feature 1 — no new top-level directory.

**Structure Decision**: Modify Feature 1's modules in place rather than
adding parallel ones, since this is a bug fix to logic those modules
already own (not a new capability living beside them). The one genuinely
new responsibility — safely parsing a structured JSON block out of
free-form transcript text — gets its own small module
(`phase_result.py`) per the spec's own suggested structure (§17) and
because it has a distinct, independently-testable safety property
(never executes transcript content) worth isolating.

## Complexity Tracking

*No Constitution Check violations — table intentionally empty.*

## Post-Design Constitution Re-Check

Re-evaluated after Phase 1 (`data-model.md`, `contracts/attempt-outcome.md`,
`quickstart.md`): the design adds no dependency, no destructive
operation, and every new field on `PhaseAttempt` is additive. The
structured-result parser only ever calls `json.loads` on
brace-matched substrings — never `eval`/`exec` — satisfying the NFR
directly. All six principles still PASS.
