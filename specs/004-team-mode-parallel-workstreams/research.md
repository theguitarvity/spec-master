# Phase 0 Research: Team Mode Parallel Workstreams

**Input**: [spec.md](spec.md), constitution Principles I, II, III, V, VI

## Unknowns from Technical Context

### 1. Verdict storage location

- **Decision**: Review/integration verdicts are stored as new fields directly on each package
  object inside `.spec-master/workstreams.json` — `review_verdict: {status, reviewer_agent,
  reason}` and `integration_verdict: {status, reason}`, both defaulting to `{status: "PENDING",
  ...}` when absent (old `workstreams.json` files without these fields remain valid — backwards
  compatible per Principle VI).
- **Rationale**: `workstreams.json` is already the single source of truth for package definitions
  (`team_model.py::build_workstreams`); a human already knows to look there (Principle V) instead
  of a second file that could drift out of sync. The new `spec-master/lib/team_workstreams.py`
  module stays pure (functions take/return the packages list), and `cmd_workstreams` in `cli.py`
  owns the load-mutate-save of the file — the exact same split `cmd_state` already uses for
  `state.json`.
- **Alternatives considered**: A separate `.spec-master/team/verdicts.json` — rejected, adds a
  second file that must be kept consistent with package ids for no benefit; storing verdicts in
  `.spec-master/state.json` — rejected, that file is about phase/workflow state, not Team Mode
  package data, and mixing concerns there would violate the existing separation between
  `state.json` and `workstreams.json`.

### 2. Wave computation and worktree creation at package granularity

- **Decision**: No new wave-computation or worktree-creation code. `worktree.compute_waves` is
  called directly by the orchestrating agent with each package mapped to
  `{"id": package["id"], "dependencies": package["depends_on"]}`; `worktree.plan_worktree` is
  called directly with the package id passed as its `feature_id` argument. Both already exist,
  are already tested, and are already generic over what a "feature id" string represents.
- **Rationale**: `worktree.py`'s functions never inspect what an id "means" — they only use it as
  a path/lookup key. Adding a second, Team-Mode-specific wave/worktree module would duplicate
  logic already proven correct (Principle VI, DRY). The only genuinely new behavior this feature
  adds is verdict recording and verdict-aware aggregation (research #3).
- **Alternatives considered**: A `team_workstreams.compute_package_waves()` wrapper that just
  renames the field and forwards to `worktree.compute_waves` — rejected as a needless
  pass-through layer (no logic difference, just call-site convenience); left as documentation
  (contracts/cli-workstreams.md) instead of code, consistent with "don't design for hypothetical
  future requirements."

### 3. Peer-review identity enforcement

- **Decision**: `record_review_verdict` MUST reject a verdict whose `reviewer_agent` argument
  does not match the package's own assigned `reviewer_agent` (from `team_model.py
  ::assign_peer_review`), raising a `ValueError` the CLI surfaces as a non-zero exit.
- **Rationale**: `conflict_policy.rules` already documents "no implementation package is complete
  until a **different** dev agent reviews it" — today nothing enforces "different"; a package's
  own owner could otherwise record their own approval. Checking identity against the already-
  computed `reviewer_agent` field turns this from prose into an enforced structural gate, which
  is exactly this feature's stated purpose (spec.md User Story 2) at negligible cost (the field
  already exists on every package).
- **Alternatives considered**: Trusting the caller to pass the right `reviewer_agent` — rejected,
  that is exactly the un-enforced status quo this feature exists to fix.

### 4. Integration verdict authority

- **Decision**: `record_integration_verdict` does not take an `agent` argument at all — Team
  Mode's `technical_owner` is always `"tech-lead"` (a `build_workstreams()` constant), so there is
  only one possible integration-approving role; recording who is implicit rather than a free-text
  field that could be spoofed.
- **Rationale**: Matches `team_model.py`'s own design (`technical_owner: "tech-lead"` is already
  a fixed constant in `build_workstreams`'s output, not a per-call parameter) — no new
  configurability is introduced where none existed before (Principle I: simplicity).
- **Alternatives considered**: Accepting an `agent` argument and validating it equals
  `"tech-lead"` — rejected as strictly equivalent but more surface area for the same guarantee.

## Output

All Technical Context unknowns resolved; no `NEEDS CLARIFICATION` markers remain.
