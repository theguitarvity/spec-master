# Validation Report: Parallel Worktree Execution

**Phase**: validate (no Spec Kit prompt template exists for this phase — executed directly
against PROTOCOL.md Section 7's QA-validates-against-acceptance-criteria guidance, standing in
for QA in Auto Mode).

**Evidence sources**: `spec-master/tests/test_worktree.py` (11 mocked unit tests, all passing —
see `spec-master/tests/test_worktree.py`) plus a real, throwaway git repository exercised
manually in this session (real `worktree plan` creation, real idempotent reuse, real
`worktree conflicts` detection against genuinely overlapping and non-overlapping files) — not
mocks alone.

## Acceptance Criteria

1. **"Features with no dependency edge between them can execute in isolated git worktrees
   concurrently"** — PASS. `ComputeWavesTests` (both cases) plus `PlanWorktreeTests
   ::test_plan_worktree_creates_handle_per_feature_in_multi_feature_wave` confirm independent
   features land in the same wave and each gets its own non-overlapping worktree path.

2. **"Each worktree runs exactly one feature's full phase loop without touching another
   feature's files"** — PASS. `ResolveProjectRootTests` plus `resolve_project_root()`'s
   documented contract (research.md #5) give the caller an explicit, testable project-root
   value; the real-repo smoke test confirmed two worktrees have independent working
   directories.

3. **"Results (branch/diff/status) are aggregated back and merge conflicts are reported, never
   auto-resolved"** — PASS. `ConflictsTests` (both cases) plus the real-repo smoke test
   correctly identified only the genuinely overlapping file. `AggregateTests
   ::test_aggregate_preserves_blocked_worktree_directory` confirms a non-terminal handle is
   never mutated or deleted (FR-008); `conflicts()` only ever calls read-only git plumbing
   (`rev-parse`, `merge-base`, `diff --name-only` — confirmed by code inspection), never
   `git merge`.

## Success Criteria (spec.md)

- **SC-001** (wave wall-clock no worse than the slowest single feature) — **PARTIAL / scope
  boundary, not a defect**. `compute_waves` delivers the structural primitive (grouping
  independent features into the same wave) that makes concurrent execution *possible*, but
  actually driving concurrent phase loops is caller-bounded by design (research.md #1: "the
  caller decides how many worktrees it actually drives concurrently") and plan.md's Scale/Scope
  limits this feature's deliverable to `worktree.py` + `cli.py` — no controller/execution-mode
  integration is in tasks.md. Full realization of SC-001 requires a follow-on integration task
  wiring `compute_waves`/`plan_worktree` output into an actual concurrent execution driver; that
  is out of this feature's scope as planned, not an implementation gap within it.
- **SC-002** (real conflict reported 100% of the time, never silently merged) — PASS.
  `ConflictsTests` + real-repo smoke test.
- **SC-003** (interrupted worktree always resumable, never loses/discards content) — PASS.
  `test_plan_worktree_reuses_existing_path_without_recreating` + real-repo smoke test's second
  `plan` call reusing the existing directory without error or duplication.
- **SC-004** (single-feature/non-git runs unchanged, byte-for-byte) — PASS.
  `test_single_feature_wave_skips_worktree_creation`,
  `test_non_git_repo_falls_back_to_sequential`. Full suite run
  (`python3 -m unittest discover -s spec-master/tests -v`): 171 tests, all 11 new
  `test_worktree.py` tests pass, zero pre-existing test files modified. 21 pre-existing,
  unrelated `ModuleNotFoundError: No module named 'pytest'` errors exist in
  `test_graph_*`/`test_knowledge_*`/`test_traceability_graph` (files that `import pytest` at
  module level, incompatible with `unittest discover`) — confirmed pre-existing, untouched by
  this feature, not a regression.

## Quality Gates

`gates detect --path .` returned `[]` — no repo-configured lint/test gate files detected beyond
the test suite already run above.

## Verdict

**PASSED**, with one explicitly documented scope boundary (SC-001 — enabled by this feature,
fully realized only once a controller integrates `compute_waves`/`plan_worktree` into an actual
concurrent execution driver, which is a natural candidate for a follow-on feature/task).
