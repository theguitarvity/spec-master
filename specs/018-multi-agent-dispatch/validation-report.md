# Validation report: F18 multi-agent-dispatch (M1)

Date: 2026-10-19. Base: main 03ed293 (includes F15). Result: PASSED with one deviation (SC-005 host replay).

## Gates

| Gate | Result |
|---|---|
| `python3 -m unittest discover -s spec-master/tests` | 1251 OK, 1 skipped (baseline 1122; +129, of which 47 are new F18 tests: 31 dispatch, 7 scope, 5 cli, 4 packaging; the rest came with the F15 merge) |
| `doctor run --errors-only` | exit 0, errors [], warnings step_path_budget and evidence (pre-existing) |
| `evals run` | 5/5 |
| `graph validate --path .` | valid, 0 issues |
| `packaging.py check` | ok, no drift (VERSION 0.4.0, MCP SERVER_VERSION aligned) |
| `test_protocol_conformance`, `test_cli_lazy` | OK |
| `cards/dispatch.md` | 1642 bytes (< 3 KB) |

## Acceptance criteria to tests

| Criterion | Test |
|---|---|
| FR-001/002 manifest, <= 2k tokens | test_dispatch BuildManifestTests |
| FR-003 cap 1..8, default 4 | ResolveCapTests, test_dispatch_cli |
| FR-004 reviewer != owner | RecordResultTests |
| FR-005 prepare via plan_worktree | PrepareTests |
| FR-006 result cap 8000 | RecordResultTests |
| FR-007 status join | StatusTests |
| FR-008 aggregate no merge | AggregateTests |
| FR-009 per-worktree governance | test_dispatch_scope |
| FR-010 agents per host, review read-only | test_packaging SubagentTests |
| FR-011 Patch refused | BuildManifestTests, test_dispatch_cli |
| FR-013 Team Mode untouched | no change to team_* files; existing tests pass |
| SC-004 hook cost | no marker: one `os.path.isfile` on the write path; hookd tests unchanged |

COVERED traceability rows were added to the main `.spec-master/traceability/features/multi-agent-dispatch.json`.

## SC-005 replay (T022)

Executed against a real temporary git repo through the CLI (4 packages, A/B/C independent, D depends on A): wave 0 manifest 898 estimated tokens, 6 entries, one batch of 3 (cap 2 gives 2+1); `prepare` created 3 real worktrees; three PhaseResults recorded; an owner review was refused (exit 1); `status` reported 3 of 6 recorded with explicit null notes (no events/ledger in the replay repo); `aggregate` listed `src/a|b|c/x.py` per package with `integration_state: review_pending` and merged nothing.

Deviation: launching real host subagents (Claude Code, a second host) and the per-agent token/cost comparison versus a single session was not possible from this non-interactive subagent. Follow-up: run one live wave and fill per-agent tokens from F14 (`dispatch status` already joins `by_agent`).

## INFERRED decisions

- Host agent formats (Cursor/Copilot sharing `spec-master/agents/`, Gemini `agents/`) are from knowledge, not docs; others use the fallback (contracts/host-agents.md).
- Marker/scope file locations, result record names, `kind == "spec"` selects `sm-spec`, `architect` as reviewer fallback.
- VERSION bumped 0.3.0 to 0.4.0 (MCP SERVER_VERSION constant moved in step because a test pins them).
- PROTOCOL.md not edited (F15 territory); the README and `cards/dispatch.md` carry the documentation.
