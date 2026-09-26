# Validation Report: Team Mode Parallel Workstreams

**Date**: 2026-09-26 | **Feature**: `team-mode-parallel-workstreams` | **Spec**: [spec.md](spec.md)

Executed directly by the agent per PROTOCOL.md Section 7 (no `templates/prompts/validate.md`
exists for this phase; the agent validates against acceptance criteria in Auto Mode, same as
`parallel-worktree-execution`'s validate phase).

## Acceptance Criteria → Evidence

1. **"Each workstream in `.spec-master/workstreams.json` executes in its own worktree via the
   mechanism built for `parallel-worktree-execution`"** — PASS. No new worktree-creation code
   exists (research.md #2); `WaveGroupingReuseTests::test_worktree_compute_waves_accepts_package_shaped_input`
   (`spec-master/tests/test_team_workstreams.py`) proves package-shaped input flows through
   `worktree.compute_waves` unchanged, and a manual CLI walkthrough (below) confirms
   `worktree plan --feature-id <package-id> ...` — already exhaustively covered, unmodified, by
   `test_worktree.py::PlanWorktreeTests` — accepts a package id in place of a feature id with no
   code change required.
2. **"Peer review and Tech Lead integration authority are respected before a workstream is
   merged"** — PASS. `RecordReviewVerdictTests` (3 tests) and `RecordIntegrationVerdictTests`
   (2 tests) prove `record_review_verdict` rejects any `reviewer_agent` other than the package's
   own assigned one and requires a `reason` on rejection; `IntegrationStateTests` proves a package
   is never `integration_ready` with fewer than two `APPROVED` verdicts. Confirmed live via CLI
   (see below): `workstreams review --reviewer backend-dev` against a package assigned to
   `fullstack-dev` exits 1 with `{"error": "reviewer_agent 'backend-dev' does not match package
   'pkg-a''s assigned reviewer_agent 'fullstack-dev'"}`.
3. **"Workstream results are aggregated into the same reporting path as sequential Team Mode
   execution"** — PASS. `AggregateWithVerdictsTests::test_aggregate_with_verdicts_calls_worktree_aggregate`
   mock-verifies `aggregate_with_verdicts` calls `worktree.aggregate(wave_index, handles)` exactly
   once rather than recomputing a report itself; the output is `worktree.aggregate`'s existing
   `{wave_index, features, conflicts}` shape with one added field (`integration_state`) per
   feature entry — same reporting path, additively extended (FR-008).

## Success Criteria → Evidence

- **SC-001** (N independent packages, including same-`feature_id` packages, land in the same wave
  100% of the time) — PASS. `WaveGroupingReuseTests` (deterministic, no mocking needed —
  `compute_waves` is pure).
- **SC-002** (no verdict, or a `REJECTED` verdict, is never reported `integration_ready`) — PASS.
  `IntegrationStateTests::test_integration_state_transitions` is table-driven across all 5
  reachable states (no verdicts, review-only, both approved, review rejected, integration
  rejected); the live CLI walkthrough independently confirms `pkg-b` (no verdicts recorded) stays
  `review_pending` in a real aggregation call.
- **SC-003** (new module calls `worktree.compute_waves`/`plan_worktree`/`conflicts`/`aggregate`
  directly; zero duplicated logic) — PASS, per the analyze-phase repair (1 cycle, see below) that
  added a dedicated User Story 3 test phase:
  `AggregateWithVerdictsTests::test_aggregate_with_verdicts_calls_worktree_aggregate` (mocks the
  exact call site, asserts it is invoked) and
  `ReuseNotDuplicateTests::test_team_workstreams_defines_no_duplicate_wave_or_worktree_logic`
  (asserts `team_workstreams.py` defines no `compute_waves`/`plan_worktree`/`conflicts` function
  of its own).
- **SC-004** (single-package/non-git-repo byte-for-byte same as today; `test_team_model.py`
  unmodified) — PASS. `git diff --stat` against `spec-master/lib/team_model.py`,
  `spec-master/tests/test_team_model.py`, `spec-master/lib/worktree.py`, and
  `spec-master/tests/test_worktree.py` shows zero changes to any of the four files. Full suite:
  `test_team_model.py` (6/6 passing), `test_worktree.py` (12/12 passing),
  `test_team_workstreams.py` (10/10 passing, new). The full-suite run surfaces the same 21
  pre-existing `ModuleNotFoundError: No module named 'pytest'` errors in `test_graph_*`/
  `test_knowledge_*` files already documented and confirmed pre-existing/unrelated in
  `specs/003-parallel-worktree-execution/validation-report.md` — untouched by this feature.

## Analyze-Phase Repair (1 cycle, within the 3-cycle budget)

Cross-artifact analysis caught two findings before implementation began, both repaired directly
per PROTOCOL.md's override:

1. `tasks.md`'s header promised "Grouped by user story (US1/US2/US3 from spec.md)" but only had
   phases for US1 and US2 — User Story 3 ("Reuse, never duplicate...") had no dedicated phase or
   test. **Repair**: added Phase 4 (US3) with `T016`/`T017`, which became
   `test_aggregate_with_verdicts_calls_worktree_aggregate` and
   `test_team_workstreams_defines_no_duplicate_wave_or_worktree_logic` — both now in the suite and
   directly cited under SC-003 above.
2. `T014`'s requirement citation `(FR-007, FR-008)` incorrectly included FR-007 (which governs
   `worktree.conflicts`, unrelated to aggregation). **Repair**: corrected to `(FR-008)` only.

`state analyze-cycle` recorded 1 cycle for this feature (max 3) — repair verified, not exhausted.

## Manual CLI Walkthrough (quickstart.md steps 4-6)

Ran against a hand-built two-package `workstreams.json` (packages `pkg-a`/`pkg-b`, same
`feature_id`, `reviewer_agent: fullstack-dev`, no `depends_on` edge):

1. `workstreams review --package pkg-a --reviewer backend-dev --status APPROVED` → exit 1,
   `{"error": "reviewer_agent 'backend-dev' does not match package 'pkg-a''s assigned
   reviewer_agent 'fullstack-dev'"}` (identity enforcement working).
2. `workstreams review --package pkg-a --reviewer fullstack-dev --status APPROVED` → package
   updated with `review_verdict: {status: APPROVED, reviewer_agent: fullstack-dev, reason: null}`.
3. `workstreams integrate --package pkg-a --status APPROVED` → package additionally carries
   `integration_verdict: {status: APPROVED, reason: null}`.
4. `workstreams aggregate --wave-index 0 --handles <handles.json> --packages workstreams.json` →
   `pkg-a` reports `integration_state: "integration_ready"`; `pkg-b` (no verdicts recorded at all)
   reports `integration_state: "review_pending"` in the same aggregation call — confirming SC-002
   end-to-end, not just at the unit-test level.

`gates detect --path .` returned `[]` — no configured gates beyond the test suite, same as
`parallel-worktree-execution`'s validate phase.

## Verdict

**PASSED** — all 3 acceptance criteria and all 4 Success Criteria are met with test and/or live
CLI evidence; no scope-boundary caveats (unlike feature 1's SC-001) — this feature's Scale/Scope
in plan.md fully covers execution-time verdict gating and aggregation, with no external
integration left outside the plan.
