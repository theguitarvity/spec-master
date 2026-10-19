# Validation Report: Live React Dashboard

**Date**: 2026-10-19 | **Feature**: `live-react-dashboard` (cycle 2, tier S) | **Spec**: [spec.md](spec.md)

Executed per PROTOCOL.md in Auto Mode in an isolated worktree; bookkeeping (state, traceability, metrics) targets the main checkout.

## Baseline vs After

| Measure | Baseline | After |
|---|---|---|
| `python3 -m unittest discover -s spec-master/tests` | Ran 956, OK (skipped=1) | **Ran 1020, OK (skipped=1)** (+64) |
| `.venv` pytest | no `.venv` in this worktree; not run | n/a |
| `gates detect --path .` | one blocking test gate | same gate; command passed `policy preflight` (allowed, low) and was run (above) |
| `evals run` | n/a | 5/5 passed |
| `graph validate --path .` | n/a | valid, 0 issues |
| `doctor run --errors-only` | exit 0 | **exit 0** (warnings pre-existing: step_path_budget, evidence of other features) |
| `kernel/` LOC | 2444 | 2444 (new code lives outside `kernel/`; budget 2500) |

New tests: 9 (`LiveModelKeysTests`), 42 (`test_dashboard_server.py`), 4 (`DashboardServeCliTests`), 9 (`test_dashboard_bundle.py`). Existing `test_dashboard*` tests pass unchanged. `test_protocol_conformance` and `test_packaging` green.

## Acceptance Criteria to Evidence

1. FR-001 serve command, 127.0.0.1 bind, JSON line: `test_dashboard_server` (bind address, ready line, port in use returns 1) and `DashboardServeCliTests`.
2. FR-002 `/api/model` plus `tokens`, `agents`, `timeline`: server tests for model shape, tokens null/fixture/raising provider, `derive_events`.
3. FR-003 SSE: one test per source file (events, tokens, hook firings, hook decisions, changes), `model` event on state change, heartbeat, tailer (new lines only, partial line held, truncation, corrupt skipped).
4. FR-004 hardening: 405 on non-GET/HEAD, 403 foreign Host, no CORS, 404, path traversal, 503 above the SSE cap.
5. FR-005 static and fallback: static serving with content types; fallback HTML when dist missing.
6. FR-006 isolated bundle: `test_dashboard_bundle.py` (manifest hashes, tamper detection, relative assets, no sourcemaps, no Node invoked); `dashboard/web/README.md` documents the Principle IX exception.
7. FR-007 UI views: build succeeds; manual smoke in the browser pane: all 8 tabs render, status "live", no console errors (see Analyze finding A3).
8. FR-008 additive keys: `LiveModelKeysTests`; existing dashboard tests unchanged.
9. FR-009 guarded ledger: `tokens_summary` tests (missing ledger, raising provider return None); live smoke returned `tokens: null`.
10. FR-010 packaging and doctor: `test_packaging_has_no_drift`, `test_generated_plugin_files_do_not_reference_the_web_source`, doctor exit 0.
11. FR-011 docs: README row for `dashboard serve`; PROTOCOL.md untouched.

## Live smoke (T015)

Server started on 127.0.0.1:8791: `/` 200 text/html, bundled asset 200, `/api/model` schema `spec-master.dashboard/v1` with 17 features and `tokens: null`, `/api/events` streamed `: connected` then `hook.decision` records as they were appended. In the browser, every tab rendered and the feed showed `model` and `hook.decision` events live.

## Analyze findings (cycle 1 of max 3, repaired)

- A1 (MEDIUM): SSE client cap had no test. Repaired in T006 (503 test).
- A2 (MEDIUM): FR-010 was only a manual check. Repaired in T014 (automated packaging drift and no-reference tests).
- A3 (LOW): UI views are verified by build plus manual smoke, not automated tests (no JS test runner by design). Accepted.

## INFERRED decisions

Default port 8765; guarded `ledger` entry point (`summarize`/`summary`) with `tokens: null` fallback; tier budget shown as "not configured"; no auth (loopback-only plus Host guard); rescope.md "Remaining delta" overrides the original criteria; `model` notice payload is `{generated_at, reason}`.

## Follow-ups

- Confirm feature 14's ledger API name once it lands, so `tokens` stops being null.
- Metrics rounds are recorded as manual with 0 tokens (adapter does not expose token accounting).
- Rebuild requires Node: `cd dashboard/web && npm install && npm run build`.

**Verdict**: PASSED.
