# Tasks: Token ledger and statusline (T3)

**Tests**: REQUIRED (TDD): each task writes the failing unittest first.

## Phase 1: Reader
- [x] T001 [US1] Tests + refactor: shared `_absorb_response` and `telemetry.read_responses` with offset in spec-master/lib/telemetry.py, spec-master/tests/test_telemetry.py

## Phase 2: Events
- [x] T002 [US2] Tests + implement spec-master/lib/events.py (append/read/on_agent/on_phase/active_window), spec-master/tests/test_events.py
- [x] T003 [US2] Wire hookd `subagent-start`/`subagent-stop` and `state transition` phase events; tests in test_kernel_hookd.py, test_state_cli.py
- [x] T004 [US2] Add SubagentStart/SubagentStop to spec-master/lib/kernel/install.py and spec-master/lib/packaging.py (Claude only), regenerate plugin files; tests in test_kernel_install.py, test_packaging.py

## Phase 3: Ledger
- [x] T005 [US3] Tests + implement spec-master/lib/ledger.py ingest, attribution, cost estimate, summary, spec-master/tests/test_ledger.py
- [x] T006 [US3] `tokens ingest|summary` in spec-master/lib/cli.py; spec-master/tests/test_tokens_cli.py

## Phase 4: Statusline and docs
- [x] T007 [US4] spec-master/lib/statusline.py + spec-master/tests/test_statusline.py
- [x] T008 Docs: README/PROTOCOL-free install notes in docs/token-ledger.md; keep test_protocol_conformance green

## Phase 5: Validate
- [x] T009 Quality gates, doctor, evals, graph validate, validation-report.md, traceability rows
