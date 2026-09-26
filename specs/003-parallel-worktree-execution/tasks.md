# Tasks: Parallel Worktree Execution

**Input**: Design documents from `specs/003-parallel-worktree-execution/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/cli-worktree.md](contracts/cli-worktree.md)

**Tests**: Included — constitution Principle III requires every `spec-master/lib/` module to
ship a mirrored `spec-master/tests/test_<module>.py`, so test tasks are mandatory here, not
optional.

**Organization**: Tasks are grouped by user story (US1/US2/US3 from spec.md) to enable
independent implementation and testing of each story.

**Revision note**: T008/T009 (tests) and T012 (implementation) below were added during
`/speckit-analyze` repair cycle 1 to close two gaps found by cross-artifact analysis: no task
coverage for spec.md Edge Case 3 / SC-003 (idempotent worktree-path reuse on resume), and no
task wiring FR-003's phase-loop isolation contract (`resolve_project_root`, research.md #5).
All subsequent task IDs were renumbered accordingly — this file has not been consumed by
`/speckit-implement` yet, so renumbering is safe.

## Path Conventions

Single project (per plan.md Structure Decision): `spec-master/lib/`, `spec-master/tests/`.

---

## Phase 1: Setup (Shared Infrastructure)

- [x] T001 Create `spec-master/lib/worktree.py` module skeleton (module docstring per
      research.md, `from __future__ import annotations`, no logic yet)
- [x] T002 Create `spec-master/tests/test_worktree.py` skeleton mirroring the
      `_pathfix`/import pattern used by `spec-master/tests/test_git_strategy.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**⚠️ CRITICAL**: Blocks all user stories — `run_git()` is the single mockable boundary every
story's git-touching function goes through (Principle III).

- [x] T003 Implement `run_git(args: list[str], cwd: str) -> subprocess.CompletedProcess` in
      `spec-master/lib/worktree.py` (research.md #3 — the one `subprocess.run` call site)
- [x] T004 [P] Add the `worktree` subparser group scaffold (`waves`, `plan`, `conflicts`,
      `aggregate` — no-op bodies) in `spec-master/lib/cli.py`, mirroring the existing
      `git-strategy`/`state` subparser pattern

**Checkpoint**: Foundation ready — user story implementation can now begin.

---

## Phase 3: User Story 1 - Execute independent features concurrently in isolated worktrees (Priority: P1) 🎯 MVP

**Goal**: Compute waves from `features order` output and create one isolated `git worktree`
per feature in any multi-feature wave (FR-001, FR-002, FR-003), reusing/resuming an existing
worktree path idempotently on resume (Edge Case 3, SC-003).

**Independent Test**: Feed a two-feature list with no dependency edge into wave computation
and assert both land in the same wave; assert a worktree handle is created per feature with
non-overlapping paths; assert re-planning a feature whose worktree already exists reuses it
without recreating.

### Tests for User Story 1

- [x] T005 [P] [US1] `test_compute_waves_independent_features_same_wave` in
      `spec-master/tests/test_worktree.py` (Acceptance Scenario 1)
- [x] T006 [P] [US1] `test_compute_waves_dependency_strictly_later_wave` in
      `spec-master/tests/test_worktree.py` (Acceptance Scenario 3, FR-001)
- [x] T007 [P] [US1] `test_plan_worktree_creates_handle_per_feature_in_multi_feature_wave`
      in `spec-master/tests/test_worktree.py` (Acceptance Scenario 2, FR-002, FR-003) —
      mocks `run_git` from T003, asserts it is called with `git worktree add` and the path
      from data-model.md's `.spec-master/worktrees/<feature-id>` convention
- [x] T008 [P] [US1] `test_plan_worktree_reuses_existing_path_without_recreating` in
      `spec-master/tests/test_worktree.py` (spec.md Edge Case 3, SC-003; research.md #2
      idempotency note, added during `/speckit-analyze` repair cycle 1) — mocks the worktree
      path as already existing (`os.path.isdir` patched `True`) and asserts `run_git` is
      called with neither `worktree add` nor any delete/remove subcommand, and that the
      returned handle points at the same pre-existing path
- [x] T009 [P] [US1] `test_resolve_project_root_returns_worktree_path` in
      `spec-master/tests/test_worktree.py` (FR-003, Acceptance Scenario 2; research.md #5,
      added during `/speckit-analyze` repair cycle 1) — asserts
      `resolve_project_root(handle)` returns exactly `handle["path"]` for a handle produced
      by `plan_worktree`, establishing the contract callers rely on to scope a feature's
      phase loop to its own worktree directory

### Implementation for User Story 1

- [x] T010 [US1] Implement `compute_waves(ordered_features: list[dict]) -> list[dict]` in
      `spec-master/lib/worktree.py` (FR-001, data-model.md Execution Wave) — depends on T005, T006
- [x] T011 [US1] Implement `plan_worktree(feature_id: str, project_root: str, strategy: str) -> dict`
      in `spec-master/lib/worktree.py` (FR-002, FR-003, data-model.md Worktree Handle) using
      `run_git` from T003; MUST check whether the target path already exists and, if so,
      return a handle for the existing directory instead of calling `git worktree add`
      (research.md #2 idempotency note) — depends on T003, T007, T008
- [x] T012 [US1] Implement `resolve_project_root(handle: dict) -> str` in
      `spec-master/lib/worktree.py`, returning `handle["path"]` (FR-003, research.md #5) —
      document in its docstring that every caller driving a feature's phase loop inside a
      wave MUST use this as that loop's project root — depends on T009, T011
- [x] T013 [US1] Wire `worktree waves` and `worktree plan` CLI verbs to T010/T011 in
      `spec-master/lib/cli.py` per `contracts/cli-worktree.md` — depends on T004, T010, T011

**Checkpoint**: US1 fully functional and independently testable — waves compute correctly,
worktrees are created only for multi-feature waves, an existing worktree is resumed rather
than recreated, and `resolve_project_root` gives callers an explicit isolation contract.

---

## Phase 4: User Story 2 - Aggregate and report worktree results, never auto-merge conflicts (Priority: P1)

**Goal**: After a wave finishes, aggregate each feature's status/changed files and detect
file-level conflicts between worktrees without mutating either side (FR-006, FR-007, FR-008).

**Independent Test**: Simulate two worktrees with conflicting changes to the same file, run
conflict detection, assert a conflict is reported and neither worktree's content changed.

### Tests for User Story 2

- [x] T014 [P] [US2] `test_conflicts_detects_overlapping_files` in
      `spec-master/tests/test_worktree.py` (Acceptance Scenario 2, research.md #4 — mocks
      `run_git`'s `rev-parse`/`merge-base`/`diff --name-only` sequence, the diff-intersection
      first pass research.md #4 explicitly sanctions)
- [x] T015 [P] [US2] `test_conflicts_empty_when_no_overlap` in
      `spec-master/tests/test_worktree.py`
- [x] T016 [P] [US2] `test_aggregate_records_status_and_changed_files` in
      `spec-master/tests/test_worktree.py` (Acceptance Scenario 1, FR-006)
- [x] T017 [P] [US2] `test_aggregate_preserves_blocked_worktree_directory` in
      `spec-master/tests/test_worktree.py` (Acceptance Scenario 3, FR-008 — asserts aggregate
      never calls any delete/remove path for a non-terminal or BLOCKED handle)

### Implementation for User Story 2

- [x] T018 [US2] Implement `conflicts(path_a: str, path_b: str) -> dict` in
      `spec-master/lib/worktree.py` using `run_git` for read-only `rev-parse`/`merge-base`/
      `diff --name-only` calls, intersecting each worktree's changed files since their common
      merge-base (FR-007, research.md #4) — depends on T003, T014, T015
- [x] T019 [US2] Implement `aggregate(wave_index: int, handles: list[dict]) -> dict` in
      `spec-master/lib/worktree.py` (FR-006, FR-008, data-model.md Aggregation Result) —
      depends on T016, T017
- [x] T020 [US2] Wire `worktree conflicts` and `worktree aggregate` CLI verbs to
      T018/T019 in `spec-master/lib/cli.py` per `contracts/cli-worktree.md` — depends on
      T004, T018, T019

**Checkpoint**: US1 + US2 both work independently — waves execute in isolation and results
aggregate safely with honest conflict reporting.

---

## Phase 5: User Story 3 - Fall back to sequential execution when isolation isn't warranted (Priority: P2)

**Goal**: Never create a worktree for a single-feature wave or a non-git repository (FR-004,
FR-005), preserving today's behavior byte-for-byte (SC-004).

**Independent Test**: Feed a single-feature wave and a `is_git_repo: false` context and assert
`plan_worktree`/`compute_waves` callers never invoke `run_git`.

### Tests for User Story 3

- [x] T021 [P] [US3] `test_single_feature_wave_skips_worktree_creation` in
      `spec-master/tests/test_worktree.py` (Acceptance Scenario 1, FR-004)
- [x] T022 [P] [US3] `test_non_git_repo_falls_back_to_sequential` in
      `spec-master/tests/test_worktree.py` (Acceptance Scenario 2, FR-005)

### Implementation for User Story 3

- [x] T023 [US3] Add the single-feature-wave and `is_git_repo=False` short-circuit guards to
      `plan_worktree` (return a `null`/no-op handle sentinel instead of calling `run_git`) in
      `spec-master/lib/worktree.py` (FR-004, FR-005) — depends on T011, T021, T022

**Checkpoint**: All three user stories independently functional; sequential/non-git paths are
provably unchanged.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [x] T024 [P] Run `python3 -m unittest discover -s spec-master/tests -v` and confirm the full
      suite passes with zero modifications to any pre-existing test file (SC-004)
- [x] T025 [P] Update `plan`/`task` columns of the 10 traceability rows for FR-001..FR-010 via
      `traceability add` (state.json), pointing at this tasks.md and plan.md
- [x] T026 Run `quickstart.md` validation end-to-end and confirm every documented command
      produces the expected output shape

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories (T003's `run_git` is
  used by every story)
- **US1 (Phase 3)**: Depends on Foundational only
- **US2 (Phase 4)**: Depends on Foundational only — independently testable from US1, though in
  practice consumes US1's `Worktree Handle` output at integration time
- **US3 (Phase 5)**: Depends on Foundational + US1's `plan_worktree` signature (T011) since it
  adds guards to the same function
- **Polish (Phase 6)**: Depends on US1 + US2 + US3 complete

### Parallel Opportunities

- T005, T006, T007, T008, T009 (US1 tests) run in parallel — different test functions, same
  file, no shared mutable state
- T014–T017 (US2 tests) run in parallel with each other and with US1 tasks once Foundational
  is done
- T021, T022 (US3 tests) can be written in parallel with US1/US2 work, but T023's
  implementation must land after T011 exists

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 → Phase 2 → Phase 3 (US1)
2. **STOP and VALIDATE**: `compute_waves` + `plan_worktree` + `resolve_project_root` tests
   green, quickstart.md's first two sections pass
3. This alone delivers the spec's core value proposition (concurrent isolated execution)

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. US1 → validate independently (MVP)
3. US2 → validate independently (safe aggregation/conflict reporting)
4. US3 → validate independently (regression guarantee)
5. Polish

---

## Notes

- [P] tasks touch different functions/tests in the same two files (`worktree.py`,
  `test_worktree.py`) with no shared mutable state — safe to parallelize by task, not by file
  lock
- Every implementation task has a corresponding test task ordered before it in this file,
  consistent with Principle III's test-first framing
- No task touches `feature_model.py` — wave computation is strictly additive on top of its
  existing `order_features()` output (plan.md Constitution Check, Principle VI)
