---
description: "Task list for Guarded No-op Phase Validation"
---

# Tasks: Guarded No-op Phase Validation

**Input**: Design documents from `specs/002-guarded-noop-phase-validation/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/attempt-outcome.md, quickstart.md

**Tests**: Required (spec.md §16 mandates specific unit/integration cases; Constitution
Principle III applies, same as Feature 1).

**Organization**: This spec has no user-story/priority sections (it is a targeted bug
fix, not a new capability) — tasks are grouped by the spec's own scenario groups
(§15 Cenários A-G) after a shared Foundational phase, since every scenario depends
on the same `phase_result.py`/`PHASE_POLICY`/`resolve_active_feature_dir` primitives.

**Regression gate**: T001 and T0-final both run the full existing suite
(`python3 -m unittest discover -s spec-master/tests -v`) — it must show the same
95 passing tests both before touching any Feature-1 file and after every change.

## Format: `[ID] [P?] Description`

- **[P]**: Can run in parallel (different files, no dependencies)

## Phase 0: Baseline

- [X] T001 Run `python3 -m unittest discover -s spec-master/tests -v` and confirm
      the pre-existing 95 tests pass before any change (regression baseline).

## Phase 1: Foundational (Blocking Prerequisites)

**⚠️ CRITICAL**: No scenario-specific task can begin until this phase is complete.

- [X] T002 Create `spec-master/lib/phase_result.py`: `parse_last_phase_result(text: str) -> dict | None`.
      Scan `text` for every syntactically balanced `{...}` span (bracket-depth
      counter, not regex), `json.loads()` each candidate inside a `try/except
      (json.JSONDecodeError, ValueError)`, keep it only if the result is a
      `dict` with a `"phase_result"` key whose value is one of
      `artifact_updated | no_changes_required | user_decision_required | failed`
      (data-model.md "`phase_result`"). Return the **last** qualifying dict, or
      `None`. Never `eval`/`exec` anything (NFR, research.md item 5).
- [X] T003 [P] `spec-master/tests/test_phase_result.py`: a transcript with one
      valid block after prose returns it; a transcript with two valid blocks
      returns the last; a transcript with a `checks` sub-object (nested braces)
      parses correctly; invalid JSON is ignored, not raised; a block with an
      unrecognized `phase_result` value is ignored; no block at all returns
      `None`.
- [X] T004 In `spec-master/lib/phase_contracts.py`, add
      `PHASE_CONTRACT_VERSION = 2` and
      `PHASE_POLICY = {...}` (data-model.md "Phase Policy") mapping every
      phase to `produce-or-update`/`inspect-or-update`/`execute`.
- [X] T005 In `spec-master/lib/phase_contracts.py`, add
      `class ActiveFeatureUnresolved(Exception)` and
      `resolve_active_feature_dir(project: Path) -> Path`: read
      `.specify/feature.json`, reject missing/unreadable/invalid JSON, reject
      an absent/empty/absolute `feature_directory` or one containing `..`,
      reject a resolved path that escapes the project root (reuse the same
      `.resolve()` + `relative_to` containment check `phase_runner.
      _symlink_escapes_project` already uses) — raise `ActiveFeatureUnresolved`
      on any of these; otherwise return the resolved feature directory (§7).
- [X] T006 [P] `spec-master/tests/test_phase_contracts.py`: `PHASE_POLICY`
      classifies every phase correctly (§16 `test_phase_contracts.py` item 1);
      `resolve_active_feature_dir` resolves a valid `feature.json` correctly,
      and raises `ActiveFeatureUnresolved` for: missing file, `feature_directory`
      with `..`, an absolute path, and a symlink escaping the project (§16
      items 2-3).
- [X] T007 In `spec-master/lib/phase_contracts.py`, add two pure predicates:
      `clarify_result_ok(project, structured_result) -> bool` (spec.md §5,
      conditions 5-8 — feature resolved via `resolve_active_feature_dir`,
      `spec.md` exists/non-empty, no placeholder markers, no
      `[NEEDS CLARIFICATION` — conditions 1-4 and 9-11 are handled by
      `phase_runner.py` since they depend on process-level data (exit code,
      forbidden writes, the structured result's own `checks` values) not
      available to a pure filesystem predicate) and
      `analyze_result_ok(project, structured_result) -> bool` (spec.md §8,
      conditions 1-2 — spec/plan/tasks of the active feature exist, non-empty,
      no blocking placeholders). Both raise `ActiveFeatureUnresolved` when
      `.specify/feature.json` can't be resolved (propagated by the caller into
      `reason: "active_feature_unresolved"`).
- [X] T008 [P] `spec-master/tests/test_phase_contracts.py`: a complete,
      marker-free active spec is `clarify_result_ok`-eligible (§16 item 5); a
      spec still containing `[NEEDS CLARIFICATION]` is not; a clean spec/plan/tasks
      trio is `analyze_result_ok`-eligible (§16 item 6).

**Checkpoint**: `phase_result.py`, `PHASE_POLICY`, `resolve_active_feature_dir`,
and the two result predicates exist and are independently tested. Scenario work
can begin. Re-run T001's suite now — Feature 1 must still be untouched and green.

## Phase 2: Cenário A/B — Clarify no-op decision (`phase_runner.py`)

**Goal**: `clarify` passes without a filesystem change when the active spec is
already complete and the agent's structured result says so and is corroborated;
it fails, not passes, when the structured claim contradicts the filesystem.

- [X] T009 In `spec-master/lib/phase_runner.py`, restructure `run_phase`'s
      pass/fail decision to evaluate branches in the fixed order from
      research.md item 7: (1) existing hard-fail checks (`timed_out`,
      `exit_code != 0`, `fake_tool_markers`, `forbidden_writes`,
      `artifact_wrong_location`, `blocking_gate_failed`) exactly as before —
      unconditional, regardless of policy or outcome (spec.md §2, §14). Parse
      `structured_result = phase_result.parse_last_phase_result(stdout)` and
      `outcome = structured_result["phase_result"] if structured_result else
      None` right after the hard-fail checks, before anything else. (2) See
      T011 (`user_decision_required` check — evaluated next, before
      `required_changed`). (3) When `required_changed` is `True` (and outcome
      isn't `user_decision_required`), behavior is unchanged from Feature 1
      (`PASSED`, `reason: None`, `outcome` defaults to `"artifact_updated"` if
      the agent didn't say otherwise).
- [X] T010 In `run_phase`, when `required_changed` is `False` (and outcome
      isn't `user_decision_required` — see T011) and
      `PHASE_POLICY[phase] == "inspect-or-update"`: if `outcome !=
      "no_changes_required"` (including `None`), fail with
      `reason: "phase_result_missing"` (no block found) or
      `reason: "phase_result_invalid"` (a block was found but claims something
      else, e.g. `failed`). If `outcome == "no_changes_required"`, call
      `phase_contracts.clarify_result_ok`/`analyze_result_ok` (dispatched by
      `phase`); catch `ActiveFeatureUnresolved` → `reason:
      "active_feature_unresolved"`; on `True` → `PASSED`,
      `reason: "valid_noop"`; on `False` → `FAILED`,
      `reason: "phase_result_invalid"` (Cenário B).
- [X] T011 In `run_phase`, immediately after the hard-fail checks and
      *before* evaluating `required_changed` at all (research.md item 7,
      analyze finding C1): if `outcome == "user_decision_required"` →
      `FAILED`, `reason: "user_decision_required"`, regardless of whether a
      file also changed this attempt. This is a distinct terminal reason the
      caller (`controller.py`, Phase 4 below) must treat specially (pause,
      don't consume an attempt) — it always takes priority over both the
      `required_changed == True` fast-path and the no-op paths.
- [X] T012 Extend `run_phase`'s return dict with `outcome`, `policy`
      (`PHASE_POLICY[phase]`), `contract_version`
      (`phase_contracts.PHASE_CONTRACT_VERSION`), `active_artifacts` (the
      resolved feature directory's relevant file(s) when
      `resolve_active_feature_dir` was actually used this attempt, else `[]`),
      and `structured_result` (verbatim, or `None`) — data-model.md
      "PhaseAttempt (extended)".
- [X] T013 [P] `spec-master/tests/test_phase_runner.py`: Cenário A (clean spec,
      valid `no_changes_required` block, no write → `PASSED`/`valid_noop`,
      §16 `test_phase_runner.py` item 1); a clean spec with **no** structured
      block → `FAILED`/`phase_result_missing` (§16 item 2); a spec still
      containing `[NEEDS CLARIFICATION]` with a `no_changes_required` claim →
      `FAILED`/`phase_result_invalid` (§16 item 3, Cenário B); a forbidden
      write alongside a `no_changes_required` claim still fails as
      `forbidden_write`, not `valid_noop` (§16 item 4, Cenário D); a timeout
      alongside any claim always fails as `timeout` (§16 item 5); `analyze`
      with zero findings and no write passes as `valid_noop` (§16 item 6,
      Cenário E); a `produce-or-update` phase (`tasks`) with no write and no
      structured result still fails as before this feature (§16 item 7,
      until Phase 3 below adds its trust path); a `clarify` attempt that
      both changes `spec.md` and emits a `user_decision_required` block
      fails as `user_decision_required`, not `PASSED` (analyze finding
      C1 — priority-order regression test).

**Checkpoint**: `clarify`/`analyze` no-op decisions work in isolation
(`phase_runner.run_phase` called directly with a fake transcript). Producer
phases are untouched so far — still exactly Feature-1 behavior. Re-run T001's
suite.

## Phase 3: Cenário E extension — Producer-phase retry trust (`phase_runner.py`)

**Goal**: A `produce-or-update` phase can pass on a retry without a new change,
but only when every prior attempt for that phase was free of forbidden writes —
never on the very first attempt.

- [X] T014 `run_phase` gains an optional `history: list[dict] = ()` parameter
      (the phase's prior `PhaseAttempt` records, oldest first — supplied by
      `controller.py`). When `required_changed` is `False` and
      `PHASE_POLICY[phase] == "produce-or-update"`: if `history` is non-empty
      (this is a retry, not the first attempt — spec.md §9, "não deve permitir
      no-op na primeira execução válida") **and** no entry in `history` has a
      non-empty `forbidden_writes` or `"out_of_project_write"` in its `events`
      (research.md item 2) **and** `missing_artifacts`/`placeholder_artifacts`
      are both empty right now → `PASSED`, `reason: "valid_noop"`,
      `outcome: "no_changes_required"` (research.md item 3). Otherwise →
      `FAILED`, `reason: "unchanged_artifact"` (unchanged from today).
- [X] T015 [P] `spec-master/tests/test_phase_runner.py`: a `tasks` phase with
      one prior clean (no forbidden-write) attempt and no change this attempt
      → `PASSED`/`valid_noop`; the very first attempt of `tasks` with no
      change → still `FAILED`/`unchanged_artifact` regardless of `history`
      being empty; a `tasks` phase whose prior attempt had a forbidden write
      never passes via this path even after a later clean attempt.

**Checkpoint**: full `phase_runner.py` decision surface for this feature is
done and independently tested. Re-run T001's suite — must still be 95/95 plus
the new tests so far.

## Phase 4: Cenário F/G — Controller: pause, budget accounting, and resume revalidation

**Goal**: `user_decision_required` pauses the workflow without burning an
attempt; a phase blocked under the old contract gets a fair re-evaluation on
`resume` without needing to delete history or force a full re-run when it's
avoidable.

- [X] T016 In `spec-master/lib/controller.py`, pass `history=attempts` (the
      phase's attempts *so far this call*, i.e. before appending the new
      record) into `phase_runner.run_phase` from
      `_run_phase_with_attempts` (wires T014).
- [X] T017 In `_run_phase_with_attempts`, after appending a `FAILED` record
      with `reason == "user_decision_required"`: do not continue the attempt
      loop. Call `state_mod.transition_workflow_status(state, "PAUSED")`,
      save state, print the paused phase and (if present)
      `record["structured_result"]["checks"]`, and return a new sentinel
      `"PAUSED"` (distinct from `"PASSED"`/`"BLOCKED"`).
- [X] T018 In `_drive_workflow`, when a phase returns `"PAUSED"`: stop the
      phase loop immediately (like `"BLOCKED"` does), but report
      `workflow_status: "PAUSED"` (not `"BLOCKED"`) in the final payload, and
      do **not** call `transition_workflow_status(state, "BLOCKED")` —
      leave it at `"PAUSED"`.
- [X] T019 Change every "how many attempts has this phase used" computation
      (`_run_phase_with_attempts`'s `start_number`/loop bound and
      `_phase_status`'s `BLOCKED` check) from `len(attempts)` to
      `len([a for a in attempts if a["reason"] != "user_decision_required"])`
      (data-model.md "Attempt budget accounting").
- [X] T020 [P] `spec-master/tests/test_controller.py`: a fake agent that
      emits `user_decision_required` on `clarify`'s first attempt pauses the
      workflow (`workflow_status: "PAUSED"`) without a second attempt being
      spawned, and a subsequent normal attempt (simulating the operator
      answering and re-running) still has its full `max_attempts` budget
      available (§16 `test_controller.py` item 2).
- [X] T021 In `spec-master/lib/controller.py`, add
      `_try_contract_revalidation(project, phase, last_attempt, context_hash) -> dict | None`:
      returns `None` immediately unless all four §11 conditions hold
      (`last_attempt.get("contract_version", 1) < phase_contracts.PHASE_CONTRACT_VERSION`,
      `last_attempt["reason"] in ("missing_artifact", "unchanged_artifact")`,
      the phase's required artifact currently exists/non-empty, and
      `last_attempt.get("context_hash") == context_hash`). If they hold,
      re-read `last_attempt["transcript"]` from disk (skip — return `None` —
      if it's gone) and call a new `phase_runner.revalidate_from_transcript(project,
      phase, transcript_text)` that runs the *same* structured-result parse +
      `clarify_result_ok`/`analyze_result_ok` predicate `run_phase` uses,
      without invoking any subprocess or writing a new transcript. On a
      passing revalidation, return a `PhaseAttempt`-shaped dict with
      `status: "PASSED"`, `reason: "valid_noop"`,
      `source: "contract_revalidation"`; otherwise return `None` (research.md
      item 6 — the caller then falls through to a normal, live attempt).
- [X] T022 Add `phase_runner.revalidate_from_transcript(project, phase,
      transcript_text) -> dict`: shares the structured-result-parse +
      predicate logic from T009-T010 (factor the shared piece into a small
      helper both `run_phase` and this function call, rather than
      duplicating it) but skips the snapshot/subprocess/forbidden-write
      machinery entirely — it only asks "does the filesystem right now,
      combined with this already-existing transcript's structured result,
      satisfy the no-op contract." Returns `None` (not a dict) if the
      transcript has no valid structured result, so `_try_contract_revalidation`
      knows to fall back to a live attempt.
- [X] T023 In `_run_phase_with_attempts`, before entering the attempt loop:
      if the phase's last attempt exists and is not `PASSED`, call
      `_try_contract_revalidation`; on a non-`None` result, append it as a
      new attempt record (numbered after the existing ones, still subject to
      T019's budget accounting — a revalidation success does consume a
      nominal slot for audit-trail purposes, but since it passes immediately
      this never matters for the budget) and return `"PASSED"` without
      entering the loop; on `None`, proceed exactly as before (a live
      attempt).
- [X] T024 [P] `spec-master/tests/test_controller.py`: reproduce the real
      regression — a fake `clarify` attempt fails as `missing_artifact`
      with no `contract_version` recorded (simulating a pre-feature
      attempt) against a complete, marker-free spec; `resume` promotes it
      via `_try_contract_revalidation` (no new subprocess call observed) with
      `source: "contract_revalidation"`, and the original blocked entry is
      still present, unedited, in `state["attempts"]["clarify"]` (§16
      `test_controller.py` items 3-4; Cenário G; acceptance criterion 8).

**Checkpoint**: `PAUSED` and contract-revalidation both work end to end
through `controller.py`. Re-run T001's suite.

## Phase 5: Polish & Regression

- [X] T025 `spec-master/tests/test_controller.py`: a fully simulated workflow
      that hits a `clarify` no-op and an `analyze` no-op both reaches
      `COMPLETED` (§16 `test_controller.py` item 5).
- [X] T026 Run `python3 -m unittest discover -s spec-master/tests -v` and
      confirm the full suite — the original 95 tests plus every test added
      in this feature — passes with 0 failures (spec.md §18 criterion 1).
- [X] T027 Add an `outcomes: {phase: <last attempt's outcome>}` field to
      `controller.py`'s `_drive_workflow` report payload, alongside the
      existing `phases`/`attempts_summary` fields (analyze finding H1 — the
      printed report did not actually expose `outcome` anywhere; only
      `state["attempts"]` did, which isn't part of the CLI contract).
      Update `specs/001-guarded-mode-controller/contracts/cli.md`'s example
      JSON to include `outcomes`, noting it was added by this feature.
      Extend `TestFullWorkflow` in `test_controller.py` to assert
      `outcomes["clarify"] == "no_changes_required"` for a no-op scenario
      and `outcomes["specify"] == "artifact_updated"` for an ordinary pass
      (spec.md §18 criterion 9).
- [X] T028 Manually run `quickstart.md` steps 1-5 and confirm the observed
      output matches what's documented.
- [X] T029 `spec-master/tests/test_controller.py`: NPV-012 compatibility —
      load a synthetic `state.json` shaped exactly like a completed
      Feature-1-only workflow (`status: "COMPLETED"`, every
      `PhaseAttempt` missing `contract_version`/`policy`/`outcome`/
      `active_artifacts`/`structured_result`/`source`) through
      `controller.status`/`_phase_status`/`_try_contract_revalidation`
      and confirm none of them raise (all new fields are read via
      `.get(...)` with a safe default, never direct indexing) — analyze
      finding M1.

## Dependencies & Execution Order

- **T001** (baseline): no dependencies, run first.
- **Foundational (T002-T008)**: depends on T001; BLOCKS every later phase.
- **Phase 2 (T009-T013)**: depends on Foundational.
- **Phase 3 (T014-T015)**: depends on Phase 2 (shares `run_phase`'s decision
  structure T009 builds).
- **Phase 4 (T016-T024)**: depends on Phase 2 and Phase 3 (needs the full
  `phase_runner.run_phase` decision surface, including `history`, to exist).
- **Phase 5 (T025-T028)**: depends on all of the above.

### Parallel Opportunities

- T003, T006, T008 (foundational tests) once their respective implementation
  task lands.
- T013 and T015 can be written in parallel (different scenario groups within
  the same file — coordinate on `test_phase_runner.py` merges).
- T020 and T024 (controller tests) in parallel once T016-T023 land.
- T027 and T028 in Polish are independent of each other and of T026.

## Implementation Strategy

1. T001 baseline, then Foundational (T002-T008) — nothing observable changes
   yet, but the primitives exist and are tested.
2. Phase 2 fixes the actual reported bug (`clarify` no-op) end to end at the
   `phase_runner` level — this alone resolves Cenários A, B, D, E and
   acceptance criteria 3-6.
3. Phase 3 extends the same mechanism to producer-phase retries (a smaller,
   related gap noticed while implementing Phase 2, explicitly scoped by §9).
4. Phase 4 wires it into `controller.py`'s actual attempt loop and adds the
   `PAUSED`/resume-revalidation behavior — this is what makes the real
   `qwen-greeting-api` regression (Cenário G) actually resolvable via
   `resume`, and what makes Cenário F (human-decision pause) real.
5. Polish confirms the full regression suite and the quickstart scenarios.
