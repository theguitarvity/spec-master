# Feature Specification: Parallel Worktree Execution

**Feature Branch**: `003-parallel-worktree-execution` (trunk-based: no dedicated branch created, isolated logically under this directory)

**Created**: 2026-09-26

**Status**: Draft

**Input**: User description: "Paralelização real de features independentes via git worktrees. O grafo de dependências e a ordenação topológica já existem em `feature_model.py`; falta o mecanismo de execução paralela isolada por worktree e a agregação/merge dos resultados." (docs/market-benchmark-roadmap.md, Tier 1, item 1)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Execute independent features concurrently in isolated worktrees (Priority: P1)

An operator running `/spec-master` against a context with several
independent features (no dependency edge between them) wants the workflow
to execute them concurrently instead of one at a time, to shorten total
wall-clock time. Spec Master computes the execution order via
`features order` (already deterministic), groups features into "waves" —
features with no unresolved dependency at that point form one wave — and,
for each feature in a wave with more than one member, creates an isolated
`git worktree` before driving that feature's phase loop, so no two
features can write to each other's files mid-run.

**Why this priority**: This is the core value proposition of the feature —
without concurrent isolated execution, "parallel worktree execution" does
not exist; it is Tier 1 item 1 in the benchmark and a direct dependency of
Tier 1 item 2 (Team Mode parallel workstreams).

**Independent Test**: Can be fully tested by feeding a features list with
two independent features (no shared dependency) into the wave-grouping
function and asserting both appear in the same wave, then asserting a
worktree is created/removed for each and that the two features' output
directories never overlap.

**Acceptance Scenarios**:

1. **Given** a resolved feature order from `features order` with two
   features that have no dependency edge between them, **When** the
   workflow computes execution waves, **Then** both features are placed in
   the same wave and are eligible for concurrent worktree execution.
2. **Given** a wave with more than one feature, **When** execution starts
   for that wave, **Then** a separate `git worktree` is created per
   feature under a dedicated path (e.g. `.spec-master/worktrees/<feature-id>`),
   and each feature's phase loop runs only inside its own worktree.
3. **Given** a feature depends on another feature, **When** waves are
   computed, **Then** the dependent feature is placed in a strictly later
   wave than its dependency, never the same or an earlier one.

---

### User Story 2 - Aggregate and report worktree results, never auto-merge conflicts (Priority: P1)

After a wave finishes, the operator needs a clear picture of what
happened in each worktree: whether the feature's phase loop passed, what
changed, and — critically — whether merging that worktree's branch back
would conflict. Spec Master aggregates each worktree's final phase status
and diff summary into the workflow's own report, and if merging a
worktree's changes back onto the base branch would conflict, it reports
the conflict (files, feature id) instead of attempting any automatic
resolution.

**Why this priority**: Without safe, honest aggregation, parallel
execution is unusable in practice — a silently-eaten merge conflict would
corrupt work. This directly implements constitution Principle V
(Non-Destructive Recovery).

**Independent Test**: Can be fully tested by simulating two worktrees that
touch the same file with conflicting changes, running the aggregation
step, and asserting the result reports a conflict for that pair without
having modified either worktree's content.

**Acceptance Scenarios**:

1. **Given** a wave of worktrees has finished their phase loops, **When**
   results are aggregated, **Then** each feature's final phase status
   (PASSED/FAILED/BLOCKED) and the list of changed files are recorded in
   the workflow report.
2. **Given** two worktrees in the same wave both modified the same file in
   incompatible ways, **When** the aggregation step attempts to reconcile
   them onto the base branch, **Then** the result reports a merge conflict
   naming both feature ids and the file, and neither worktree's content is
   discarded or force-merged.
3. **Given** a worktree's feature reached `BLOCKED` or `FAILED`, **When**
   the wave is aggregated, **Then** that worktree's directory is preserved
   (not deleted) so a human can inspect it, consistent with Principle V.

---

### User Story 3 - Fall back to sequential execution when isolation isn't warranted (Priority: P2)

For a wave containing exactly one feature, or when the repository doesn't
support `git worktree` (e.g. not a git repository, or worktrees disabled),
Spec Master runs that feature directly on the working tree, exactly as it
does today, without creating an unnecessary worktree.

**Why this priority**: Keeps the existing sequential, single-feature
behavior (constitution Principle VI, Backwards-Compatible Evolution)
fully intact — parallel execution is additive, never a required path.

**Independent Test**: Can be fully tested by feeding a single-feature wave
and asserting no worktree is created — the feature runs against the
current working directory exactly like the pre-existing sequential path.

**Acceptance Scenarios**:

1. **Given** a wave with exactly one feature, **When** that wave executes,
   **Then** no git worktree is created and the feature's phase loop runs
   directly against the current working tree.
2. **Given** `is_git_repo` is `false` in `discovery scan`, **When** wave
   execution is attempted, **Then** the workflow falls back to fully
   sequential execution (one feature at a time, current working tree) and
   records that worktrees were unavailable.

### Edge Cases

- What happens when a worktree's feature never reaches a terminal phase
  status (still `RUNNING`) and the process is interrupted? The worktree
  directory MUST remain on disk (never auto-deleted) so a resumed run can
  detect and continue it, per Principle V.
- How does the system handle a wave where one feature in the wave fails
  its `analyze` repair cycles (reaches `BLOCKED`) while a sibling in the
  same wave is still running? The sibling continues independently; the
  blocked feature does not halt the rest of the wave.
- What happens if the target path for a new worktree already exists (e.g.
  from a prior interrupted run)? The existing worktree is reused/resumed
  rather than recreated, consistent with the state machine's own
  resume-vs-restart handling (fingerprint compare on that feature's own
  artifacts).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST compute execution "waves" from the output of
  `features order`, where a wave is the maximal set of not-yet-executed
  features whose dependencies have all reached a terminal `PASSED` status.
- **FR-002**: For any wave containing more than one feature, the system
  MUST create one isolated `git worktree` per feature in that wave before
  starting that feature's phase loop.
- **FR-003**: Each feature's phase loop, when running inside a worktree,
  MUST only read/write files inside that worktree's own directory.
- **FR-004**: The system MUST NOT create a worktree for a wave containing
  exactly one feature; that feature runs directly on the current working
  tree.
- **FR-005**: The system MUST NOT create worktrees when `is_git_repo` is
  `false` in `discovery scan`; execution falls back to fully sequential,
  current-working-tree execution.
- **FR-006**: After a wave finishes, the system MUST aggregate each
  feature's final phase status and changed-file list into a single
  report structure.
- **FR-007**: When two or more worktrees in the same wave modify the same
  file in incompatible ways, the system MUST report the conflict
  (feature ids + file paths) and MUST NOT automatically resolve or
  discard either side.
- **FR-008**: A worktree whose feature did not reach a terminal status
  (`PASSED`, `FAILED`, or `BLOCKED`) MUST NOT be deleted by the system.
- **FR-009**: All new worktree-orchestration logic MUST live in
  `spec-master/lib/` as pure, testable Python, exposed via
  `spec-master/lib/cli.py`, per constitution Principle I.
- **FR-010**: The underlying `git worktree add`/`git worktree remove`
  invocations MUST go through a boundary that can be mocked in tests, per
  constitution Principle III — tests MUST NOT require a real git
  repository with real concurrent processes to pass.

### Key Entities

- **Execution Wave**: An ordered group of feature ids that can run
  concurrently because none of them depends on another still-pending
  feature in the same or a later wave.
- **Worktree Handle**: The association between a feature id, its
  filesystem path under `.spec-master/worktrees/<feature-id>`, and its
  current lifecycle state (created, running, finished, conflict-pending).
- **Aggregation Result**: The per-wave report of each feature's final
  phase status, changed files, and any detected merge conflicts.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For a set of N mutually independent features, total
  wall-clock phase-loop execution time is no worse than the slowest
  single feature's own execution time, rather than the sum of all N
  (validated in the deterministic test suite via a mocked worktree
  boundary, not real timing).
- **SC-002**: A wave with a real file-level conflict between two features
  is reported as a conflict 100% of the time in the deterministic test
  suite — never silently merged.
- **SC-003**: An interrupted worktree is always resumable: re-running the
  workflow after an interruption never loses or discards a worktree's
  existing content.
- **SC-004**: Single-feature and non-git-repo runs produce byte-for-byte
  the same phase-loop behavior as before this feature existed (regression
  coverage against the existing sequential test suite).

## Assumptions

- Concurrency is process/coroutine-level within this same Spec Master
  invocation, not a distributed/multi-machine execution model — out of
  scope per the benchmark roadmap's own framing (native worktree support
  in the running agent/runtime, not a new distributed system).
- "Merge back onto the base branch" means applying each worktree's
  resulting changes onto the branch the workflow started from (trunk, per
  this repository's current git strategy); it does not imply creating new
  long-lived feature branches, consistent with constitution's Development
  Workflow section.
- The existing `feature_model.order_features` topological sort remains
  the single source of truth for dependency ordering; wave computation is
  a grouping built on top of its output, not a replacement for it.
- Git itself is available on the host (already a precondition of
  `is_git_repo: true`); no new dependency is introduced to invoke it,
  consistent with constitution Principle II.
