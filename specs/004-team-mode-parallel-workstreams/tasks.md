# Tasks: Team Mode Parallel Workstreams

**Input**: Design documents from `specs/004-team-mode-parallel-workstreams/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/cli-workstreams.md](contracts/cli-workstreams.md)

**Tests**: Included — constitution Principle III requires every `spec-master/lib/` module to
ship a mirrored `spec-master/tests/test_<module>.py`.

**Organization**: Grouped by user story (US1/US2/US3 from spec.md).

## Path Conventions

Single project: `spec-master/lib/`, `spec-master/tests/`.

---

## Phase 1: Setup

- [ ] T001 Create `spec-master/lib/team_workstreams.py` module skeleton (module docstring per
      research.md, `from __future__ import annotations`, no logic yet)
- [ ] T002 Create `spec-master/tests/test_team_workstreams.py` skeleton mirroring the
      `_pathfix`/import pattern used by `spec-master/tests/test_worktree.py`

---

## Phase 2: User Story 1 - Run independent packages concurrently via reused worktree mechanism (Priority: P1)

**Goal**: No new code for waves/worktrees/conflicts — confirm via a smoke-level test that the
existing `worktree.py` CLI/functions work unchanged when fed package data.

**Independent Test**: Feed two packages sharing a `feature_id` with no `depends_on` edge between
them into `worktree.compute_waves` (mapped per contracts/cli-workstreams.md) and assert both land
in the same wave.

### Tests for User Story 1

- [ ] T003 [P] [US1] `test_worktree_compute_waves_accepts_package_shaped_input` in
      `spec-master/tests/test_team_workstreams.py` (Acceptance Scenario 1) — asserts
      `worktree.compute_waves` groups two packages with the same `feature_id` and no
      `depends_on` edge into the same wave, once each is mapped to
      `{"id": p["id"], "dependencies": p["depends_on"]}` (no new function under test — this
      documents/locks in the reuse contract from research.md #2)

### Implementation for User Story 1

- [ ] T004 [US1] No implementation task — `worktree.compute_waves`/`plan_worktree` are reused
      unchanged (research.md #2); T003 is the only artifact for this story

**Checkpoint**: Package-level wave grouping and worktree creation confirmed to work via the
existing, unmodified `worktree.py` surface.

---

## Phase 3: User Story 2 - Gate integration on recorded peer review and Tech Lead approval (Priority: P1)

**Goal**: Add the one genuinely new capability — verdict recording with peer-review identity
enforcement, and verdict-aware aggregation (FR-004..FR-008).

**Independent Test**: Record a review verdict from the wrong agent and assert it is rejected;
record it from the correct `reviewer_agent` and assert it is accepted; aggregate before/after
both verdicts are `APPROVED` and assert `integration_state` changes accordingly.

### Tests for User Story 2

- [ ] T005 [P] [US2] `test_record_review_verdict_rejects_non_assigned_reviewer` in
      `spec-master/tests/test_team_workstreams.py` (research.md #3) — package has
      `reviewer_agent: "fullstack-dev"`; calling with `reviewer_agent="backend-dev"` raises
      `ValueError`
- [ ] T006 [P] [US2] `test_record_review_verdict_accepts_assigned_reviewer` in
      `spec-master/tests/test_team_workstreams.py` — sets `review_verdict.status` to
      `"APPROVED"` with the matching `reviewer_agent`
- [ ] T007 [P] [US2] `test_record_review_verdict_requires_reason_when_rejected` in
      `spec-master/tests/test_team_workstreams.py` (data-model.md) — `status="REJECTED"` with no
      `reason` raises `ValueError`
- [ ] T008 [P] [US2] `test_record_integration_verdict_approved` in
      `spec-master/tests/test_team_workstreams.py` — sets `integration_verdict.status` to
      `"APPROVED"`, no agent argument accepted (research.md #4)
- [ ] T009 [P] [US2] `test_integration_state_transitions` in
      `spec-master/tests/test_team_workstreams.py` (Acceptance Scenarios 1-3, data-model.md) —
      table-driven: no verdicts → `review_pending`; review approved only →
      `integration_pending`; both approved → `integration_ready`; either rejected → `rejected`
- [ ] T010 [P] [US2] `test_aggregate_with_verdicts_annotates_integration_state` in
      `spec-master/tests/test_team_workstreams.py` (Acceptance Scenario 3, FR-008) — calls
      `worktree.aggregate` output through `aggregate_with_verdicts` and asserts each entry gains
      `integration_state` without altering `worktree.aggregate`'s existing fields

### Implementation for User Story 2

- [ ] T011 [US2] Implement `record_review_verdict(packages: list[dict], package_id: str,
      reviewer_agent: str, status: str, reason: str | None = None) -> list[dict]` in
      `spec-master/lib/team_workstreams.py` (FR-004, FR-006, research.md #3) — depends on T005,
      T006, T007
- [ ] T012 [US2] Implement `record_integration_verdict(packages: list[dict], package_id: str,
      status: str, reason: str | None = None) -> list[dict]` in
      `spec-master/lib/team_workstreams.py` (FR-005, FR-006, research.md #4) — depends on T008
- [ ] T013 [US2] Implement `integration_state(package: dict) -> str` in
      `spec-master/lib/team_workstreams.py` (data-model.md) — depends on T009
- [ ] T014 [US2] Implement `aggregate_with_verdicts(wave_index: int, handles: list[dict],
      packages: list[dict]) -> dict` in `spec-master/lib/team_workstreams.py`, calling
      `worktree.aggregate` then annotating each entry via `integration_state` (FR-008) —
      depends on T010, T013
- [ ] T015 [US2] Wire `workstreams review`, `workstreams integrate`, `workstreams aggregate` CLI
      verbs to T011/T012/T014 in `spec-master/lib/cli.py` per contracts/cli-workstreams.md,
      including the file load/mutate/save cycle for `--file`/`--packages` (research.md #1) —
      depends on T011, T012, T014

**Checkpoint**: Peer review cannot be self-recorded or spoofed; a package is never reported
integration-ready without both explicit approvals.

---

## Phase 4: User Story 3 - Reuse, never duplicate, the worktree/conflict/aggregation mechanism (Priority: P1)

**Goal**: Prove structurally — not just by convention — that `team_workstreams.py` calls into
`worktree.py` rather than reimplementing wave/worktree/conflict/aggregate logic (spec.md User
Story 3 Acceptance Scenarios 1-2, SC-003's "verified by code inspection / mocking those exact
call sites" requirement).

**Independent Test**: Mock-patch `worktree.aggregate` and assert `aggregate_with_verdicts` calls
it exactly once rather than recomputing an aggregation result itself; inspect
`team_workstreams.py`'s own namespace and assert it defines no function that duplicates
`compute_waves`/`plan_worktree`/`conflicts`.

### Tests for User Story 3

- [ ] T016 [P] [US3] `test_aggregate_with_verdicts_calls_worktree_aggregate` in
      `spec-master/tests/test_team_workstreams.py` — patches `team_workstreams.worktree.aggregate`
      and asserts `aggregate_with_verdicts` calls it exactly once with `(wave_index, handles)`
      rather than recomputing the result itself (spec.md US3 Acceptance Scenario, SC-003)
- [ ] T017 [P] [US3] `test_team_workstreams_defines_no_duplicate_wave_or_worktree_logic` in
      `spec-master/tests/test_team_workstreams.py` — asserts
      `{"compute_waves", "plan_worktree", "conflicts"}.isdisjoint(dir(team_workstreams))`, i.e. no
      function under those names is defined in the new module itself (spec.md User Story 3,
      research.md #2's rejected-wrapper decision)

### Implementation for User Story 3

- [ ] T018 [US3] No implementation task — T016/T017 assert an existing property of T011-T014's
      implementation (calls `worktree.aggregate`, defines no competing wave/worktree/conflict
      function); if either assertion fails, the fix is in T014, not a new task here — depends on
      T014

**Checkpoint**: The reuse contract from research.md #2 is enforced by tests, not just by review
convention — a future edit that reimplements wave/worktree/conflict/aggregate logic in
`team_workstreams.py` fails the suite.

---

## Phase 5: Polish & Cross-Cutting Concerns

- [ ] T019 [P] Run `python3 -m unittest discover -s spec-master/tests -v` and confirm the full
      suite passes with zero modifications to `test_team_model.py` or `test_worktree.py` (SC-004)
- [ ] T020 [P] Add/update traceability rows for FR-001..FR-010 via direct `state.json` edit
      (`traceability add` only appends; existing rows use the update-in-place pattern from
      `parallel-worktree-execution`'s validate phase), pointing at this tasks.md and plan.md
- [ ] T021 Run `quickstart.md` validation end-to-end (mocked `workstreams.json` fixture) and
      confirm every documented command produces the expected output shape

---

## Dependencies & Execution Order

- **Setup (Phase 1)**: No dependencies
- **US1 (Phase 2)**: Depends on Setup only — locks in the reuse contract, no new code
- **US2 (Phase 3)**: Depends on Setup only — independent of US1 (different functions entirely)
- **US3 (Phase 4)**: Depends on US2 (T014) — verifies a property of `aggregate_with_verdicts`
- **Polish (Phase 5)**: Depends on US1 + US2 + US3 complete

### Parallel Opportunities

- T005-T010 (US2 tests) run in parallel — different test functions, same file
- US1 (T003) and US2 (T005-T010) can be written in parallel — no shared code path
- T016-T017 (US3 tests) run in parallel with each other once T014 lands

## Notes

- No task touches `team_model.py` or `worktree.py` — this feature is strictly additive on top of
  both (plan.md Constitution Check, Principle VI)
- Every implementation task has a corresponding test task ordered before it, consistent with
  Principle III's test-first framing
