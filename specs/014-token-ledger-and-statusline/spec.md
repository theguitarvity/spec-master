# Feature Specification: Token ledger and statusline (T3)

**Feature Branch**: `014-token-ledger-and-statusline` (trunk-based; implemented in an isolated worktree, one commit)

**Created**: 2026-10-19

**Status**: Draft

**Input**: "Tornar o consumo de tokens das sessoes do Spec Master sempre visivel e real (opcao T3)." (`docs/performance-multiagent-speed-roadmap.md` §5/§6; `.spec-master/context/app-features.md` Ciclo 2, Feature 14)

## Grounding (DISCOVERED_FROM_CODEBASE)

- `spec-master/lib/telemetry.py` already discovers transcripts by cwd slug (`locate_transcripts`, `session_transcripts`), de-duplicates responses by `message.id`, splits main thread vs subagents and returns aggregates (`read_transcript_usage`). It has no per-response output and no persisted offset, so a second reader would duplicate its parser.
- `telemetry ingest --append` and metrics schema v2 (`source`, `cost_basis`) already exist; calibration already ignores unmeasured rows (H7 mostly closed).
- `kernel/hookd.py` maps `subagent-stop` to a no-op; there is no `SubagentStart` entry in `kernel/install.py` or `packaging.py`.
- `docs/contracts/token-ledger-v1.md` (revised, owned by the orchestrator) fixes the formats of `.spec-master/events.jsonl`, `.spec-master/metrics/tokens.jsonl` and `tokens summary`. This feature is its producer; the live dashboard consumes it.
- `doctor run --errors-only` enforces `kernel/` <= 2500 LOC (about 56 left) and the hook path budget (<= 1500 LOC, 100 ms p50).

## Clarifications

### Session 2026-10-19

Autonomous run; no question was blocking, each was resolved as INFERRED.

- Q: The original criteria say "schema v2" and "record-round accepts ledger tokens". → A: OBSOLETE (INFERRED, reason: re-scope report for F14): schema v2 and `telemetry ingest --append` already shipped upstream; the remaining delta replaces those criteria with the ledger, events, `tokens` CLI and statusline below.
- Q: Is the OTLP/HTTP receiver in scope? → A: Deferred (INFERRED; the re-scope marks it optional). Recorded as a follow-up; the ledger `source` enum already reserves `host-otel`.
- Q: Which hosts get SubagentStart/SubagentStop hook entries? → A: Claude Code only (INFERRED; the only host whose payload and event names were verified). Other hosts keep the existing four events.
- Q: Who writes `phase.started`/`phase.finished`? → A: `state transition` (INFERRED; it is the single choke point of the phase machine). Session id is `null` there and matches any session.
- Q: Cost without a measured source? → A: Estimated from a documented list-price table (`cost_basis: "estimated"`), `null` for a model the table does not know (INFERRED; contract §2).
- Q: A response whose lines straddle two reads? → A: Emitted once, on first sight, with the usage seen then (INFERRED; transcript lines of one response repeat the same usage object).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Incremental per-response reader (Priority: P1)

The ledger needs one record per model response without re-reading whole transcripts.

**Independent Test**: read a transcript twice with the returned offset; the second read yields only new responses.

**Acceptance Scenarios**:

1. **Given** a transcript with N responses, **When** `telemetry.read_responses(path)` runs, **Then** it yields N records (one per `message.id`, usage taken as the per-field max) and the byte offset after the last complete line.
2. **Given** that offset, **When** more lines are appended and the reader runs again from the offset, **Then** only responses from the new lines are yielded.
3. **Given** a half-written last line, **When** read, **Then** the offset stops before it.
4. **Given** the same transcript, **When** `read_transcript_usage` runs, **Then** its totals are unchanged (shared absorb logic, no second parser).

### User Story 2 - Attribution events (Priority: P1)

**Acceptance Scenarios**:

1. **Given** a SubagentStart/SubagentStop hook payload, **When** hookd handles it, **Then** `agent.started`/`agent.finished` is appended to `.spec-master/events.jsonl` with `agent_id`, `agent_type`, `transcript_path`, `session_id` and the active `feature_id`/`phase`.
2. **Given** `state transition ... RUNNING|PASSED|FAILED|BLOCKED|SKIPPED`, **Then** `phase.started`/`phase.finished` is appended (best effort, never fails the transition).
3. **Given** the packaged Claude hooks and `install-hooks`, **Then** both include SubagentStart and SubagentStop.

### User Story 3 - Token ledger and summary (Priority: P1)

**Acceptance Scenarios**:

1. **Given** transcripts for the project, **When** `tokens ingest` runs, **Then** one `spec-master.tokens/v1` line per response is appended to `.spec-master/metrics/tokens.jsonl`, with feature/phase/agent attribution from `events.jsonl` or `null`.
2. **Given** `tokens ingest` runs twice, **Then** no line is duplicated (offsets + request-id de-duplication).
3. **Given** a transcript with no recognisable usage, **Then** ingest appends nothing and reports a note; no count is invented.
4. **Given** a known model, **Then** `cost_usd` is estimated with `cost_basis: "estimated"`; an unknown model gives `null`.
5. **Given** the ledger, **When** `tokens summary [--since]` runs, **Then** it prints `spec-master.tokens-summary/v1` exactly as in contract §3 (totals, by_feature, by_phase, by_agent, by_model, burn rate, window, cache hit ratio).
6. **Given** a ledger with sidechain responses lacking final output, **Then** `output_tokens_complete` is `false` on those lines.

### User Story 4 - Statusline (Priority: P2)

**Acceptance Scenarios**:

1. **Given** the host's statusline JSON on stdin, **When** `statusline.py` runs, **Then** it prints one line with feature, phase, tier, session tokens, cost, cache hit and context % (omitting what is unknown) and exits 0 even on malformed input.
2. **Given** a stale ledger, **Then** the statusline ingests the session transcript incrementally first.
3. **Given** README/docs, **Then** the install snippet for `statusLine` is documented.

### Edge Cases

- Missing/empty/rotated (shorter than offset) transcript; non-JSON lines; synthetic model; ledger file absent for `summary` (empty aggregate with zero totals).
- Concurrent ingests: append under the existing file-lock pattern, offsets saved atomically.

## Requirements *(mandatory)*

- **FR-001**: `telemetry.read_responses(path, offset=0)` returns per-response records and the new offset, reusing the same absorb code as `read_transcript_usage`.
- **FR-002**: `lib/events.py` appends and reads `spec-master.event/v1` lines; hookd `subagent-start`/`subagent-stop` and `state transition` call it; logic stays outside `kernel/`.
- **FR-003**: `lib/ledger.py` ingests incrementally (persisted offsets, de-duplication), attributes, estimates cost and summarises per contract.
- **FR-004**: `cli.py tokens ingest|summary` (additive block).
- **FR-005**: `lib/statusline.py` renders the status line; install documented.
- **FR-006**: Hook entries for SubagentStart/SubagentStop in `kernel/install.py` and `packaging.py` (Claude only); generated plugin files regenerated; `doctor run --errors-only` exits 0.
- **FR-007**: Unknown/unreadable formats degrade to nothing + note; never an invented count.
- **FR-008**: Prompt/response content is never read into the ledger (metadata only).

## Success Criteria

- **SC-001**: A second `tokens ingest` over unchanged transcripts appends 0 lines.
- **SC-002**: `tokens summary` totals equal `read_transcript_usage` totals over the same transcripts (parity test).
- **SC-003**: hook path stays within `doctor` budgets.

## Requirements traceability (original acceptance criteria)

| Original criterion | Disposition |
|---|---|
| Incremental stdlib reader with offset, no hardcoded path | FR-001, FR-003 |
| Tokens/model/cost attributed to feature/phase/agent | FR-003 |
| Attribution events by adapter hooks | FR-002, FR-006 |
| Optional OTLP receiver | Deferred (INFERRED) |
| metrics round schema v2; record-round accepts ledger tokens | OBSOLETE (shipped upstream; INFERRED) |
| Statusline | FR-005 |
| calibration uses real tokens (H7) | Already closed upstream (INFERRED) |
| Unknown format degrades to 0 + note | FR-007 |
