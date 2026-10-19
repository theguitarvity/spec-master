# Feature Specification: Live React Dashboard (D1)

**Feature Branch**: `016-live-react-dashboard` (trunk-based: no dedicated branch, isolated logically under this directory)
**Created**: 2026-10-19 | **Status**: Draft
**Input**: "Dashboard React em tempo real para o operador acompanhar a execução (opção D1)" (`.spec-master/context/app-features.md`, Ciclo 2, Feature 16; user decision D1: stdlib SSE server + React/Vite app with a COMMITTED built bundle).

## Grounding (DISCOVERED_FROM_CODEBASE)

- `spec-master/lib/dashboard.py` already has `build_model(root)` (read-only, never raises, schema `spec-master.dashboard/v1`), a static HTML renderer and `dashboard render|model` in `cli.py`. This feature REUSES it; no second model.
- Upstream added `hooks/decisions.jsonl` (kernel/hookd.py), `hooks/firings.jsonl`, `.spec-master/changes/` (kernel/changes.py: `<id>.json`, `active.json`, `log.jsonl`) and `quality_gates` in `state.json`; all are plain files the server can tail.
- `docs/contracts/token-ledger-v1.md` §1–§4 fixes the events/tokens JSONL formats, the `tokens summary` aggregate and the live server contract (§4). This feature is the CONSUMER; the producer (`ledger`) is built in parallel (feature 14).
- `state.json` mixes cycles: cycle-1 features are `COMPLETED` with every phase `PENDING` (delivered outside the flow, `delivery.mode = agentic-outside-spec-master`), so the global "completeness" (`done phases / all phases`) is misleading.
- Constitution 2.0.0 Principle II forbids dependencies in the core; Principle IX allows one isolated, documented exception. Node/React/Vite is that exception: only needed to REBUILD the UI, never to run it.

## Re-scope (INFERRED, reason recorded)

`rescope.md` "Remaining delta" replaces the original acceptance criteria where they conflict: (a) the server is `lib/dashboard_server.py` following contract §4; (b) CI has no Node, so the bundle is verified by a hash manifest and never rebuilt in tests; (c) the packaging generator must not break `doctor`; (d) views are refined to tokens (totals, burn rate, cache hit, cost, by feature/phase/agent/model), feature progress per cycle, phase timeline, gates, active agents, lanes/changes, hook decisions and a dependency map. The "orçamento do tier" budget has no source of truth in the contract: the UI says "no budget configured" (INFERRED).

## Clarifications

### Session 2026-10-19 (autonomous, nothing blocking)

- Q: Default port? -> A: 8765; `--port 0` picks an ephemeral port (INFERRED); the URL is printed as JSON.
- Q: How is the ledger summary obtained while `ledger` does not exist yet? -> A: guarded import of `ledger`; calls `ledger.summarize(root)` or `ledger.summary(root)` when present, else `tokens: null`; a provider can be injected (tests use fixtures). The transcript parser is NOT implemented here (INFERRED, contract ownership).
- Q: Tier token budget? -> A: no budget field exists; show "not configured" rather than invent one (INFERRED).
- Q: Authentication? -> A: none; read-only, loopback-only, Host-header validation against DNS rebinding (INFERRED security default).
- Q: What does `event: model` carry? -> A: a small notice `{generated_at, reason}`; the client refetches `/api/model` (INFERRED).

## User Scenarios & Testing

### US1 - Operator opens a live dashboard (P1)
`python3 spec-master/lib/cli.py dashboard serve --open` starts a localhost server and opens the React UI, with no Node installed.
1. Given no Node, When the operator runs `dashboard serve`, Then the committed bundle is served at `/` and `/api/model` answers JSON.
2. Given the server runs, When a line is appended to `events.jsonl`, `metrics/tokens.jsonl`, `hooks/firings.jsonl`, `hooks/decisions.jsonl`, or a file appears in `changes/`, Then `/api/events` emits the matching `event:` within ~1 s.
3. Given the bundle directory is missing, When `/` is requested, Then the static HTML dashboard (current model) is served (fallback).

### US2 - Honest progress and tokens (P1)
1. Given cycle-1 features delivered outside the flow, When the model is built, Then each feature exposes `cycle`, `effective_percent` (100 for COMPLETED) and `delivery`, `cycles[]` gives per-cycle done/total/percent, and the original `completeness` stays unchanged.
2. Given a ledger summary, When `/api/model` is requested, Then `tokens` equals the contract §3 aggregate; without a ledger `tokens` is `null`.

### US3 - Safe by default (P1)
Server binds only `127.0.0.1`, accepts only GET/HEAD, rejects foreign `Host` headers, never serves outside the bundle dir, survives corrupt JSONL.

### US4 - Bundle integrity without Node (P2)
A committed `MANIFEST.json` (sha256 per file in `dashboard/web/dist`); a test recomputes and compares; rebuild only via `npm run build`, which regenerates the manifest.

## Requirements

- **FR-001**: `cli.py dashboard serve [--port N] [--path P] [--open]` starts `dashboard_server` bound to `127.0.0.1` only; prints one JSON line `{url, port, root, bundle}`; Ctrl-C stops cleanly.
- **FR-002**: `GET /api/model` returns `dashboard.build_model(root)` plus `tokens` (contract §3 aggregate or `null`), `agents` (from `agent.*` events) and `timeline` (phase intervals from `phase.*` events).
- **FR-003**: `GET /api/events` is SSE; `event: <type>` + single-line `data: <JSON>` for new lines of `events.jsonl` (`type` = record type), `metrics/tokens.jsonl` (`tokens`), `hooks/firings.jsonl` (`hook.fired`), `hooks/decisions.jsonl` (`hook.decision`), changes dir (`change`), `event: model` on `state.json` change; `: ping` every 15 s; only lines appended after connection are streamed; partial lines are held; truncation resets the offset.
- **FR-004**: Only GET/HEAD (else 405); foreign `Host` -> 403; no CORS headers; static paths resolved inside the dist dir; bounded concurrent SSE clients.
- **FR-005**: `/` serves `dashboard/web/dist/index.html` and assets; missing bundle -> `dashboard.render_html(model)` fallback; `dashboard render|model` untouched.
- **FR-006**: React+Vite app in `dashboard/web/` (isolated, never imported by the core), built bundle committed in `dashboard/web/dist/` with `MANIFEST.json`; Principle IX exception documented in `dashboard/web/README.md`.
- **FR-007**: UI views: Overview (run state, per-cycle progress), Features (kanban by current phase + dependency map), Timeline (phases), Tokens (totals, burn rate, cache hit, cost, by feature/phase/agent/model, tier budget "not configured"), Agents & lanes (active agents, workstream packages, changes), Gates, Hooks (firings + decisions), live feed with connection status.
- **FR-008**: `dashboard.py` gains ADDITIVE keys only: per-feature `cycle`, `effective_percent`, `delivery`; top-level `cycles`, `gates`, `lanes`, `hook_decisions`. Existing keys and static HTML unchanged.
- **FR-009**: Guarded `ledger` import; missing/failing ledger -> `tokens: null`; corrupt JSONL lines are skipped, never crash the server.
- **FR-010**: Packaging generator and `doctor run --errors-only` stay green (new code outside `kernel/`; bundle not generated by `packaging.py`).
- **FR-011**: README documents `dashboard serve`; `test_protocol_conformance` stays green.

## Success Criteria

- **SC-001**: server tests (ephemeral 127.0.0.1 port, offline) cover FR-001..FR-005, FR-009.
- **SC-002**: `python3 -m unittest discover -s spec-master/tests` passes with no Node present.
- **SC-003**: bundle manifest test passes; `doctor run --errors-only` exits 0.
- **SC-004**: existing `test_dashboard*` tests pass unchanged.

## Non-goals

Transcript parsing / ledger production (feature 14); OTLP receiver; remote or multi-user access; auth; write actions from the UI; a Node runtime requirement; dev server in CI.
