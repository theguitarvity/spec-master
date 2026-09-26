# Tasks: Spec Kit Tracker Orchestration

**Input**: Design documents from `specs/005-speckit-tracker-orchestration/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/cli-tracker.md](contracts/cli-tracker.md)

**Tests**: Included — constitution Principle III requires every `spec-master/lib/` module to
ship a mirrored `spec-master/tests/test_<module>.py`.

**Organization**: Grouped by user story (US1/US2/US3 from spec.md).

## Path Conventions

Single project: `spec-master/lib/`, `spec-master/tests/`.

---

## Phase 1: Setup

- [ ] T001 Create `spec-master/lib/tracker_orchestration.py` module skeleton (module docstring per
      research.md, `from __future__ import annotations`, no logic yet)
- [ ] T002 Create `spec-master/tests/test_tracker_orchestration.py` skeleton mirroring the
      `_pathfix`/temp-directory-fixture pattern used by `spec-master/tests/test_discovery.py`

---

## Phase 2: User Story 1 - Detect installed tracker extensions without inventing presence (Priority: P1)

**Goal**: A manifest-only detection function, following `discovery.py`'s existing "only report what
a file on disk actually proves" precedent.

**Independent Test**: Point `detect_tracker_extensions` at a temp dir with a
`.claude/skills/speckit-taskstoissues/SKILL.md` fixture (real front-matter, copied from the actual
file) and assert it reports one `github_issues` extension; point it at an empty temp dir and assert
an empty list, no exception.

### Tests for User Story 1

- [ ] T003 [P] [US1] `test_detect_tracker_extensions_finds_github_issues_skill` in
      `spec-master/tests/test_tracker_orchestration.py` (Acceptance Scenario 1) — temp dir with a
      `.claude/skills/speckit-taskstoissues/SKILL.md` fixture whose `description` matches
      `speckit-taskstoissues`'s real one; asserts one entry with `tracker_type: "github_issues"`
- [ ] T004 [P] [US1] `test_detect_tracker_extensions_empty_when_no_skills_dir` in
      `spec-master/tests/test_tracker_orchestration.py` (Acceptance Scenario 2) — empty temp dir,
      asserts `[]` and no exception
- [ ] T005 [P] [US1] `test_detect_tracker_extensions_skips_non_tracker_skill` in
      `spec-master/tests/test_tracker_orchestration.py` (Acceptance Scenario 3) — temp dir with a
      `SKILL.md` whose description has no tracker keyword, asserts it is excluded (no false
      positive from directory presence alone)
- [ ] T006 [P] [US1] `test_detect_tracker_extensions_skips_malformed_frontmatter` in
      `spec-master/tests/test_tracker_orchestration.py` (Edge Case: malformed YAML front-matter) —
      asserts silent exclusion, no exception

### Implementation for User Story 1

- [ ] T007 [US1] Implement `detect_tracker_extensions(root: str = ".") -> list[dict]` in
      `spec-master/lib/tracker_orchestration.py` (FR-001, FR-002, research.md #1, #2) — walks
      `.claude/skills/`, `.opencode/skill/`, `.qwen/skill/`, reads each `SKILL.md`'s front-matter,
      classifies `tracker_type` by keyword match, skips silently on parse failure or no keyword
      match — depends on T003, T004, T005, T006
- [ ] T008 [US1] Wire `tracker_extensions` as a new additive field on `discovery.scan()`'s return
      value in `spec-master/lib/discovery.py`, calling `tracker_orchestration
      .detect_tracker_extensions(root)` (FR-003) — depends on T007

**Checkpoint**: `discovery scan` reports real, evidence-backed tracker extensions with zero false
positives and zero new fields changed on any existing key.

---

## Phase 3: User Story 2 - Orchestrate a detected extension instead of reimplementing sync (Priority: P1)

**Goal**: Add the detect-then-instruct entry point and the traceability column that gives a synced
issue link a structural home.

**Independent Test**: Given one detected extension, call `orchestrate` and assert its result names
the exact skill/command with no tracker-API call of its own; add a traceability row with an `issue`
value and assert it renders in the matrix without disturbing other columns.

### Tests for User Story 2

- [ ] T009 [P] [US2] `test_orchestrate_returns_invocation_for_detected_extension` in
      `spec-master/tests/test_tracker_orchestration.py` (Acceptance Scenario 1) — one fixture
      extension, asserts `orchestrated: True` and `invocations == [{"skill": ..., "tracker_type":
      ..., "command": "/speckit-taskstoissues"}]`
- [ ] T010 [P] [US2] `test_orchestrate_lists_all_when_multiple_detected` in
      `spec-master/tests/test_tracker_orchestration.py` (Acceptance Scenario 2) — two fixture
      extensions under different integration dirs, asserts both appear, neither is dropped
- [ ] T011 [P] [US2] `test_traceability_add_row_issue_defaults_empty` in
      `spec-master/tests/test_tracker_orchestration.py` (data-model.md; imports `traceability`
      directly — does not modify `test_traceability.py`, per SC-004) — `add_row` without `issue`
      renders `""` in the new `Issue` column, every other column unaffected
- [ ] T012 [P] [US2] `test_traceability_add_row_with_issue_renders_in_matrix` in
      `spec-master/tests/test_tracker_orchestration.py` (Acceptance Scenario 3) — `add_row` with
      `issue="https://github.com/x/y/issues/1"`, asserts `render()` includes it

### Implementation for User Story 2

- [ ] T013 [US2] Implement `orchestrate(root: str = ".") -> dict` in
      `spec-master/lib/tracker_orchestration.py` (FR-004, FR-005, research.md #3) — calls
      `detect_tracker_extensions`, builds one invocation per extension, never performs a network
      call — depends on T009, T010
- [ ] T014 [US2] Add `"issue"` to `_COLUMNS`/`_HEADERS` in `spec-master/lib/traceability.py`
      (FR-007, research.md #4) — depends on T011, T012
- [ ] T015 [US2] Wire `tracker orchestrate` CLI verb in `spec-master/lib/cli.py` per
      contracts/cli-tracker.md (no new flag needed on `traceability add` — its existing
      `--row-file`/`--row-json` mechanism already passes an `"issue"` key through once T014 lands)
      — depends on T013, T014

**Checkpoint**: A detected extension produces an unambiguous, network-free invocation instruction;
a synced issue link has a structural home in the traceability matrix.

---

## Phase 4: User Story 3 - Absence of any tracker extension never blocks the workflow (Priority: P1)

**Goal**: Prove structurally that zero detection is a normal, non-blocking result, and that no
tracker-sync/network logic was introduced anywhere in `spec-master/lib/`.

**Independent Test**: Run `orchestrate` against an empty temp dir and assert `orchestrated: False`
with a reason and no exception; inspect `tracker_orchestration.py`'s own source for forbidden
network-library imports.

### Tests for User Story 3

- [ ] T016 [P] [US3] `test_orchestrate_returns_false_when_nothing_detected` in
      `spec-master/tests/test_tracker_orchestration.py` (Acceptance Scenario 1, spec.md US3) —
      empty temp dir, asserts `{"orchestrated": False, "extensions": [], "invocations": [],
      "reason": <non-empty str>}`, no exception raised
- [ ] T017 [P] [US3] `test_tracker_orchestration_module_has_no_network_imports` in
      `spec-master/tests/test_tracker_orchestration.py` (SC-003) — reads
      `spec-master/lib/tracker_orchestration.py`'s own source text and asserts none of
      `"import requests"`, `"import urllib"`, `"import http.client"`, `"import socket"` appear

### Implementation for User Story 3

- [ ] T018 [US3] No implementation task — T016/T017 assert an existing property of T007/T013's
      implementation (returns a clean non-blocking result on empty detection; imports nothing
      network-capable); if either assertion fails, the fix is in T007/T013, not a new task here —
      depends on T013

**Checkpoint**: The "never blocks on absence, never reimplements a tracker client" contract from
research.md #3 is enforced by tests, not just by review convention.

---

## Phase 5: Polish & Cross-Cutting Concerns

- [ ] T019 [P] Run `python3 -m unittest discover -s spec-master/tests -v` and confirm the full
      suite passes with zero modifications to `test_discovery.py` or `test_traceability.py` (SC-004)
- [ ] T020 [P] Add/update traceability rows for FR-001..FR-008 via direct `state.json` edit,
      pointing at this tasks.md and plan.md
- [ ] T021 Run `quickstart.md` validation end-to-end against this repository's own
      `.claude/skills/speckit-taskstoissues/SKILL.md` and confirm every documented command
      produces the expected output shape

---

## Dependencies & Execution Order

- **Setup (Phase 1)**: No dependencies
- **US1 (Phase 2)**: Depends on Setup only
- **US2 (Phase 3)**: Depends on US1 (T007) for detection to orchestrate over, and Setup for the
      traceability column
- **US3 (Phase 4)**: Depends on US2 (T013) — verifies properties of `orchestrate`
- **Polish (Phase 5)**: Depends on US1 + US2 + US3 complete

### Parallel Opportunities

- T003-T006 (US1 tests) run in parallel — different test functions, same file
- T009-T012 (US2 tests) run in parallel with each other once fixtures from US1 exist
- T016-T017 (US3 tests) run in parallel with each other once T013 lands

## Notes

- No task touches `discovery.py`'s existing scan functions' behavior, `team_model.py`,
  `worktree.py`, or `team_workstreams.py` — this feature is strictly additive (plan.md Constitution
  Check, Principle VI)
- No task adds a tracker-sync/network dependency anywhere — Principle VII, enforced by T017
- Every implementation task has a corresponding test task ordered before it, consistent with
  Principle III's test-first framing
- All task ids follow the strict `T\d{3}` sequential pattern (no lettered suffixes) so they remain
  compatible with `speckit-taskstoissues`'s own `\bT\d{3,}\b` dedup-matching regex if this
  `tasks.md` is ever run through that skill directly (analyze-phase repair, cycle 1)
