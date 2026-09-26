# Feature Specification: Team Mode Parallel Workstreams

**Feature Branch**: `004-team-mode-parallel-workstreams` (trunk-based: no dedicated branch created, isolated logically under this directory)

**Created**: 2026-09-26

**Status**: Draft

**Input**: User description: "Executar os workstreams do Team Mode (.spec-master/workstreams.json) em paralelo usando o mecanismo de worktree da feature parallel-worktree-execution, respeitando peer review e autoridade de integração do Tech Lead." (docs/market-benchmark-roadmap.md, Tier 1, item 2)

## Grounding (constitution Principle VI)

- `spec-master/lib/team_model.py::build_workstreams(features)` already produces the `workstreams.json`
  shape: `{mode, orchestrator, technical_owner, packages: [{id, feature_id, title, owner_agent,
  reviewer_agent, depends_on, source_task}], lanes: {agent_id: [package_ids]}, conflict_policy}`.
  Today `packages[i].depends_on` is a list of other **package ids** (not feature ids) — a package's
  own prior task in the same feature is chained sequentially by construction.
- `conflict_policy.rules` already documents, as text, that "no implementation package is complete
  until a different dev agent reviews it" and "the tech lead approves integration after peer
  review, QA, and blocking gates" — but nothing in code today enforces either rule; `reviewer_agent`
  is just an assigned string, and `technical_owner: "tech-lead"` is just a label.
- Nothing today reads `workstreams.json` back and drives execution; the CLI's `team workstreams`
  action only prints the planned packages/lanes (`spec-master/lib/cli.py::cmd_team`).
- `spec-master/lib/worktree.py` (built for `parallel-worktree-execution`, already merged) exposes
  `compute_waves(ordered_features)`, `plan_worktree(feature_id, project_root, strategy, wave_size,
  is_git_repo)`, `resolve_project_root(handle)`, `conflicts(path_a, path_b)`, `aggregate(wave_index,
  handles)` — all keyed by a generic `id`/`feature_id` string, none of it Team-Mode-specific. It is
  not yet referenced anywhere in `team_model.py` or the `team` CLI group.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Run independent work packages from the same or different features concurrently (Priority: P1)

A Tech Lead Agent has just produced `.spec-master/workstreams.json` for a set of features. Several
packages have no dependency edge between them — including packages that belong to the *same*
feature but different lanes (e.g. a `backend-dev` package and a `frontend-dev` package for the same
feature, per Team Mode's own division of labor). Spec Master groups these packages into waves using
the same dependency-wave algorithm already proven for whole features, then creates one isolated
`git worktree` per package in any multi-package wave, keyed by package id, before that package's
owner agent starts work — so two agents assigned to the same feature never overwrite each other's
files mid-run.

**Why this priority**: This is Team Mode's actual parallelism claim — without package-level
concurrent isolation, Team Mode "parallel workstreams" is just the existing sequential loop with
extra role labels; it is Tier 1 item 2 and explicitly depends on `parallel-worktree-execution`.

**Independent Test**: Feed a `workstreams.json` packages list where two packages share a
`feature_id` but have no `depends_on` edge between them, group into waves, and assert both land in
the same wave with two distinct worktree paths.

**Acceptance Scenarios**:

1. **Given** two packages with no `depends_on` edge between them (whether same or different
   `feature_id`), **When** packages are grouped into waves, **Then** both are placed in the same
   wave and are eligible for concurrent worktree execution.
2. **Given** a wave with more than one package, **When** execution starts for that wave, **Then** a
   separate `git worktree` is created per package under a dedicated path keyed by package id, and
   each package's owner agent works only inside its own worktree.
3. **Given** package B's `depends_on` includes package A's id, **When** waves are computed, **Then**
   B is placed in a strictly later wave than A, never the same or an earlier one.

---

### User Story 2 - Gate integration on recorded peer review and Tech Lead approval (Priority: P1)

Today `conflict_policy.rules` documents, in prose only, that a package isn't complete until a
different dev agent reviews it and that the tech lead approves integration — but nothing stops a
package's worktree from being aggregated back before either happens. Spec Master now records an
explicit review verdict (from the package's assigned `reviewer_agent`) and an explicit integration
verdict (from the tech lead) per package, and refuses to include a package's worktree in a wave's
aggregation result until both verdicts are `APPROVED`.

**Why this priority**: Without a coded gate, "peer review and Tech Lead integration authority are
respected" (this feature's own acceptance criterion) is unverifiable — it would silently regress to
the same undocumented-convention state that exists today. This directly implements constitution
Principle V (Non-Destructive Recovery: nothing merges without an explicit accountable decision).

**Independent Test**: Plan a package's worktree, attempt to aggregate its wave before recording a
review verdict, and assert the aggregation result marks that package `review_pending` rather than
folding it in as complete; record `APPROVED` review and integration verdicts and assert a second
aggregation now includes it.

**Acceptance Scenarios**:

1. **Given** a package's worktree has finished its owner agent's work but has no recorded review
   verdict, **When** the wave is aggregated, **Then** the result marks that package
   `review_pending` and does not report it as integration-ready.
2. **Given** a package has a recorded `APPROVED` review verdict from its `reviewer_agent` but no
   recorded Tech Lead integration verdict, **When** the wave is aggregated, **Then** the result
   marks that package `integration_pending`.
3. **Given** a package has both an `APPROVED` review verdict and an `APPROVED` Tech Lead integration
   verdict, **When** the wave is aggregated, **Then** the result marks that package
   `integration_ready` and includes its final status and changed files exactly as
   `parallel-worktree-execution`'s aggregation already does for whole features.

---

### User Story 3 - Reuse, never duplicate, the worktree/conflict/aggregation mechanism (Priority: P1)

Package-level wave computation, worktree creation, conflict detection, and result aggregation MUST
be the same `spec-master/lib/worktree.py` functions already built and tested for whole-feature
parallel execution — called with package ids in place of feature ids — not a second parallel
implementation.

**Why this priority**: Constitution Principle VI (Backwards-Compatible Evolution) and the DRY
intent behind building `worktree.py` as generic, id-keyed primitives in the first place; duplicating
wave/worktree/conflict logic here would double the surface area to keep correct for no behavioral
gain.

**Independent Test**: Inspect that the new Team Mode module imports and calls
`worktree.compute_waves`, `worktree.plan_worktree`, `worktree.conflicts`, and `worktree.aggregate`
directly rather than reimplementing equivalent logic.

**Acceptance Scenarios**:

1. **Given** a `workstreams.json` packages list, **When** wave grouping is requested, **Then** the
   implementation calls `worktree.compute_waves` with each package mapped to `{"id": package_id,
   "dependencies": package["depends_on"]}`, not a second wave algorithm.
2. **Given** a multi-package wave, **When** worktrees are planned, **Then** the implementation calls
   `worktree.plan_worktree(feature_id=package_id, ...)` directly, reusing its existing idempotency
   and single/non-git fallback guards without modification to `worktree.py` itself.

### Edge Cases

- What happens when two packages in the same wave are owned by the same agent (e.g. two
  `backend-dev` packages with no dependency edge)? They still get separate worktrees and can run
  concurrently — Team Mode's `lanes` grouping (by owner agent) is a *reporting/assignment* view, not
  a concurrency constraint; only `depends_on` edges gate wave placement, consistent with how
  `feature_model.py`'s dependency graph — not any grouping label — gates `parallel-worktree-
  execution`'s waves.
- What happens if a package's review verdict is `REJECTED` rather than pending? The package stays
  `review_pending` in the aggregation result (never silently treated as approved) and the Aggregation
  Result records the rejection reason so a human/orchestrator can route it back to the owner agent;
  the system MUST NOT auto-retry or auto-fix the package.
- What happens to a package's worktree once it reaches `integration_ready`? Identical to
  `parallel-worktree-execution`'s FR-008: it is not deleted by this feature — deletion/cleanup
  remains a separate, explicit operation outside this feature's scope.
- What happens for a `workstreams.json` with only one package total, or in a non-git repository?
  Falls back to the existing sequential Team Mode path with no worktree created, inheriting
  `plan_worktree`'s existing `wave_size`/`is_git_repo` guards unchanged (no new code needed for this
  case — see User Story 3).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST group `workstreams.json` packages into concurrency waves using
  `worktree.compute_waves`, mapping each package's `depends_on` (package ids) into the `dependencies`
  key that function expects — MUST NOT implement a second wave-grouping algorithm.
- **FR-002**: For any wave containing more than one package, the system MUST create one isolated
  `git worktree` per package via `worktree.plan_worktree`, called with the package id in place of a
  feature id, before that package's owner agent begins work.
- **FR-003**: Each package's work, when running inside a worktree, MUST only read/write files inside
  that worktree's own directory, using `worktree.resolve_project_root` unchanged.
- **FR-004**: A package's worktree MUST NOT be considered `integration_ready` in an Aggregation
  Result until an `APPROVED` review verdict has been recorded from that package's `reviewer_agent`.
- **FR-005**: A package's worktree MUST NOT be considered `integration_ready` in an Aggregation
  Result until an `APPROVED` Tech Lead integration verdict has additionally been recorded, even if
  its review verdict is already `APPROVED`.
- **FR-006**: Review and integration verdicts MUST be recorded through an explicit, structural CLI
  verb (not inferred or defaulted to approved) — a package with no recorded verdict MUST report as
  pending, never as silently approved.
- **FR-007**: When two or more package worktrees in the same wave modify the same file in
  incompatible ways, the system MUST reuse `worktree.conflicts` to report the conflict (package ids
  + file paths) and MUST NOT automatically resolve or discard either side.
- **FR-008**: After a wave finishes, the system MUST reuse `worktree.aggregate` to fold each
  package's final status and changed-file list into a single report structure, extended with that
  package's review/integration verdict state (`review_pending`, `integration_pending`,
  `integration_ready`).
- **FR-009**: All new Team-Mode-parallel logic MUST live in `spec-master/lib/` as pure, testable
  Python exposed via `spec-master/lib/cli.py`, per constitution Principle I, and MUST import and
  call `spec-master/lib/worktree.py`'s existing functions rather than duplicating their logic
  (Principle VI).
- **FR-010**: A wave with exactly one package, or a non-git repository, MUST fall back to today's
  sequential Team Mode behavior with no worktree created — inherited unchanged from
  `worktree.plan_worktree`'s existing `wave_size`/`is_git_repo` guards (no new guard logic required).

### Key Entities

- **Work Package Wave**: An ordered group of package ids (from `workstreams.json`) that can run
  concurrently because none of them depends (via `depends_on`) on another still-pending package in
  the same or a later wave. Structurally identical to `parallel-worktree-execution`'s Execution
  Wave, computed by the same function, at package granularity instead of feature granularity.
- **Review Verdict**: A recorded `{package_id, reviewer_agent, status: APPROVED|REJECTED, reason}`
  decision, required before a package can be considered integration-ready.
- **Integration Verdict**: A recorded `{package_id, status: APPROVED|REJECTED, reason}` decision from
  the Tech Lead, required in addition to the Review Verdict before a package can be considered
  integration-ready.
- **Workstream Aggregation Result**: `parallel-worktree-execution`'s existing Aggregation Result,
  extended with each package's review/integration verdict state.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For a `workstreams.json` with N packages that have no dependency edges between them
  (including packages sharing a `feature_id`), all N are grouped into the same wave 100% of the time
  in the deterministic test suite.
- **SC-002**: A package with no recorded review verdict, or a `REJECTED` review/integration verdict,
  is never reported as `integration_ready` in the deterministic test suite — 100% of the time it
  reports `review_pending`, `integration_pending`, or its rejection is recorded, never silently
  treated as approved.
- **SC-003**: The new module calls `worktree.compute_waves`, `worktree.plan_worktree`,
  `worktree.conflicts`, and `worktree.aggregate` directly (verified by code inspection / mocking
  those exact call sites in tests) — zero duplicated wave/worktree/conflict/aggregate logic.
- **SC-004**: A single-package wave or non-git-repo run produces byte-for-byte the same behavior as
  today's sequential Team Mode path (regression coverage against the existing `test_team_model.py`
  suite, which this feature MUST NOT modify).

## Assumptions

- "Peer review" and "Tech Lead integration authority" verdicts are recorded by the orchestrating
  agent (standing in for the `reviewer_agent`/`tech-lead` roles per Team Mode's simulated-multi-agent
  model, PROTOCOL.md), not by a second live agent process — consistent with constitution Principle I
  (the deterministic core records structural state; judging the actual code diff is semantic work the
  agent performs, exactly like every other role-playbook interaction in this codebase today).
- Worktree isolation is keyed by **package id**, not feature id, because Team Mode's whole value
  proposition is multiple agents working the *same* feature concurrently — reusing
  `worktree.plan_worktree`'s `feature_id` parameter with a package id is a call-site choice, not a
  signature change to `worktree.py`.
- `workstreams.json` remains the source of truth for package definitions (`build_workstreams`
  unchanged); this feature only adds execution/gating on top of it, per Principle VI.
- Verdict storage location (where `APPROVED`/`REJECTED`/pending state persists between CLI calls) is
  a Technical Context unknown resolved during `/speckit-plan` (research.md), not fixed here.
