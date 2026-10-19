# Spec Master Execution Report — cycle 2 (performance, multi-agent, speed, tokens, live dashboard)

## Context

- Context file: `docs/performance-multiagent-speed-roadmap.md` (dogfood run, 2026-10-19).
- Request (EXPLICIT): brownfield/greenfield compatibility assessment, performance, multi-agent mode,
  speed mode (TDD first), always-visible token consumption, real-time React dashboard.
- User decisions: M1 subagents + dispatch manifest; S1 refined to the harness proposal's Standard lane;
  D1 stdlib SSE + React/Vite committed bundle; T3, P1–P6, B1+G1 adopted as recommended defaults (INFERRED).

## Git Strategy

Trunk-based on `main`. Features ran as parallel Sonnet worktree agents and were merged by the
orchestrator with `--no-ff`. Mid-cycle, origin/main had moved 22 commits (harness kernel, hookd,
telemetry, lanes/cards, packaging, CI). It was merged first (33 conflicts resolved) and every feature
was re-scoped to the remaining delta (`rescope.md`, roadmap §7). Merge order: F19 → F17 → F14 → F16 → F15 → F18.

## Constitution

2.0.0 (upstream). No amendment needed. Principle VII is preserved: the full cycle always runs
`/speckit.analyze`. The deterministic `verify:pre` replaces it only inside the Standard lane.

## Features

| # | Feature | Tier | Spec dir | Status | Trace rows |
|---|---|---|---|---|---|
| F19 | brownfield-greenfield-tracks | — | specs/019 | COMPLETED | 5 COVERED |
| F17 | speed-mode-tdd-first | M | specs/017 | COMPLETED | 6 COVERED |
| F14 | token-ledger-and-statusline | M | specs/014 | COMPLETED | 5 COVERED |
| F16 | live-react-dashboard | S | specs/016 | COMPLETED | 11 COVERED |
| F15 | protocol-and-cli-performance | M | specs/015 | COMPLETED | 13 (status `PASSED`) |
| F18 | multi-agent-dispatch | M | specs/018 | COMPLETED | 10 COVERED + 5 PLANNED |

What was delivered:
- **F19:** monorepo package discovery; `tracks brownfield-map|brownfield-constitution|brownfield-characterize`
  and greenfield bootstrap. Everything is a proposal and is never applied without the user's approval.
  Cards: `cards/brownfield.md`, `cards/greenfield.md`.
- **F17:** `standard begin|verify-pre|red|green`, the deterministic analyze (`verify_pre`), and TDD RED/GREEN gates
  that record evidence.
- **F14:** `events.jsonl` (phase/agent attribution) and the `metrics/tokens.jsonl` ledger, deduplicated by
  `message.id`. Also `tokens ingest|summary`, the Claude Code statusline, and SubagentStart/Stop hooks.
- **F16:** `dashboard serve`, a loopback-only SSE server with a React/Vite UI. The `dist/` bundle is committed
  and checked against a sha256 manifest. 8 views, including tokens, per-cycle progress, gates, agents, and lanes/hook decisions.
- **F15:**
  - `state advance` (transition + round + rows + next step in one call)
  - a full-cycle router card plus `protocol show --section`
  - per-phase model/effort hints
  - a pruned snapshot walk with a hash cache
  - a debounced dashboard
  - in-process MCP
  - lazy CLI imports
- **F18:** `sm-spec` / `sm-implement` / `sm-review` subagents generated for 8 hosts; `dispatch` manifest
  (≤2k tokens), agent cap per wave, reviewer ≠ owner, per-worktree scope governance in hookd.
  Team Mode is frozen.

Post-merge wiring (`62e798d`):
- H6 closed: `risk_profile.light_analyze` runs on XS/S, and its result is returned as `next.light_analyze`.
- A single prune list is shared by discovery and the phase snapshot.
- The routers link the brownfield/greenfield cards.

## Traceability

`.spec-master/reports/traceability.md`: 89 rows over all features. Cycle 2: 60 rows. Two oddities:
- F15 recorded its 13 rows with status `PASSED` instead of `COVERED`.
- F18 keeps 5 `PLANNED` rows from planning, alongside its 10 `COVERED` rows.

## Quality Gates

| Gate | Result |
|---|---|
| `python3 -m unittest discover -s spec-master/tests` | 1251 tests OK (1 skipped). This was 956 when cycle 2 started on upstream |
| `doctor run --errors-only` | exit 0; warnings: `step_path_budget` (5248 LOC vs 4500 target), `evidence` |
| `evals run` | 5/5 |
| `graph validate` | 0 issues; health 98 (A); snapshot `cycle-2-final` |
| `packaging.py check` | no drift (VERSION 0.4.0) |
| `kernel/` LOC | 2474 / 2500 |
| hooks audit | 1761 decisions in 21 days, would-block rate 0.23% (target 2%) |

Measured performance (F15):
- `state show` went from 106 to 77 ms, and `--help` from 102 to 80 ms.
- A warm snapshot walk went from 14.6 to 6.9 ms.
- Protocol read per full-cycle step went from 39.9 KB to 7–14 KB.

## Delivery Metrics

- `metrics summarize`: 37 rounds. All cycle-2 rounds were typed by hand with 0 tokens (`manual-unverified`).
- Token ledger, first real ingest:
  - 25 transcripts and 1739 responses, ingested in 0.2 s.
  - 1.27M input+output tokens, plus 179M cache-read and 5.5M cache-creation tokens.
  - Cache hit rate 97%. Estimated cost $125.10 (`cost_basis: estimated`).
  - Only phases opened after `events.jsonl` existed are attributed to a feature (F14, F18).
  - The ledger files are local runtime data and are gitignored.
- F18 rounds: `f18-spec-half` was recorded with the wrong window (11:50–12:20Z instead of about 11:49Z).
  The start of `f18-implement` is an estimate. Rounds are never edited by hand.

## Remaining Risks

- Evidence:
  - F14 has 7 phases that were promoted `unverified` while its artifacts lived in a worktree. A dry-run of
    `state evidence --phase` passes for all 7 on main now. There is no CLI to re-record it.
  - F18 has 5 such phases (specify–analyze); its implement and validate phases are verified.
  - 4 older features show `missing` evidence because they were promoted before evidence existed.
- F18 host agent formats are INFERRED for Cursor, Copilot and Gemini. They need a check on a real install.
  The SC-005 replay with real host subagents and per-agent tokens is still pending.
- The F16 debounce is leading-edge only, so the last event in a 2 s window renders at the next event.

## Technical Debt

- `step_path_budget`: 5248 LOC against a 4500 target.
- Splitting PROTOCOL Step 6 further.
- A trailing dashboard render.
- A CLI path to re-verify evidence for phases imported as unverified.

## Final Status

**SUCCESS_WITH_WARNINGS.**
- All 6 cycle-2 features are COMPLETED; the suite, `doctor`, evals, graph and packaging checks are green.
- Warnings: evidence that is unverified or missing on previously imported phases, and the step-path LOC budget.
