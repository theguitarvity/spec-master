# Feature Specification: Protocol and CLI Performance (P1-P6)

**Feature Branch**: `015-protocol-and-cli-performance` (trunk-based: no dedicated branch)

**Created**: 2026-10-19

**Status**: Draft

**Input**: "Cut agent round-trips, protocol tokens and per-phase I/O (P1-P6)." (`docs/performance-multiagent-speed-roadmap.md` section 3; `.spec-master/context/app-features.md`, Ciclo 2, Feature 15). Re-scoped after the upstream merge by the cycle-2 v2 addendum: the "Remaining delta" of the F15 re-scope report replaces the original criteria where they conflict (INFERRED, reason: upstream already delivered the output diet, `state show --summary`, the lane router/cards and part of the protocol prune, and owns a `step` lane API).

## Grounding (DISCOVERED_FROM_CODEBASE)

- Already delivered upstream and NOT redone: CLI output diet (-86% stdout, transition ack), `state show --summary`, the lane router and cards (`spec-master/cards/`, `kernel/step.py`), a partial `PROTOCOL.md` prune (49.8 KB to 37.9 KB with `docs/protocol-reference.md`).
- P1: the full cycle needs one `state transition` (RUNNING), another after the work (PASSED), plus `metrics record-round` and one `traceability add` per row: 3+ calls per phase. The kernel owns a lane API named `step`; the full-cycle composite must not reuse that name.
- P2: the full-cycle entrypoint (`templates/entrypoints/full-cycle.md`) tells the agent to read all of `PROTOCOL.md` (37,952 bytes) before anything else.
- P3: `risk_profile.CEREMONY_PROFILES` declares which phases are required/skippable but nothing about the model or effort a phase needs.
- P4: `phase_contracts.snapshot` does `project.rglob("*")` and filters afterwards, so it descends into `node_modules`, `.venv`, `dist`, `build`, `target` before discarding; it re-hashes every file on every call.
- P5: `hooks.py` emits the dashboard re-render on every event; `dashboard.build_model` rebuilds the graph each time.
- P6: `mcp/spec_master_mcp.py` `run_cli` spawns `python3 cli.py` per tool call; `cli.py` imports about 30 modules eagerly.

## Clarifications

### Session 2026-10-19

Autonomous run (no user): no blocking question; every default below is INFERRED.

- Q: Name of the composite command? -> A: `state advance` (the kernel `step` lane API already exists with different semantics; the re-scope report asks for a different name).
- Q: Does "delta" belong in the composite? -> A: No (re-scope report P1 says transition + record + next): the answer carries the next step instead.
- Q: What does "on-demand sections via CLI" look like? -> A: `protocol sections` lists headings with byte sizes, `protocol show --section <query>` prints one section; the full-cycle router points at them. No second copy of the protocol text (it would drift).
- Q: Which directories does the snapshot prune? -> A: the existing ones plus `dist`, `build`, `target`, `.tox`, `.mypy_cache`, `.pytest_cache`, `vendor`, `vendored`, `.next`, `coverage`. Only DIRECTORY names are pruned; a file named `build` is still hashed.
- Q: Process model for MCP? -> A: in-process dispatch of `cli.main` with captured stdout/stderr, cwd and env restored under a lock; automatic fallback to the subprocess path when the call cannot run safely. Tool results stay identical (content, isError, structuredContent).
- Q: Hint vocabulary? -> A: host-neutral classes (`model`: `fast|balanced|deep`; `effort`: `low|medium|high`), never vendor model names.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - One call per phase boundary (Priority: P1)

The agent closes a phase with one `state advance` call that moves the phase, optionally records the round and traceability rows, and answers with the next step.

**Acceptance Scenarios**:
1. **Given** a feature with `specify` RUNNING and its artifact present, **When** `state advance --feature F --phase specify --status PASSED --round-json {...} --trace-json [...]` runs, **Then** the phase is PASSED with evidence, the round is appended to `rounds.json`, the rows are in the feature traceability store, and the answer names the next phase with its model/effort hint.
2. **Given** evidence is missing, **When** the same call runs, **Then** it fails with the same error as `state transition` and nothing else is written (no round, no rows).
3. **Given** the last phase passes, **Then** the answer says `next: null` and `feature_status: COMPLETED`.

### User Story 2 - Short router plus the card for the current step (Priority: P1)

The full-cycle entrypoint loads a router of at most 5 KB and, for each step, only the PROTOCOL section for that step.

**Acceptance Scenarios**:
1. `cards/full-cycle.md` is at most 5,120 bytes and names every step with the exact `protocol show --section` call.
2. `protocol sections` lists every heading with its byte size; `protocol show --section "Step 6"` prints that section only; an unknown or ambiguous query fails and lists the candidates.
3. The full-cycle entrypoint says "read the router and the card for the current step" and no longer says "read PROTOCOL.md in full"; `test_protocol_conformance` stays green; the lane text is unchanged.

### User Story 3 - Per-phase model/effort hint (Priority: P2)

1. `risk profiles`/`risk profile` show `hints` per phase for each tier; every phase of every tier has a valid `model` and `effort`; XS/S downshift.
2. The hint is emitted in the `state advance` next block and in the controller phase prompt.

### User Story 4 - Cheap snapshot (Priority: P2)

1. `snapshot` never descends into pruned directories and ignores `dist/ build/ target/` and vendored trees.
2. Files with unchanged (size, mtime_ns) are not re-hashed (cache under `.spec-master/cache/`); a changed file is re-hashed; the result equals the uncached result.
3. `phase_contracts.walk_project(project)` is exposed and `discovery` reuses it where it lists files.

### User Story 5 - Quiet dashboard (Priority: P3)

1. Hook-driven re-render is debounced (a render within the window is skipped unless forced) and the graph is cached by file size/mtime, so unchanged inputs never rebuild it.

### User Story 6 - Fast MCP and CLI (Priority: P2)

1. MCP tool calls run the core in-process; results are identical to the subprocess path; a crash or `SystemExit` inside the core becomes an error result and never kills the server.
2. `cli.py` imports each command module on first use; `--help` and all existing commands still work; `state show` latency drops.

### Edge Cases
- `state advance` with invalid round/trace JSON fails before any write.
- Cache file corrupt or unwritable: snapshot falls back to hashing.
- Debounce state unreadable: render proceeds.
- In-process MCP call for a command that reads stdin: subprocess fallback.

## Requirements *(mandatory)*

- **FR-001** `state advance` (P1): transition, optional `--round-json`, optional `--trace-json` (list), answer with `next`. Reuses the transition code of `state transition` and a next-phase function in `state.py` shared with the controller. Transition + traceability rows under one state transaction; the round is appended only after the transition succeeded.
- **FR-002** `cards/full-cycle.md` <= 5,120 bytes; `protocol sections|show`; entrypoint text updated (P2).
- **FR-003** Ceremony profiles declare `hints` per phase; emitted in the advance answer and the controller prompt (P3).
- **FR-004** `phase_contracts.snapshot` prunes during the walk, adds the listed directory names, caches hashes by (size, mtime_ns), exposes `walk_project` (P4).
- **FR-005** Dashboard re-render in `hooks.py` debounced; `dashboard.py` caches the graph (P5).
- **FR-006** MCP in-process dispatch with subprocess fallback; `cli.py` lazy imports as one isolated change, done last (P6).
- **FR-007** Before/after numbers (CLI latency, protocol bytes per full-cycle step, snapshot walk time) in `validation-report.md`.
- **FR-008** stdlib only; native behaviour unchanged; `doctor run --errors-only` exits 0; `test_protocol_conformance` green; new code outside `kernel/`.

## Success Criteria
- **SC-001** Bytes loaded for a full-cycle step (router + one section) are under 40% of the 37,952-byte protocol.
- **SC-002** Median `state show` latency is lower than the 106 ms baseline.
- **SC-003** Snapshot never visits pruned directories.
- **SC-004** `python3 -m unittest discover -s spec-master/tests` passes.

## Out of scope
Token ledger/telemetry, `dashboard serve`, `lib/dashboard_server.py` (other features); `kernel/` changes; Spec Kit internals.
