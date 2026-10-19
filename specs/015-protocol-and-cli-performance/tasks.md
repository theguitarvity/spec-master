# Tasks: Protocol and CLI Performance (P1-P6)

**Input**: `specs/015-protocol-and-cli-performance/` (spec.md, plan.md). Tests are REQUIRED (TDD): each task writes the failing unittest first.

## Phase 1: Setup

- [x] T001 Record baseline (CLI latency, protocol bytes, snapshot time) in specs/015-protocol-and-cli-performance/validation-report.md

## Phase 2: User Story 1 - state advance (P1)

- [x] T002 [US1] Tests then `state.next_phase` in spec-master/lib/state.py (tests/test_advance.py)
- [x] T003 [US1] Tests then spec-master/lib/advance.py (`next_block`, JSON validation)
- [x] T004 [US1] Extract the transition body of cmd_state into a helper and add `state advance` in spec-master/lib/cli.py (tests/test_advance.py CLI cases)

## Phase 3: User Story 2 - router and sections (P1)

- [x] T005 [US2] Tests then spec-master/lib/protocol_sections.py (tests/test_protocol_sections.py)
- [x] T006 [US2] `protocol sections|show` in spec-master/lib/cli.py
- [x] T007 [US2] spec-master/cards/full-cycle.md (<= 5 KB), update spec-master/templates/entrypoints/full-cycle.md, document in spec-master/PROTOCOL.md; keep test_protocol_conformance green

## Phase 4: User Story 3 - hints (P2)

- [x] T008 [US3] Tests then PHASE_HINTS in spec-master/lib/risk_profile.py; hint line in controller prompt and in advance next block (tests/test_risk_hints.py)

## Phase 5: User Story 4 - snapshot (P2)

- [x] T009 [US4] Tests then pruned `walk_project`, cache and new ignored names in spec-master/lib/phase_contracts.py (tests/test_phase_snapshot.py)
- [x] T010 [US4] Expose `walk_project` for discovery (discovery.py has no tree walk to replace; nothing to rewire)

## Phase 6: User Story 5 - dashboard (P3)

- [x] T011 [US5] Tests then debounce in spec-master/lib/hooks.py and graph cache in spec-master/lib/dashboard.py (tests/test_dashboard_debounce.py)

## Phase 7: User Story 6 - MCP and CLI (P2)

- [x] T012 [US6] Tests then in-process dispatch with fallback in spec-master/mcp/spec_master_mcp.py (tests/test_mcp_inprocess.py)
- [x] T013 [US6] Lazy imports in spec-master/lib/cli.py, isolated and last (tests/test_cli_lazy.py)

## Phase 8: Polish

- [x] T014 Run all gates (unittest, doctor run --errors-only, gates detect, evals run, graph validate), measure after, write specs/015-protocol-and-cli-performance/validation-report.md
