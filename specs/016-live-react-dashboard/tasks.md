# Tasks: Live React Dashboard

**Prerequisites**: plan.md, spec.md, contracts/api.md. **Tests**: REQUIRED (Principle III): failing unittest first.

## Phase 1: Setup
- [x] T001 Baseline: record unittest count and `doctor run --errors-only` status in validation-report.md

## Phase 2: Model additions (US2, FR-008)
- [x] T002 [US2] Failing tests in spec-master/tests/test_dashboard.py: feature `cycle`/`delivery`/`effective_percent`, top-level `cycles`, `gates`, `lanes`, `hook_decisions`; existing keys unchanged
- [x] T003 [US2] Implement the additive keys in spec-master/lib/dashboard.py

## Phase 3: Server core (US1/US3, FR-002..FR-005, FR-009)
- [x] T004 [US1] Failing tests in spec-master/tests/test_dashboard_server.py: tailer (new lines only, partial line held, truncation, corrupt skipped), `format_sse`, changes/state watchers, `derive_events`, `tokens_summary` (provider, missing ledger -> None, raising -> None)
- [x] T005 [US1] Implement watchers, tailer, derive and tokens helpers in spec-master/lib/dashboard_server.py
- [x] T006 [US3] Failing HTTP tests (ephemeral 127.0.0.1 port): bind address, `/api/model` shape + `tokens` null/fixture, `/healthz`, 405, 403 foreign Host, 404, path traversal, SSE event per source file, heartbeat, `model` event, fallback HTML when dist missing, static serving + content types, 503 beyond the SSE client cap
- [x] T007 [US1] Implement `make_server`/handler/`serve` in spec-master/lib/dashboard_server.py

## Phase 4: CLI (FR-001, FR-011)
- [x] T008 [US1] Failing test in spec-master/tests/test_dashboard_cli.py: `dashboard serve -h` parses `--port/--path/--open`; serve with port 0 prints JSON line (server run in thread via entry point with a stop event)
- [x] T009 [US1] Add the `serve` subparser block and branch in spec-master/lib/cli.py

## Phase 5: React app + bundle (US4, FR-006/FR-007)
- [x] T010 [P] [US4] Failing tests in spec-master/tests/test_dashboard_bundle.py: manifest hashes match `dashboard/web/dist`, index.html present and references only relative assets, no Node invoked, `write_manifest`/`verify_manifest` unit tests on a temp dir (tamper detection), source tree has no `node_modules`
- [x] T011 [P] [US1] Create dashboard/web (package.json, vite.config.js, index.html, src/api.js, App.jsx, views, styles.css, README.md with the Principle IX exception)
- [x] T012 [US4] `npm install && npm run build` (or report missing npm); generate dist/MANIFEST.json; commit dist; add `dashboard/web/node_modules` to .gitignore
- [x] T013 [US4] Implement `manifest`/`write_manifest`/`verify_manifest` and the `manifest` script entry in dashboard_server.py (done with T005 if trivial)

## Phase 6: Polish
- [x] T014 [FR-010] Add test in spec-master/tests/test_dashboard_bundle.py that `packaging.check` reports no drift and that no generated plugin file references `dashboard/web`; README section for `dashboard serve`; confirm packaging.py check and `doctor run --errors-only` stay green
- [x] T015 Live smoke: start the server, curl `/api/model`, append lines to the JSONL files, observe SSE
- [x] T016 Validate: full unittest, pytest (.venv), gates detect, evals run, graph validate, doctor; write validation-report.md; traceability rows

## Dependencies
T002->T003; T004->T005->T006->T007->T008->T009; T010,T011 parallel; T012 after T011 and T013; T014..T016 last.
