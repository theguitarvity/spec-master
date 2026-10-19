# Tasks: Multi-Agent Dispatch

**Prerequisites**: plan.md, spec.md, contracts/dispatch-manifest.md. **Tests**: REQUIRED (Principle III): failing unittest first (RED), then code (GREEN).
**Gate to start implement**: F14 (events.jsonl, ledger, hookd subagent-stop) and F17 (Standard lane API, test-first card) merged on main. Budget rule: no edits in `spec-master/lib/kernel/` except T022 (<= 20 LOC); `doctor run --errors-only` must stay 0 after every phase.

Format: `- [ ] Tnnn [P?] [USn] description | depends_on: ... | owns: files`

## Phase 1: Setup
- [x] T001 Baseline: record unittest count, `doctor run --errors-only` status and hook p50 in specs/018-multi-agent-dispatch/validation-report.md; verify F14 `agent.*` event fields and F17 lane API against docs/contracts/token-ledger-v1.md and lanes.py | depends_on: [] | owns: specs/018-multi-agent-dispatch/validation-report.md

## Phase 2: Manifest core (US1; FR-001..FR-004, FR-011)
- [x] T002 [US1] RED tests in spec-master/tests/test_dispatch.py: `resolve_cap` (arg > policy > default 4, 0 and 9 rejected); packages from tasks with owners and `depends_on`; `build_manifest` fields, waves by dependency, batches [4,3] for 7 packages, reviewer != owner for every owner, review entry carries `after`, single-package wave and non-git repo -> `worktree: null`, Patch lane refused, `--force-lane` needs a reason, output deterministic | depends_on: [T001] | owns: spec-master/tests/test_dispatch.py
- [x] T003 [US1] Failing fixtures: temp git repo helper with two worktrees (reuse test_worktree.py helpers) | depends_on: [T002] | owns: spec-master/tests/test_dispatch.py
- [x] T004 [US1] GREEN: `resolve_cap`, `build_packages`, `build_manifest` in spec-master/lib/dispatch.py reusing `worktree.compute_waves`, `team_model.build_workstreams`, `risk_profile.profile_for` hints | depends_on: [T002, T003] | owns: spec-master/lib/dispatch.py

## Phase 3: Prepare and aggregate (US1/US4; FR-005, FR-008)
- [x] T005 [US4] RED tests: `prepare` creates worktrees through `worktree.plan_worktree` (assert delegation), writes scope records and marker, is idempotent; `aggregate` returns changed files, conflicts and `integration_state`, never runs merge/rebase/push/remove (assert git call log) | depends_on: [T004] | owns: spec-master/tests/test_dispatch.py
- [x] T006 [US4] GREEN: `prepare`, `aggregate` | depends_on: [T005] | owns: spec-master/lib/dispatch.py

## Phase 4: Results and status (US2/US3; FR-004, FR-006, FR-007, FR-012)
- [x] T007 [US2] RED tests: `record_result` parses the last PhaseResult via `phase_result`, allow-lists fields, truncates at 8000 chars with `truncated`, writes atomically, refuses owner-as-reviewer, ignores invalid blocks (`failed` recorded with reason) | depends_on: [T004] | owns: spec-master/tests/test_dispatch.py
- [x] T008 [US2] GREEN: `record_result` | depends_on: [T007] | owns: spec-master/lib/dispatch.py
- [x] T009 [US3] RED tests: `status` joins fixture `events.jsonl` (`agent.started|finished`) and a ledger provider (`by_agent`); missing files -> nulls plus note; corrupt lines skipped; review eligibility only after owner result | depends_on: [T008] | owns: spec-master/tests/test_dispatch.py
- [x] T010 [US3] GREEN: `status` with guarded optional producers | depends_on: [T009] | owns: spec-master/lib/dispatch.py

## Phase 5: CLI (FR-001, FR-014)
- [x] T011 [US1] RED tests in spec-master/tests/test_dispatch_cli.py: `dispatch manifest|prepare|result|status|aggregate -h` parse; `manifest` prints one JSON object; unknown feature exits non-zero with a message; `test_protocol_conformance` still green with the new invocations documented | depends_on: [T010, T006] | owns: spec-master/tests/test_dispatch_cli.py
- [x] T012 [US1] GREEN: `dispatch` subparser and branch in spec-master/lib/cli.py (lazy import of `dispatch`) | depends_on: [T011] | owns: spec-master/lib/cli.py

## Phase 6: Governance (US2; FR-009)
- [x] T013 [US2] RED tests in spec-master/tests/test_dispatch_scope.py: no marker -> `None`; write inside `owned_paths` allow; outside deny; `sm-review` any write deny; `git merge|push|rebase|worktree remove` deny; write to state.json/workstreams.json/policy.json deny; marker with bad JSON -> allow with note (fail-open like hookd); main-root absolute paths normalised | depends_on: [T004] | owns: spec-master/tests/test_dispatch_scope.py
- [x] T014 [US2] GREEN: spec-master/lib/dispatch_scope.py (`load_marker`, `decide`) using `kernel/paths` and `kernel/policy` | depends_on: [T013] | owns: spec-master/lib/dispatch_scope.py

## Phase 7: Host subagents (US5; FR-010)
- [x] T015 [US5] Docs check: confirm each host's plugin-shipped agent format (claude, qwen, copilot, cursor, gemini, codex, kiro; antigravity/agent-plugins -> fallback) and record in specs/018-multi-agent-dispatch/contracts/host-agents.md; hosts not confirmable use the fallback | depends_on: [T001] | owns: specs/018-multi-agent-dispatch/contracts/host-agents.md
- [x] T016 [US5] RED tests in spec-master/tests/test_packaging.py: `render()` includes `sm-spec|sm-implement|sm-review` for each confirmed host, review tools are read-only, bodies reference `cards/dispatch.md` and stay < 1.5 KB, every output is deterministic, `check` fails on a tampered agent file, existing packaging tests unchanged | depends_on: [T015] | owns: spec-master/tests/test_packaging.py
- [x] T017 [US5] Write spec-master/cards/dispatch.md (<= 3 KB: role contract, owned paths, test-first order, single PhaseResult ending, never merge, main session owns bookkeeping) and add a cards-budget assertion | depends_on: [T016] | owns: spec-master/cards/dispatch.md
- [x] T018 [US5] GREEN: spec-master/lib/packaging_agents.py + merge into `packaging.render()`; bump VERSION; run `packaging.py generate` and commit the generated files | depends_on: [T017] | owns: spec-master/lib/packaging_agents.py, spec-master/lib/packaging.py, spec-master/agents/, generated host files

## Phase 8: hookd integration (FR-009) — LAST, after F14/F17 hookd edits
- [x] T019 [US2] RED test in spec-master/tests/test_kernel_hookd.py: with a marker in the project root, a Write outside `owned_paths` returns the scoped deny in block mode and is logged with `agent_key` in audit mode; without a marker the decision is identical to today and `dispatch_scope` is not imported | depends_on: [T014, F14, F17] | owns: spec-master/tests/test_kernel_hookd.py
- [x] T020 [US2] GREEN: <= 20 LOC hook point in spec-master/lib/kernel/hookd.py (lazy import); run `doctor run --errors-only` (kernel budget, hook path p50) | depends_on: [T019] | owns: spec-master/lib/kernel/hookd.py

## Phase 9: Polish
- [x] T021 Update spec-master/PROTOCOL.md Step 6 and README.md with the "Multi-agent dispatch" section; keep spec-master/docs/team-mode.md untouched; run conformance test | depends_on: [T012, T018, T020] | owns: spec-master/PROTOCOL.md, README.md
- [x] T022 Replay one Standard-lane wave (>= 3 packages) with two hosts' subagents when available; record per-agent tokens (F14), reviewer != owner and cost vs single session in validation-report.md (SC-005) | depends_on: [T021] | owns: specs/018-multi-agent-dispatch/validation-report.md

## Dependency summary
T001 -> T002 -> T003 -> T004 -> {T005->T006, T007->T008->T009->T010, T013->T014} -> T011->T012; T001 -> T015 -> T016 -> T017 -> T018; {T014, F14, F17} -> T019 -> T020; {T012, T018, T020} -> T021 -> T022.
Parallel-safe sets (disjoint files): {T013-T014 (dispatch_scope)} and {T015-T018 (packaging)} can run alongside the dispatch.py chain T005-T010, which is serial (shares dispatch.py and test_dispatch.py). T012 touches cli.py, which other cycle-2 features also edit: keep it to one subparser block.

## Task-to-requirement map
FR-001..004: T002-T004 | FR-005, FR-008: T005-T006 | FR-006: T007-T008 | FR-007, FR-012: T009-T010 | FR-009: T013-T014, T019-T020 | FR-010: T015-T018 | FR-011: T002/T004 | FR-013: T001, T011, every `doctor` run | FR-014: T021 | SC-005: T022
