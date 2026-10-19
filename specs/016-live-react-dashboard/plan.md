# Implementation Plan: Live React Dashboard

**Spec**: [spec.md](spec.md) | **Tier**: S | **Date**: 2026-10-19

## Technical Context

- Python 3 stdlib only in `spec-master/lib` and `spec-master/tests` (`http.server.ThreadingHTTPServer`, `threading`, `json`, `hashlib`, `webbrowser`). The always-loaded CLI path imports `dashboard_server` lazily inside `cmd_dashboard` (`serve` branch) so no server code loads for other commands.
- Node/React/Vite lives ONLY in `dashboard/web/` (Principle IX exception): `package.json` (react, react-dom, vite, @vitejs/plugin-react), `src/`, committed `dist/` + `dist/MANIFEST.json`. No Node at runtime; tests never invoke Node.
- Reuse: `dashboard.build_model` / `render_html` (model + fallback), upstream file layout (contract §1, §2, §4). New code stays OUTSIDE `kernel/` (budget 2500 LOC) and outside the hook path.
- `ledger` (feature 14) is imported inside try/except; the aggregate is optional.

## Constitution Check

I stdlib deterministic core: PASS. II stdlib-only: PASS for lib/tests; Node isolated. III test-first, offline, ephemeral port: PASS. IV no state writes (server is read-only; bookkeeping goes through the CLI): PASS. VI additive keys only, static HTML kept: PASS. VII reuse build_model, no second parser: PASS. VIII n/a. IX documented exception in `dashboard/web/README.md`: PASS. X nothing is published: PASS.

## Design

### `spec-master/lib/dashboard_server.py`
- `LiveSources(root)`: paths of the watched files; `Tailer` per jsonl (offset at EOF on creation, holds partial lines, resets on truncation, skips corrupt JSON); `ChangesWatcher` (signature of `changes/` names+mtimes -> `change` event with `{id, status}` read defensively); `StateWatcher` (mtime+size -> `model` notice).
- `poll(sources) -> [(event, json_text)]`; `format_sse(event, data)`.
- `derive_live(root)`: reads the tail (<= 512 KiB) of `events.jsonl` and returns `agents` and `timeline` (pure `derive_events(records)`).
- `tokens_summary(root, provider=None)`: provider override, else guarded `ledger.summarize|summary`, else `None`; exceptions -> `None`.
- `build_live_model(root, provider=None)` = `dashboard.build_model` + `tokens` + `agents` + `timeline`.
- `make_server(root, port=0, dist_dir=None, heartbeat=15, poll_interval=0.5, tokens_provider=None) -> ThreadingHTTPServer` bound to `("127.0.0.1", port)`; handler: GET/HEAD only, Host check (`127.0.0.1|localhost|[::1]` + optional `:port`), routes `/api/model`, `/api/events`, `/healthz`, static (safe join, `Content-Type` by extension, `Cache-Control: no-store` for `index.html`), fallback HTML; SSE client counter (max 32 -> 503).
- `serve(root, port, open_browser, ...)` blocking with graceful `KeyboardInterrupt`.
- `manifest(dist)`, `write_manifest(dist)`, `verify_manifest(dist) -> list[str]` (problems); `python3 dashboard_server.py manifest` writes it (used by `npm run build`).

### `spec-master/lib/dashboard.py` (additive)
Per feature: `cycle` (explicit or `1` when absent), `delivery` (dict|None), `effective_percent` (100.0 when `status == COMPLETED`, else `percent`). Top-level: `cycles` (per state cycle id: status, features, done/total phases, `percent` over phases of flow-run features, `effective_percent` mean of effective), `gates` (state `quality_gates` reduced), `lanes` (active change + last 10 of `changes/log.jsonl`), `hook_decisions` (last 20 of `hooks/decisions.jsonl`, each reduced).

### `cli.py`
Small additive block: `dashboard serve` subparser (`--port` int default 8765, `--path` default `.`, `--open`) and a `serve` branch in `cmd_dashboard`. No change to the import block.

### `dashboard/web/`
Vite + React 18, no router/state libs. `src/api.js` (fetch model, EventSource with auto-reconnect, debounced refetch), `src/App.jsx` (tabs), views as small components, `src/styles.css` (tokens on `:root`, dark mode via `prefers-color-scheme`, glyph + text with every colour). Build output `dist/` with relative base (`base: "./"`) so any mount works.

## Project Structure

```
specs/016-live-react-dashboard/{spec,plan,tasks,analysis-report,validation-report}.md contracts/api.md
spec-master/lib/dashboard_server.py   spec-master/tests/test_dashboard_server.py
spec-master/lib/dashboard.py (additive)  spec-master/tests/test_dashboard.py (additive tests)
spec-master/lib/cli.py (serve block)
dashboard/web/{package.json,vite.config.js,index.html,README.md,src/**,dist/**}
spec-master/tests/test_dashboard_bundle.py
```

## Risks

- Parallel feature 14 may rename the ledger entry point: mitigated by trying `summarize` then `summary` and by injection; documented as follow-up.
- Other features edit `cli.py`: the block is additive and small; the orchestrator merges.
- A stale committed bundle: manifest test guards integrity, not freshness; README documents `npm run build`.
