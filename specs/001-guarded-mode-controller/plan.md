# Implementation Plan: Guarded Mode Controller

**Branch**: `001-guarded-mode-controller` (trunk-based, no dedicated branch) | **Date**: 2026-08-17 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/001-guarded-mode-controller/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Add a deterministic controller (`spec-master/lib/controller.py` +
`execution_mode.py` + `phase_contracts.py` + `phase_runner.py`, reusing the
already-present but uncommitted `opencode_runner.py`) that can drive the
Spec Kit phase sequence one isolated session at a time, validating
required artifacts before promoting any phase, and that implements
`native`/`guarded`/`auto` mode semantics at its own CLI layer (FR-001,
FR-002). This increment ships the core fully tested and usable
standalone; it does **not** wire mode selection into the `/spec-master`
agent-level command or change `PROTOCOL.md`'s current (fully agentic)
default behavior — see `research.md` item 1 for the scoping rationale,
which follows the source spec's own phased migration plan (§19).

## Technical Context

**Language/Version**: Python 3.14 (matches this repo's interpreter; stdlib only).

**Primary Dependencies**: None (Constitution Principle II — stdlib-only).
External *processes* (not dependencies): `opencode` CLI, invoked via
`subprocess`, only when `--integration opencode` actually runs (never
required for the test suite).

**Storage**: A single JSON file, `.spec-master/state.json`, read/written
exclusively through the existing `spec-master/lib/state.py` (atomic
write-temp-then-replace, already implemented — reused, not duplicated).

**Testing**: `unittest` (stdlib), `python3 -m unittest discover -s spec-master/tests -v`.
External processes mocked via `unittest.mock` / fake-agent fixture
scripts — no real OpenCode/Ollama/network in the blocking suite.

**Target Platform**: Linux/macOS developer machines (CLI tool), same as
the rest of `spec-master/lib/`.

**Project Type**: CLI / library extension of an existing single-package
Python CLI (`spec-master/lib/`).

**Performance Goals**: Not applicable — a single-phase, batch,
human/agent-paced CLI tool; no throughput or latency target is implied by
the source spec.

**Constraints**: Deterministic and fully testable without network,
Ollama, or OpenCode (NFR); `--mode native` behavior must not change
(Constitution Principle VI); no destructive git operations
(Constitution Principle V / FR-015).

**Scale/Scope**: One project workflow at a time, up to 8 phases
(`constitution`..`validate`), `max_attempts_per_phase = 2` by default;
no concurrency across phases (explicit non-goal: "executar duas fases
simultaneamente").

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Status |
|---|---|---|
| I. Deterministic Core, Model-Agnostic Agent | New logic (`execution_mode.py`, `phase_contracts.py`, `phase_runner.py`, `controller.py`) is pure/stdlib Python under `spec-master/lib/`, exposed via CLI; no LLM call inside the core itself (only subprocesses out to `opencode`, itself mockable). | PASS |
| II. Stdlib-Only, Zero Dependencies | No new third-party dependency introduced. | PASS |
| III. Test-First, Mockable Boundaries | Every new module gets a mirrored `spec-master/tests/test_<module>.py`; `subprocess.run` is the sole external-process boundary and is mocked in tests. | PASS |
| IV. Atomic, Verifiable State Promotion | All new state (`execution`, `attempts`) written via `state_mod.save()`; no phase promoted without `phase_contracts` artifact validation. | PASS |
| V. Non-Destructive Recovery | Failed-attempt transcripts preserved under `.spec-master/logs/` (and copied to `.spec-master/failed-attempts/` on exhaustion); no `git reset --hard` anywhere in new code. | PASS |
| VI. Backwards-Compatible Evolution | `--mode native` is rejected by the *new* controller with a clear message rather than emulated — `PROTOCOL.md` and existing adapters are untouched by this increment, so native's actual behavior is unchanged. | PASS |

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
│   ├── controller.py         # NEW — run/resume/status CLI (guarded-mode entrypoint)
│   ├── execution_mode.py     # NEW — mode parsing, event classification, auto->guarded migration
│   ├── phase_contracts.py    # NEW — required-artifacts/allowlist table, snapshot/diff, placeholder + fake-tool detection (extracted + extended from opencode_runner.py)
│   ├── phase_runner.py       # NEW — thin integration-agnostic layer: resolves paths, invokes the chosen adapter, classifies events
│   ├── opencode_runner.py    # EXISTING (uncommitted) — refactored to import shared checks from phase_contracts.py instead of duplicating them; gains `validate` phase entry
│   ├── state.py              # EXISTING — reused as-is for atomic save/load; no schema-breaking change, only new top-level keys (execution, attempts)
│   └── cli.py                # EXISTING — untouched
└── tests/
    ├── fixtures/
    │   └── fake_agent.py         # NEW — shared fake-`opencode` harness used by every test file below
    ├── test_execution_mode.py    # NEW
    ├── test_phase_contracts.py   # NEW
    ├── test_phase_runner.py      # NEW
    ├── test_controller.py        # NEW (includes fake-agent integration scenarios)
    └── test_opencode_runner.py   # EXISTING (uncommitted) — extended for the `validate` phase + refactor
```

No `frontend/`, `backend/`, `api/`, `ios/`, `android/` split applies — this
is a single-package Python CLI extension, matching every existing module
under `spec-master/lib/`.

**Structure Decision**: Extend the existing single `spec-master/` package
in place, following the exact module/test-pairing convention already
observed in the repository (`discovery.py`/`test_discovery.py`,
`opencode_runner.py`/`test_opencode_runner.py`). The "suggested structure"
in `docs/spec-master/guarded-mode-spec.md` §18 is followed as-is except
for `templates/prompts/guarded/`, which is added lazily in the `tasks`
phase only if a phase actually needs a prompt skeleton distinct from the
existing `templates/prompts/*.md` (kept minimal per "não introduza
refatorações não necessárias").

## Post-Design Constitution Re-Check

Re-evaluated after Phase 1 (`data-model.md`, `contracts/cli.md`,
`quickstart.md`): the design introduces no new dependency, no destructive
operation, no change to `--mode native` behavior, and keeps
`.spec-master/state.json` as the sole atomic-write surface. All six
principles still PASS; no new complexity to justify.

## Complexity Tracking

*No Constitution Check violations — table intentionally empty.*
