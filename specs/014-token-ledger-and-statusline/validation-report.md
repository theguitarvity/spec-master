# Validation Report: Token ledger and statusline (T3)

**Date**: 2026-10-19 | **Feature**: `token-ledger-and-statusline` (cycle 2) | **Spec**: [spec.md](spec.md)
**Tier**: M | Executed in an isolated worktree, one commit; bookkeeping written to the main checkout's state.

## Baseline vs After

| Measure | Before | After |
|---|---|---|
| `python3 -m unittest discover -s spec-master/tests` | Ran 956, OK | **Ran 1005, OK (skipped=1)** |
| pytest | `.venv` absent in the worktree: not run | not run |
| `gates detect --path .` | one blocking unittest gate | unchanged |
| `policy preflight python3` | allowed (low) | allowed (low) |
| `evals run` | 5/5 | **5/5** |
| `graph validate --path .` | valid, 0 issues | **valid, 0 issues** |
| `doctor run --errors-only` | exit 0 | **exit 0** (kernel 2459 LOC, within 2500; warnings `step_path_budget` 4844 LOC and `evidence` are pre-existing and identical in the main checkout) |

## Acceptance Criteria -> Evidence

1. **Incremental stdlib reader, persisted offset, no hardcoded path** (FR-001, FR-003): PASS.
   `ReadResponsesTests` (8) and `test_ledger.IngestTests` (idempotent re-ingest, rotation/truncation without duplicates,
   discovery via `locate_transcripts` plus event `transcript_path`).
2. **Tokens, model, estimated cost attributed to feature/phase/agent** (FR-003): PASS.
   `IngestTests`, `SummaryTests`, `estimate_cost` tests (known model priced, unknown model `null`, prices.json override).
3. **Attribution events by adapter hooks** (FR-002, FR-006): PASS. `test_events.py` (9), `test_kernel_hookd`
   subagent test, `test_kernel_install` / `test_packaging` (Claude-only SubagentStart/SubagentStop), `test_state_cli`
   phase events.
4. **Statusline** (FR-005): PASS. `test_statusline.py` (5): full line, incremental ingest, omitted unknowns,
   malformed stdin exits 0, outside a project.
5. **Unknown format degrades to 0 + note** (FR-007): PASS. `test_unknown_format_degrades_to_nothing_with_a_note`.
6. **Optional OTLP receiver**: DEFERRED (INFERRED); **schema v2 / record-round tokens / calibration**: OBSOLETE, already shipped upstream.
7. **CLI** (`tokens ingest|summary`): PASS, `test_tokens_cli.py` (3).

## Notes

- Metadata only: `test_no_message_content_reaches_the_ledger` asserts a secret in the transcript text never appears.
- Evidence for the phases was imported with `--import-unverified`: the artifacts live in the worktree commit, not in the main checkout.
- Caveat: a response whose lines straddle two ingests may be recorded from the first part only (flagged
  `output_tokens_complete: false`).
- Contract `docs/contracts/token-ledger-v1.md` unchanged. Its `host-otel` source is not in `metrics.SOURCES`; no impact until the receiver ships.
