# Validation Report: Protocol and CLI Performance

**Date**: 2026-10-19 | **Feature**: `protocol-and-cli-performance` | **Spec**: [spec.md](spec.md)

Cycle-2 feature (roadmap P1-P6). Executed by the agent in a worktree; bookkeeping (state, traceability,
metrics) went to the main checkout. Decisions that replace the original acceptance criteria are tagged
INFERRED in spec.md.

## Acceptance Criteria -> Evidence

1. **FR-001 `state advance` (P1)** - PASS. One call does transition + optional round + optional trace rows and
   answers with a `next` block; the transition code is shared with `state transition` (`_transition`) and the
   next-phase function lives in `state.py`. Tests: `test_advance.py` (13), including invalid-round-fails-before-any-write.
2. **FR-002 router and sections (P2)** - PASS. `spec-master/cards/full-cycle.md` is 4,297 B (<= 5,120);
   `protocol sections|show --section` prints one PROTOCOL.md section; the full-cycle entrypoint now says
   "read the router + the card for the current step". Tests: `test_protocol_sections.py` (14), `test_protocol_conformance`
   green, `doctor` cards check (router budget extended to `full-cycle.md`).
3. **FR-003 hints (P3)** - PASS. Every `CEREMONY_PROFILES` tier carries per-phase `hints`; emitted in the `advance`
   answer and appended to the first-attempt controller prompt. Tests: `test_risk_hints.py`.
4. **FR-004 snapshot (P4)** - PASS. `phase_contracts.walk_project` prunes during `os.walk`; new ignored names
   (dist, build, target, .tox, .mypy_cache, .pytest_cache, .next, coverage, vendor, vendored); (size, mtime_ns) hash cache
   at `.spec-master/cache/snapshot.json` (ignored by the snapshot, safe on corrupt/unwritable). Tests: `test_phase_snapshot.py` (11).
5. **FR-005 dashboard (P5)** - PASS. `render_dashboard` hook action debounced (default 2 s,
   `SPEC_MASTER_DASHBOARD_DEBOUNCE`, 0 disables, stamp under `.spec-master/cache/`); `dashboard._graph` cached by
   path/size/mtime_ns. Tests: `test_dashboard_debounce.py` (10).
6. **FR-006 MCP and CLI (P6)** - PASS. MCP `run_cli` dispatches in-process (cwd/stdout/stderr/fd 1 restored under a lock,
   SystemExit handled, subprocess fallback; groups controller/gates/evals/doctor/dashboard and any explicit timeout keep
   the subprocess). `cli.py` imports 25 engine modules lazily via a module proxy (calibration, metrics, risk_profile, state stay eager).
   Tests: `test_mcp_inprocess.py` (12), `test_cli_lazy.py` (4).
7. **FR-007 numbers** - PASS, see below.
8. **FR-008 constraints** - PASS. stdlib only; new code outside `kernel/` (only a one-line `doctor.cards` budget tweak inside it);
   `doctor run --errors-only` exits 0.

## Success Criteria -> Evidence

- **SC-001** - PASS. Router 4,297 B + largest section (Step 6, 6,939 B) = 11,236 B = 29% of the 38,345 B protocol
  (`test_router_plus_largest_step_is_far_below_the_whole_protocol`, threshold 40%).
- **SC-002** - PASS. `state show` median 106.2 ms -> 77.0 ms.
- **SC-003** - PASS. `test_walk_does_not_descend_into_pruned_dirs`.
- **SC-004** - PASS. 1,030 tests OK (956 before; +74).

## Before / After

| Metric | Before | After |
|---|---|---|
| `state show` median of 5 | 106.2 ms | 77.0 ms |
| `--help` median of 5 | 102.2 ms | 80.1 ms |
| Snapshot walk, this repo (462 -> 475 files), warm cache | 14.6 ms | 6.9 ms |
| Protocol bytes read per full-cycle step | 1,970 (entrypoint) + 37,952 (PROTOCOL.md) = 39,922 | 2,364 + 4,297 (router) + one section (0.3-6.9 KB) = 7.0-13.6 KB |
| Step-path LOC reported by doctor | 4,916 | 4,753 |
| MCP call | one interpreter start per call | in-process (no process spawn) |
| Tests | 956 | 1,030 |

The snapshot walk on this small repo is dominated by hashing; on repos with `node_modules`, `.venv`, `dist` or `target` the pruned
walk avoids visiting them at all (not measured here: this repo has none).

## Gates

- `python3 -m unittest discover -s spec-master/tests`: 1,030 tests, OK (1 skipped, as before).
- `gates detect --path .` returned the unittest command; `policy preflight` allowed it.
- `evals run`: 5/5. `graph validate --path .`: valid, 0 issues.
- `doctor run --errors-only --path .`: exit 0 (warnings: step_path_budget, evidence on older features, unchanged).
- `test_protocol_conformance`: green (the documented `protocol show --section` invocation exists in the parser).
- No `.venv` in the worktree, so no pytest run.

## Notes and follow-ups

- Debounce is leading-edge only: the last event inside a 2 s window is not rendered until the next event
  (`dashboard render` always renders). A trailing render would need a background timer.
- In-process MCP calls have no hard timeout; setting `--timeout`/`SPEC_MASTER_MCP_TIMEOUT` or `SPEC_MASTER_MCP_INPROCESS=0` restores the subprocess path.
- `discovery.py` contains no tree walk, so it needed no rewiring; `walk_project` is exposed for future use.
- Step 6 of PROTOCOL.md is still 6.9 KB; splitting its metrics paragraph into its own subsection would lower the worst-case read further.
- The controller shares only `state.next_phase` and the hint with `advance`; it does not call `advance` itself.
