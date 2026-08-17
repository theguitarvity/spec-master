---
description: "Task list for Guarded Mode Controller"
---

# Tasks: Guarded Mode Controller

**Input**: Design documents from `specs/001-guarded-mode-controller/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/cli.md, quickstart.md

**Tests**: Required, not optional — `docs/spec-master/guarded-mode-spec.md` §16 mandates 14
unit tests and 8 fake-agent integration scenarios, and Constitution Principle III
("Test-First, Mockable Boundaries") applies. Every task below that adds behavior
has a paired test task; test tasks are written to fail before their implementation
task lands.

**Organization**: Tasks are grouped by user story (US1-US4 from `spec.md`) after a
shared Setup/Foundational phase, since every user story depends on the same
`phase_contracts.py`/`phase_runner.py` primitives.

**Out of scope for this task list** (see `research.md` item 1): wiring `--mode`
into the `/spec-master` agent-level command, any `PROTOCOL.md`/adapter change, and
the real-model `qwen-todo-api` smoke test.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1-US4)

## Phase 1: Setup

- [X] T001 Create `spec-master/tests/fixtures/fake_agent.py`: a small stdlib-only
      script that stands in for `opencode run` in tests. It reads a JSON
      "script" (env var `FAKE_AGENT_SCRIPT` or `--script-file` arg) describing
      what to write/print, and is invoked by `unittest.mock.patch`-ed
      `subprocess.run` calls across every test file below (shared infra for
      US1-US4).

## Phase 2: Foundational (Blocking Prerequisites)

**⚠️ CRITICAL**: No user story task can begin until this phase is complete.

- [X] T002 Extract `PHASE_ARTIFACTS`, `PHASE_ALLOWED_WRITES`, `FAKE_TOOL_MARKERS`,
      `validate_transcript()`, `snapshot()`, `changed_paths()`,
      `forbidden_writes()`, `placeholder_artifacts()` from
      `spec-master/lib/opencode_runner.py` into new `spec-master/lib/phase_contracts.py`.
      Add a `validate` phase entry to `PHASE_ARTIFACTS`
      (`.spec-master/reports/traceability.md`) and `PHASE_ALLOWED_WRITES`
      (`.spec-master/reports/*`). Add module-level `PROTECTED_PATHS`
      (`.git/*`, `spec-master/*`, `.spec-master/state.json`,
      `.spec-master/logs/*`, `.spec-master/failed-attempts/*`). Generalize
      `placeholder_artifacts()` to the regex `\[[A-Z][A-Z0-9_]*\]` (research.md
      item 5) instead of the literal `"[PROJECT_NAME]"` check. Extend
      `snapshot()`'s ignore list per research.md item 7 (`.git/`, `__pycache__/`,
      `.venv/`, `venv/`, `node_modules/` at any depth,
      `.spec-master/failed-attempts/`, `.spec-master/state.json`). Update
      `spec-master/lib/opencode_runner.py` to `import phase_contracts` and use
      these instead of its own copies — no behavioral change to the existing
      functions it keeps (the `run()` CLI entrypoint, `build_parser()`, `main()`).
- [X] T003 [P] `spec-master/tests/test_phase_contracts.py`: allowlist rejection
      (unit test §16-5), placeholder detection via the generalized regex
      (§16-6), fake-tool-marker detection (§16-7), snapshot ignoring
      `.venv`/`__pycache__`/caches (§16-13).
- [X] T004 Create `spec-master/lib/execution_mode.py`: `MODES = ("native", "guarded", "auto")`;
      `parse_mode(value)` (`None`/omitted → `"auto"`, GM-001/GM-002);
      `init_execution(state, requested_mode, integration, model)` (writes
      `state["execution"]` per `data-model.md`); `record_event(state, event_type, timestamp)`
      classifying each event type as critical or recoverable per `data-model.md`
      Events, incrementing `state["execution"]["recoverable_event_count"]`
      (cumulative across the whole workflow — Clarified 2026-08-17) for
      recoverable events; `maybe_migrate(state, reason, timestamp)` appending a
      `ModeTransition` and flipping `active_mode` from `"native"` to `"guarded"`
      when a critical event fired or the recoverable counter reaches 2, and
      never migrating back or migrating at all when `active_mode` is already
      `"guarded"` or `requested_mode == "native"`.
- [X] T005 [P] `spec-master/tests/test_execution_mode.py`: parsing the three modes
      (§16-1), default mode is `auto` (§16-2), `native -> guarded` on a single
      critical event (§16-3), migration after two recoverable events
      accumulated across (not reset between) phases (§16-4, per the
      2026-08-17 clarification), and no reversion back to `native` after
      migration.
- [X] T006 Create `spec-master/lib/phase_runner.py`: `run_phase(project, phase,
      integration, model, prompt_text, attempt_number, timeout_seconds, agent="spec-phase")`.
      Resolves every path in the before/after snapshot diff to an absolute
      path and rejects (as the critical event `out_of_project_write`) any
      that escapes `project`. Classifies `phase_contracts` findings into
      `execution_mode` event-type strings per `research.md` item 4: a
      forbidden write in a pre-`implement` phase whose path extension looks
      like source code (not already implied by that phase's own allowlist)
      → `early_implementation` (critical, §16-8); any other forbidden write
      → `wrong_path` (recoverable); fake tool markers →
      `simulated_tool_call` (critical); missing required artifact on an
      exit-0 attempt → `false_phase_completion` (critical); leftover
      placeholder → `placeholder_not_removed` (recoverable); a required
      artifact's basename found at an unexpected path instead of its
      canonical glob location → `artifact_wrong_location` (recoverable);
      a non-zero exit with none of the above conditions →
      `recoverable_tool_error` (recoverable). `rejected_transition_skip`
      and `skill_reentry` are accepted by `execution_mode.record_event`
      (T004) but intentionally have no producer here — see `data-model.md`
      "Producibility this increment" (analyze finding H1). Maintains an
      `INTEGRATIONS = {"opencode": opencode_runner_invoke}` registry and
      raises a clear `ValueError` for any other `--integration` value
      (GM-012 — only OpenCode implemented this increment).
- [X] T007 [P] `spec-master/tests/test_phase_runner.py`: early-implementation
      detection during `constitution` (§16-8, matches integration scenario
      §16-3: fake agent creates `src/app.py`), out-of-project write
      rejection, `artifact_wrong_location` when a required artifact appears
      at the wrong path, `recoverable_tool_error` for an ordinary non-zero
      exit, and `ValueError` for an unsupported `--integration`.

**Checkpoint**: `phase_contracts.py`, `execution_mode.py`, `phase_runner.py` exist
and are independently tested. User story work can begin.

## Phase 3: User Story 1 — Run a workflow protected against an unreliable model (Priority: P1) 🎯 MVP

**Goal**: `controller.py run --mode guarded` never promotes a phase to
`PASSED` without validating its artifact, retries within a bounded attempt
budget, and gives up cleanly (`BLOCKED`) when the budget is exhausted.

**Independent Test**: Run `controller.py run --mode guarded` against the
`constitution` phase with a fake agent from `fixtures/fake_agent.py`
scripted to (a) produce a valid constitution, then (b) return success
without changing anything — confirm (a) passes and (b) fails, per
`docs/spec-master/guarded-mode-spec.md` §16 integration scenarios 1-2.

- [X] T008 [US1] In `spec-master/lib/controller.py`, implement state
      bookkeeping: load-or-init `state["execution"]`/`state["attempts"]`
      (reusing `state_mod.load`/`state_mod.save` — never a second write
      path), `.spec-master/run.lock` creation (`{"phase", "pid", "started_at"}`)
      and removal on completion, and per-attempt timeout enforcement via
      `subprocess`/`phase_runner` (§16-9).
- [X] T009 [US1] In `controller.py`, implement the per-phase attempt loop:
      for `attempt in range(1, max_attempts+1)`, call
      `phase_runner.run_phase(...)`, validate via `phase_contracts`, and only
      call `state_mod.transition_phase(..., "PASSED")` after validation
      passes (FR-004); append a `PhaseAttempt` record every time regardless
      of outcome (FR-011). A retry's rendered prompt includes only the
      objective failure reason, the phase's allowlist, and its expected
      artifacts — never the previous attempt's transcript (FR-013, §8).
      Exhausting `max_attempts_per_phase` marks the phase `BLOCKED` and
      stops the workflow (§16-10; FR-008).
- [X] T010 [P] [US1] `spec-master/tests/test_controller.py::TestRunPhaseLoop`:
      fake agent produces a valid constitution → phase `PASSED` only after
      the artifact is confirmed non-placeholder (§16-1); fake agent exits 0
      without changing any required artifact → phase `FAILED`, never
      `PASSED` (§16-2).
- [X] T011 [P] [US1] `spec-master/tests/test_controller.py::TestAttempts`:
      first attempt fails (e.g. placeholder left), second attempt (scripted
      to fix it) passes (§16-6); a phase scripted to always fail exhausts
      `max_attempts_per_phase` and ends `BLOCKED` (§16-7), and its last
      attempt's transcript is copied to `.spec-master/failed-attempts/<phase>/`
      (FR-015).
- [X] T012 [US1] Wire the `run` subcommand's argparse surface per
      `contracts/cli.md` (`--project`, `--context`, `--mode`, `--integration`,
      `--model`, `--max-attempts` default 2, `--phase-timeout` default 600,
      optional `--feature`). `--mode native` prints the documented
      `REJECTED` payload and exits `2` without touching state (research.md
      item 2) — no attempt loop runs.
- [X] T013 [P] [US1] `spec-master/tests/test_controller.py::TestModeFlag`:
      `--mode native` rejected with exit code 2 and no state file written;
      `--mode guarded` and `--mode auto` both accepted (§16-1).

**Checkpoint**: `controller.py run --mode guarded` is independently usable and
tested end-to-end for a single phase and for the attempt/BLOCKED policy.

## Phase 4: User Story 2 — Automatic degradation when the model misbehaves (Priority: P1)

**Goal**: `--mode auto` starts `native` and irreversibly becomes `guarded`
the moment a critical event fires or two recoverable events accumulate.

**Independent Test**: Script a fake agent to create `src/app.py` during
`constitution` under `--mode auto`; confirm the attempt is rejected and
`state["execution"]["mode_transitions"]` records `native -> guarded`
(§16-3).

- [X] T014 [US2] In `controller.py`'s attempt loop (from T009), after each
      attempt call `execution_mode.record_event`/`maybe_migrate` for every
      classified event (from `phase_runner`'s output), but only when
      `state["execution"]["active_mode"] == "native"` (i.e. only meaningful
      for `--mode auto`; a `--mode guarded` run is already fully guarded and
      has no `native` phase to migrate out of).
- [X] T015 [P] [US2] `spec-master/tests/test_controller.py::TestAutoMigration`:
      early code creation during `constitution` under `auto` triggers
      migration (§16-3); a `<tool_call>` printed as text triggers migration
      (§16-4); a write outside the project triggers migration (§16-5).
- [X] T016 [US2] Add an explicit guard in `execution_mode.maybe_migrate` (and
      assert it in `controller.py`) that once `active_mode == "guarded"`,
      further events are recorded but never flip it back to `native`, and
      that `resume` (Phase 5) preserves `active_mode == "guarded"` across
      process restarts.
- [X] T017 [P] [US2] `spec-master/tests/test_execution_mode.py::TestNoReversion`:
      once migrated, additional critical/recoverable events leave
      `active_mode` at `"guarded"`.

**Checkpoint**: US1 + US2 both independently functional — `auto` self-degrades
safely and stays degraded.

## Phase 5: User Story 3 — Resume an interrupted protected run (Priority: P2)

**Goal**: `controller.py resume` continues from the first non-`PASSED`
phase, never repeats a valid `PASSED` phase, and reclaims a stale lock.

**Independent Test**: Run one phase to `PASSED`, simulate a kill (delete
the in-memory process, keep `.spec-master/state.json` and any lock file),
call `resume`, and confirm the already-`PASSED` phase is not re-attempted
(§16, acceptance criterion 7).

- [X] T018 [US3] Implement the `resume` subcommand in `controller.py`: load
      state, error clearly if `state["execution"]` is absent (per
      `contracts/cli.md`), re-derive `mode`/`integration`/`model` from
      `state["execution"]`, and re-enter the same attempt loop as `run`
      (T009) starting from the first phase whose last attempt isn't
      `PASSED` or which has no attempts yet — reusing `fingerprint.compare`
      to confirm a `PASSED` phase's artifacts are still valid before
      skipping it (FR-010).
- [X] T019 [US3] Add stale-`run.lock` handling (`data-model.md` Run Lock) to
      both `run` and `resume`: a lock whose `started_at` is older than
      `phase_timeout_seconds` is removed and logged before proceeding; a
      fresh lock causes `resume`/`run` to reject with
      `"run already in progress (lock held)"` (exit 2).
- [X] T020 [P] [US3] `spec-master/tests/test_controller.py::TestResume`:
      `resume` skips a `PASSED` phase with a matching fingerprint and starts
      at the next `PENDING` phase (§16-11); a stale lock is removed
      automatically and the run proceeds (§16-12); a fresh (non-stale) lock
      causes `resume` to reject.

**Checkpoint**: interrupted guarded runs resume without redoing valid work.

## Phase 6: User Story 4 — Trustworthy final report (Priority: P2)

**Goal**: The `run`/`resume` terminal payload and `status` output clearly
separate workflow result, per-attempt outcomes, and mode changes, so a
controller-repaired run is never mistaken for an unaided model success.

**Independent Test**: Simulate a full 8-phase workflow with a fake agent
(two rejected attempts along the way) through `COMPLETED`, and confirm the
report lists rejected attempts separately from the passing ones (§16-8;
acceptance criterion 8).

- [X] T021a [US4] Implement `validate`-phase quality-gate execution in
      `phase_runner.py` (T006 extension): before the OpenCode adapter runs
      for `phase == "validate"`, call `quality_gates.detect()` and run each
      returned command, write `.spec-master/reports/quality-gates.md`, and
      merge results into `state["quality_gates"]`. A blocking gate failure
      makes the attempt `FAILED` with `reason: "blocking_quality_gate_failed"`
      regardless of the OpenCode adapter's own result (FR-017;
      `data-model.md` "`validate` phase behavior", analyze finding C1 fix).
- [X] T021 [US4] Implement the final-report payload in `controller.py`
      (`run`/`resume` terminal JSON per `contracts/cli.md`:
      `workflow_status`, `active_mode`, `mode_transitions`, `phases`,
      `blocked_phase`, `attempts_summary`, `quality_gates`), plus short
      human-readable progress lines emitted per attempt matching the format
      in `docs/spec-master/guarded-mode-spec.md` §13 (e.g.
      `[Spec Master] constitution attempt 1/2 started (guarded).`).
- [X] T022 [US4] Implement the `status` subcommand per `contracts/cli.md`:
      read-only, returns the documented empty payload
      (`{"execution": null, "phases": {}, "attempts_summary": {}, "blocked_phase": null}`)
      when no state file exists, never writes state or a lock.
- [X] T023 [P] [US4] `spec-master/tests/test_controller.py::TestFullWorkflow`:
      a fully simulated 8-phase run (with at least one retried phase) reaches
      `workflow_status: "COMPLETED"` (§16-8; acceptance criterion 6 — all
      eight phases in separate sessions); the report's `attempts_summary`
      shows the rejected attempt distinctly from the passing one for that
      phase (acceptance criterion 8, SC-006); the report's `quality_gates`
      reflects the (mocked) gates run during `validate` (FR-017).
- [X] T024 [P] [US4] `spec-master/tests/test_controller.py::TestStatus`:
      `status` against a project with no `.spec-master/state.json` returns
      the documented empty payload instead of raising.

**Checkpoint**: all four user stories independently functional; a full
simulated workflow is observable end-to-end via `status` and the final report.

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T025 [P] Extend `spec-master/tests/test_opencode_runner.py` to cover the
      new `validate` phase entry and confirm the `phase_contracts.py`
      extraction (T002) changed no observable behavior of the existing
      `run()`/`build_parser()`/`main()` functions.
- [X] T026 Run `python3 -m unittest discover -s spec-master/tests -v` and fix
      any failures until the entire suite (pre-existing + new) passes
      (SC-002; acceptance criterion 1).
- [X] T027 [P] Add a short, clearly-labeled "Guarded mode (opt-in,
      experimental)" note to `README.md` documenting `controller.py
      run/resume/status` as available today, explicitly stating that
      `/spec-master`'s default behavior is unchanged (research.md item 1) —
      no other section of `README.md` is touched.
- [X] T028 Manually run `quickstart.md` steps 1-3 (fake-agent based) and
      confirm the observed output matches what's documented; step 4 (real
      model smoke test) is explicitly skipped as non-blocking.

## Dependencies & Execution Order

- **Setup (T001)**: no dependencies.
- **Foundational (T002-T007)**: depends on T001 (tests need the fake-agent
  fixture); BLOCKS every user story.
- **User Story 1 (T008-T013)**: depends on Foundational only.
- **User Story 2 (T014-T017)**: depends on Foundational + US1's attempt loop
  (T009) to hook into.
- **User Story 3 (T018-T020)**: depends on Foundational + US1's state
  bookkeeping (T008) and attempt loop (T009); independent of US2.
- **User Story 4 (T021a, T021-T024)**: depends on US1 (attempts data), and
  reports on US2's `mode_transitions` and US3's resume path if present —
  implement last among the stories so there is real data to report on,
  though its own code has no hard import-time dependency on US2/US3. T021a
  additionally depends on the existing, already-tested
  `spec-master/lib/quality_gates.py` (no change needed there, only a new
  caller).
- **Polish (T025-T028)**: depends on all of the above.

### Parallel Opportunities

- T003, T005, T007 (foundational tests) can run in parallel once their
  respective implementation task lands.
- T010+T011 (US1 tests) in parallel; T015+T017 (US2 tests) in parallel;
  T020 (US3) is a single task; T023+T024 (US4 tests) in parallel.
- T025 and T027 in Polish are independent of each other and of T026/T028.
- US2 and US3 can be implemented in parallel by different people once US1's
  T008/T009 land (US2 touches the event-classification call site, US3 adds
  the `resume` subcommand — different code paths in the same file, so
  coordinate on `controller.py` merges even though the tasks are logically
  independent).

## Implementation Strategy

### MVP First (User Story 1 only)

1. Complete Setup (T001) + Foundational (T002-T007).
2. Complete User Story 1 (T008-T013).
3. **STOP and VALIDATE**: `controller.py run --mode guarded` against a
   single-phase fake-agent scenario behaves per `docs/spec-master/guarded-mode-spec.md`
   §16 integration scenarios 1, 2, 6, 7.
4. This alone already satisfies FR-001, FR-002 (via T012/T013), FR-004,
   FR-008, FR-011, FR-013.

### Incremental Delivery

1. Foundational → US1 (MVP: guarded execution with real artifact
   validation and bounded retries).
2. Add US2 (auto self-degradation) → full GM-009 coverage.
3. Add US3 (resume) → full GM-010 coverage.
4. Add US4 (reporting) → full GM-011/SC-006 coverage.
5. Polish → full suite green, `validate`-phase parity in
   `opencode_runner.py`, README note.
