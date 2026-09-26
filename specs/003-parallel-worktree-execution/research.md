# Phase 0 Research: Parallel Worktree Execution

**Input**: [spec.md](spec.md), constitution Principles I, II, III, V, VI, IX

## Unknowns from Technical Context

### 1. Concurrency bound per wave (deferred from `/speckit-clarify`)

- **Decision**: No hardcoded numeric cap in the core library. `wave.compute_waves()` returns
  the full membership of each wave; the *caller* (controller/adapter) decides how many
  worktrees it actually drives concurrently (e.g. bounded by `os.cpu_count()` or an adapter
  concurrency setting), exactly the same separation already used for phase execution timeouts
  in `execution_mode.py`.
- **Rationale**: Principle I reserves *structural* decisions for the deterministic core; how
  many OS processes/coroutines an adapter is willing to run at once is an adapter-level
  resource policy, not a spec-level requirement — the spec's own SC-001 only requires
  wall-clock no worse than the slowest single feature, which holds under any concurrency ≥
  the wave's true critical path.
- **Alternatives considered**: Hardcoding a cap (e.g. 4) in `spec-master/lib/` — rejected,
  violates Principle I (bakes an adapter-level resource policy into the deterministic core)
  and would need re-justification per hardware; making it a required CLI flag — rejected as
  needless mandatory surface area for a v1 that already has a safe default (full wave
  membership, caller-bounded).

### 2. Worktree path convention

- **Decision**: `.spec-master/worktrees/<feature-id>/`, matching the pattern already used by
  `.spec-master/failed-attempts/` (Principle V) and `.spec-master/logs/` (`phase_runner.py`).
- **Rationale**: Consistent, discoverable location under the existing `.spec-master/` state
  directory; feature-id is already the unique key used throughout `state.json`.
- **Alternatives considered**: A temp directory outside the repo — rejected, violates FR-008
  (must survive interruption/resume) since OS temp dirs are not guaranteed durable across
  reboots and are outside the existing `.spec-master/` convention a human already knows to
  look in per Principle V.
- **Idempotency note (added during `/speckit-analyze` repair cycle 1)**: `plan_worktree` MUST
  check whether `.spec-master/worktrees/<feature-id>` already exists before calling
  `git worktree add`; if it does, the existing directory is reused/resumed, never recreated
  or deleted first — this is the literal mechanism behind spec.md's Edge Case 3 and SC-003.

### 3. Git worktree invocation boundary

- **Decision**: A new `spec-master/lib/worktree.py` module exposes pure functions
  (`compute_waves`, `aggregate`, `resolve_project_root`) and two functions that perform real
  I/O through a single boundary (`plan_worktree`, `conflicts`), plus a thin `run_git(args, cwd)`
  wrapper around `subprocess.run`, called exactly once per git operation — mirroring the existing
  `phase_runner.py::_run_quality_gates` / `opencode_runner.py` pattern, where tests patch the
  subprocess call directly (`unittest.mock.patch("worktree.subprocess.run", ...)`) rather than
  requiring a real git repository or real concurrent processes.
- **Rationale**: This is the exact same mockable-boundary shape already proven in two other
  modules in this codebase (Principle III is satisfied by precedent, not a new pattern).
- **Alternatives considered**: A `GitBackend` protocol/class with a fake implementation for
  tests — rejected as unnecessary abstraction; the existing codebase's convention is a single
  wrapped function per external call, not a class hierarchy (simplicity per Principle I).

### 4. Conflict detection mechanism (FR-007)

- **Decision**: Use `git merge-tree` (or `git diff --name-only` intersection between worktree
  branches as a first pass) to detect file-level overlap without mutating any branch — run
  read-only, output parsed into `{feature_a, feature_b, files: [...]}` conflict records.
- **Rationale**: `git merge-tree` is a read-only plumbing command designed exactly for
  conflict-preview without touching the working tree or index of either side, matching FR-007
  ("MUST NOT automatically resolve or discard either side").
- **Alternatives considered**: Actually attempting `git merge` and reading its exit code —
  rejected, a real merge attempt mutates the worktree even on failure (leaves conflict markers,
  MERGE_HEAD, etc.), which FR-007 explicitly forbids equating with "discard".

### 5. Phase-loop isolation enforcement point (added during `/speckit-analyze` repair cycle 1)

- **Decision**: `worktree.py` exposes `resolve_project_root(handle: dict) -> str`, returning
  `handle["path"]`. Any caller (controller or agent) driving a feature's phase loop inside a
  wave MUST pass this value as that phase loop's project root for every
  `phase_runner`/`controller` call made during that feature's execution.
- **Rationale**: FR-003 ("phase loop MUST only read/write files inside that worktree's own
  directory") is enforced by every existing phase-execution function already being scoped to
  an explicit `project: Path` argument (`phase_runner.py`'s `_run_quality_gates`,
  `_run_opencode`, etc.) — isolation is achieved by *which path the caller passes*, not by new
  sandboxing logic in the core. Naming this accessor makes the contract explicit and testable
  instead of an implicit assumption a future caller could miss.
- **Alternatives considered**: Building a new path-sandboxing/jail mechanism in
  `spec-master/lib/` — rejected as duplicating `phase_contracts.py`'s existing
  `_symlink_escapes_project` boundary-checking pattern, which already exists and applies
  per-project regardless of which project root (main tree or worktree) is passed in.

## Output

All Technical Context unknowns resolved; no `NEEDS CLARIFICATION` markers remain.
