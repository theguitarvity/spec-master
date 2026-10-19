# Implementation Plan: Multi-Agent Dispatch (M1)

**Spec**: `specs/018-multi-agent-dispatch/spec.md` | **Contract**: `contracts/dispatch-manifest.md`
**Constitution check (2.0.0)**: stdlib only (II); tests mirror modules (III); atomic writes through existing helpers (IV); no reimplementation of `speckit.*` or of `worktree`/`team_model`/`phase_result` (VII); gates auto-detected (VIII); no new dependency (IX); no auto-merge/publish (X); native mode untouched (VI). PASS.

## Approach

The core stays deterministic and process-free. It (1) computes a per-wave manifest, (2) prepares isolated worktrees plus a governance scope, (3) ingests each subagent's bounded `PhaseResult`, (4) reports status joined with F14 events/ledger, (5) aggregates for the Tech Lead. The host does the launching, through subagents that `packaging.py` generates once and renders per host. `hookd` enforces the scope per worktree.

```
tasks/workstreams -> compute_waves(packages) -> build_manifest (cap -> batches)
      -> prepare: plan_worktree + scope/<key>.json + <worktree>/.spec-master/worktree.json
      -> host launches sm-implement (parallel, one worktree each) ... sm-review (after owner)
      -> hookd pre-tool-use: marker? -> dispatch_scope.decide (owned_paths, read-only, denied git)
      -> subagent final message: one phase_result block -> dispatch result (<= 8000 chars)
      -> F14 hookd subagent-stop writes agent.finished; dispatch status joins tokens by_agent
      -> dispatch aggregate (worktree.aggregate + conflicts + integration_state) -> Tech Lead (manual)
```

## Design decisions (all INFERRED unless noted)

1. **New module `spec-master/lib/dispatch.py` (~220 LOC), outside `kernel/`.** Functions: `resolve_cap`, `build_packages(root, feature)`, `build_manifest`, `prepare`, `record_result`, `status`, `aggregate`. Imports `worktree`, `team_model`, `team_workstreams`, `phase_result`, `risk_profile`, `state` helpers; zero duplicated logic. Not imported by the step path (keeps `step_path_budget` unchanged).
2. **New module `spec-master/lib/dispatch_scope.py` (~90 LOC)**: `load_marker(root)`, `decide(root, payload, verdict)` returning a policy verdict (`allow|ask|deny`). Pure functions over the marker; path matching via `kernel/paths` (glob/`norm`), command screening via `kernel/policy.decide_command` first, then a denylist for merge/push/rebase/worktree-remove/branch-delete.
3. **hookd hook point <= 20 LOC.** In `pre_tool_use`, after computing the base verdict: `if os.path.isfile(<root>/.spec-master/worktree.json): verdict = _scoped(root, payload, verdict)`, where `_scoped` lazily imports `dispatch_scope`. Decision log entry gains `agent_key`. No marker -> no import, no cost (SC-004). Implemented LAST because F14 (events in `subagent-stop`) and F17 (TDD hook) also edit `hookd.py`; rebase on their merged version.
4. **Agents via `packaging`.** New `spec-master/lib/packaging_agents.py` (~120 LOC) holds the three role specs (name, description, tools, model hint = none, body referencing `cards/dispatch-<role>.md`) and per-host renderers; `packaging.render()` adds the files (one merge line plus VERSION bump). Hosts: claude (`spec-master/agents/*.md`), qwen/gemini/cursor/copilot (Markdown with frontmatter at each host's plugin path), codex/kiro (their documented format), and `fallback_instructions` for agent-plugins/antigravity. `sm-review` tools are read-only (no Write/Edit); `sm-implement` and `sm-spec` have write tools. `check`/`generate` cover them; `doctor` already runs `packaging.check`.
5. **Cards.** One short card `spec-master/cards/dispatch.md` (<= 3 KB) shared by the three agents: role contract, owned paths, TDD order (reads the F17 card id), the single-PhaseResult ending, "never merge". Agent bodies are ~10 lines pointing at it.
6. **Cap and batches.** `resolve_cap(root, arg)`; batches are consecutive slices by package id order within a wave (deterministic). `sm-review` entries are placed in the batch after their owner's and flagged `after: [owner agent_key]`.
7. **Reviewer != owner.** Reuse `risk_profile._reviewer_for`/`team_model.assign_peer_review`; assert in `build_manifest`; `record_result` refuses a review whose `agent_key` equals the owner's.
8. **Results.** Allow-list + 8000-char cap; stored under `.spec-master/dispatch/<feature>/<wave>/<package>.json`; written via a temp file + `os.replace` (same atomic pattern as `state`). The host-provided `agent_id` is stored when passed, so `status` can join the ledger.
9. **Status joins F14.** Guarded read of `.spec-master/events.jsonl` (tolerant line reader) and `ledger`/`tokens summary` (`by_agent`); both optional. Corrupt lines skipped.
10. **CLI.** `cli.py dispatch {manifest,prepare,result,status,aggregate}` (one subparser block + dispatch branch, ~40 LOC in cli.py, not in kernel/); `harness entrypoint` text gains one line only if the lane card needs it.
11. **Policy key.** `policy.json` gains optional `dispatch: {max_agents}`; absent = default; unknown keys ignored (existing policy loader untouched; read directly in `dispatch.resolve_cap`).

## Files

| File | Action | Owner task |
|---|---|---|
| spec-master/lib/dispatch.py | new | T004, T006, T008, T010 |
| spec-master/lib/dispatch_scope.py | new | T014 |
| spec-master/lib/packaging_agents.py | new | T018 |
| spec-master/lib/packaging.py | edit (merge agent files, VERSION) | T018 |
| spec-master/lib/kernel/hookd.py | edit (<= 20 LOC) | T020 |
| spec-master/lib/cli.py | edit (dispatch subparser) | T012 |
| spec-master/cards/dispatch.md | new | T017 |
| spec-master/agents/*, per-host generated files | generated | T018 |
| spec-master/tests/test_dispatch.py, test_dispatch_scope.py, test_dispatch_cli.py | new | T002-T013 |
| spec-master/tests/test_packaging.py, test_kernel_hookd.py | extend | T016, T019 |
| spec-master/PROTOCOL.md, README.md | edit | T021 |

## Risks

- **hookd shared edits (F14, F17, F18)**: rebase last; budget check at T022 (`doctor`).
- **Host agent formats unverified**: T018 starts with a docs check recorded in `contracts/host-agents.md`; unknown hosts use the fallback instructions, never a guessed file.
- **Worktree `.spec-master/` copies**: tracked `state.json` exists in worktrees; the marker makes `dispatch_scope` DENY writes to it; agents never run `cli.py state ...` (the card says the main session owns bookkeeping).
- **Parallel speed claim unmeasured**: SC-005 replay at validate decides; fallback is single-session cards (proposal risk table).
- **Event gaps before F14**: status degrades to nulls, tests use fixtures.

## Quickstart (post-implement)

`dispatch manifest --feature F --wave 0` -> `dispatch prepare ...` -> host launches `sm-implement` agents -> `dispatch result --package P --text-file out.txt` -> `dispatch status` -> `dispatch aggregate --wave 0` -> `workstreams review|integrate` (manual).
