# Feature Specification: Speed Mode, TDD First (Standard lane)

**Feature Branch**: `017-speed-mode-tdd-first` (trunk-based, worktree-isolated)
**Created**: 2026-10-19 | **Status**: Implemented
**Input**: roadmap §6 S1 ("XGH do bem": speed with quality, TDD first); `.spec-master/context/app-features.md` Ciclo 2, Feature 17.

## Grounding (DISCOVERED_FROM_CODEBASE)

- Lanes exist; `standard` today just sends the change to the full cycle (`spec-master/lib/kernel/step.py` `begin`).
- Gate runs with evidence already exist: `kernel/verify.py` `run_gate`/`gate_commands`; phase evidence in `lib/evidence.py`.
- hookd exempts tests from the change envelope (`kernel/hookd.py` `_write_verdict`) and enforces only when `hooks_mode=block`.
- H6: the "light" analyze of XS/S (`risk_profile.py` `CEREMONY_PROFILES`) is only a label; nothing runs it.
- Kernel has about 56 LOC of budget left, so the new logic lives outside `kernel/`.

## Clarifications (autonomous, INFERRED unless noted)

- [EXPLICIT, user decision 2026-10-19] "Speed" is the proposal's Standard lane (§5.6): a deterministic analyze (`verify:pre`) replaces `/speckit.analyze` ONLY there. The full cycle keeps `/speckit.analyze` (constitution 2.0.0 Principle VII untouched). TDD RED/GREEN gates record evidence; the TDD hook blocks only when `hooks_mode=block`.
- INFERRED: the original criterion "profile refused when sensitivity is high unless override recorded" is satisfied by triage: any critical signal sends the change to the full cycle, and an override can only raise a lane (proposal §5.6), so there is no downgrade override.
- INFERRED: "implement only with green suite + detected gates" is `step end` for the Standard lane (gates detected by `quality_gates`, fail-closed).
- INFERRED: `/speckit.converge` stays the way to finish unbuilt work when the spec directory is a full Spec Kit set; the Standard card points to it.
- INFERRED (follow-up, not edited here: Feature 15 owns `risk_profile.py`): H6 is closed through `verify_pre.light_analyze`; `risk_profile` should call it where `analyze == "light"`.

## Requirements

- **FR-001** `standard begin` opens a `standard` change after triage (critical signals, questions or no git go to the full cycle) and allocates `specs/NNN-slug/`.
- **FR-002** `verify_pre.run` is the deterministic analyze: spec-lite at most 8 KB, no open question markers, at most 12 tasks, every acceptance check has a test or an existing task, DISCOVERED claims cite an existing `file:line`. It also accepts a full `spec.md` + `tasks.md` directory (no caps) and is exposed as `light_analyze` (H6).
- **FR-003** `standard red` records a RED only if the change already contains a test and the test command fails; `standard green` records a GREEN only after a RED and a passing run. Both are stored in the change record with test-file digests.
- **FR-004** `step end` for a standard change passes only with verify:pre, RED then GREEN (when production code changed), all tasks checked, files inside the envelope and spec dir, the diff still fitting the lane (else it ESCALATES to critical) and the project gates passing.
- **FR-005** PreToolUse guard: production writes in a running standard change are denied before verify:pre passes and before a RED exists; tests, docs and the spec are always allowed; the host enforces it only when `hooks_mode=block`.
- **FR-006** Native mode, the patch lane and the full cycle are unchanged; stdlib only; `doctor run --errors-only` exits 0.

## Acceptance Criteria

1. AC1 Deterministic analyze without LLM covers traceability (AC to test/task), open questions and size. (FR-002)
2. AC2 RED passes only with a new failing test; GREEN only after RED with a passing suite. (FR-003)
3. AC3 `step end` needs gates and RED-then-GREEN evidence. (FR-004)
4. AC4 TDD is enforced by the hook, only in block mode. (FR-005)
5. AC5 Sensitive or large changes are refused by the lane (full cycle). (FR-001)
6. AC6 Full cycle and native mode unchanged. (FR-006)
