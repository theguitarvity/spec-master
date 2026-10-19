# Implementation Plan: Token ledger and statusline (T3)

**Branch**: `014-token-ledger-and-statusline` (trunk-based) | **Date**: 2026-10-19 | **Spec**: [spec.md](./spec.md)
**Input**: `specs/014-token-ledger-and-statusline/spec.md`; contract `docs/contracts/token-ledger-v1.md`

## Summary

Refactor `telemetry.py` so one absorb routine serves both the aggregate reader and a new incremental per-response
reader (`read_responses`, persisted byte offset). New modules outside `kernel/`: `events.py` (attribution event
stream), `ledger.py` (ingest, attribution, cost estimate, summary), `statusline.py`. Small additive wiring:
`tokens` CLI group, a best-effort phase event in `state transition`, hookd `subagent-start`/`subagent-stop`
handlers that delegate to `events.py`, and SubagentStart/SubagentStop entries in `kernel/install.py` and
`packaging.py` (Claude only).

## Technical Context

**Language/Version**: Python 3 stdlib only | **Storage**: JSONL under `.spec-master/` (append-only), offsets in `.spec-master/metrics/tokens.offsets.json` (atomic replace)
**Testing**: `python3 -m unittest discover -s spec-master/tests`; mirrored `test_events.py`, `test_ledger.py`, `test_statusline.py`, additions to `test_telemetry.py`, `test_kernel_hookd.py`, `test_kernel_install.py`, `test_packaging.py`
**Constraints**: `kernel/` <= 2500 LOC (only a few lines added); hook path <= 1500 LOC and 100 ms p50 (events.py is small and imported lazily); contract is not modified.

## Constitution Check

| Principle | Check | Status |
|---|---|---|
| I Deterministic core | Logic in `spec-master/lib/`, exposed through `cli.py tokens` | PASS |
| II Stdlib-only | No dependency | PASS |
| III Test-first / mirrored tests | One test module per new module, written first | PASS |
| IV Atomic state | Offsets written with temp file + `os.replace`; `state.json` untouched | PASS |
| V Non-destructive | Ledger/events are append-only; corrupt lines skipped, never rewritten | PASS |
| VI Backwards-compatible | `read_transcript_usage` output unchanged (parity test); native mode untouched | PASS |
| VII Reuse | Reuses `telemetry` parser, `locate_transcripts`, `TOKEN_FIELDS`, `metrics.SOURCES/COST_BASES` | PASS |
| VIII Gates auto-detected | n/a | PASS |
| IX Isolation of exceptions | n/a | PASS |
| X No auto-publishing | Local files only | PASS |

## Design

1. **telemetry.read_responses(path, offset=0)** -> `(records, new_offset)`. Reads bytes from `offset`, consumes only newline-terminated lines, groups lines by response key with the shared `_absorb_response`. Record: `key, request_id, session_id, agent_id, sidechain, model, ts, tokens, final`.
2. **events.py**: `append(root, type, **fields)`, `read(root)`, `on_agent(root, kind, payload)`, `on_phase(root, feature, phase, status)`, `active_window(events, session, ts)`. Event schema per contract §1; failures never raise.
3. **ledger.py**: `ingest(root, transcripts=None)` discovers transcripts with `telemetry.locate_transcripts(include_subagents=True)` plus event `transcript_path`s; per file offset + seen keys; attribution via events (open phase window by session or null; agent type via `agent.started`); `estimate_cost(model, tokens)`; `summary(root, since=None, session=None)`.
4. **cli**: `tokens ingest [--path] [--transcript P]`, `tokens summary [--path] [--since]`.
5. **statusline.py**: stdin host JSON -> incremental ingest of `transcript_path` -> one line.
6. **Hooks**: hookd handlers delegate to `events.on_agent`; install/packaging add the two events for Claude; regenerate plugin files.

## Risks

kernel LOC budget (mitigated: logic outside kernel), hook p50 (single append), packaging divergence (regenerate + test), straddling responses (documented).
