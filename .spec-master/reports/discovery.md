# Discovery Report

Run: 2026-09-26 (restart, context = `docs/market-benchmark-roadmap.md`)

## `discovery scan` output

- `spec_kit_present`: true (`.specify/`)
- `constitution_present`: true (`.specify/memory/constitution.md`)
- `specs_dir_present`: true — existing: `001-guarded-mode-controller`,
  `002-guarded-noop-phase-validation`
- `ci_present`: false
- `docs_present`, `readme_present`: true
- `claude_md_present`, `agents_md_present`: false
- `is_git_repo`: true
- `speckit_commands`: `[]` (see note below)

## Note — Spec Kit command layout drift (real finding, not from context file)

`discovery.py` only scans `.claude/commands/speckit.*.md`,
`.opencode/commands/`, `.qwen/commands/` for `speckit.<phase>` command files.
This repository's actual Spec Kit install uses the newer skills layout
instead: `.claude/skills/speckit-{constitution,specify,clarify,plan,tasks,
analyze,implement,checklist,converge,taskstoissues}/SKILL.md`. Confirmed
present by direct listing. Per `adapters/claude-code.md` §"Executing an
actual Spec Kit phase", each phase in this run will be executed by reading
the corresponding `.claude/skills/speckit-<phase>/SKILL.md` file directly
(functionally equivalent to the `.claude/commands/speckit.<phase>.md` the
adapter doc describes — this project's Spec Kit installer just emitted the
newer convention). This does not block execution; it is the same drift
already anticipated by the project's own roadmap item about Copilot/Codex
CLI directory conventions changing — it turns out Claude Code's own Spec Kit
integration drifted too. Worth a follow-up fix to `discovery.py` later
(out of scope for this run; not one of the requested Tier 1-3 items).

## Existing normalized context (from the prior, now-superseded workflow)

`.spec-master/context/{app-features,project-goals,tech-stack}.md` exist from
the previous (restarted) run. They will be regenerated in Step 3 from the new
context file (`docs/market-benchmark-roadmap.md`).

## Git strategy (already known, not re-asked)

Prior committed state (`git log -- .spec-master/state.json`) recorded
`workflow: trunk`, all features with `branch: null`, single branch (`main`).
Repository still has only `main`. Per CLAUDE.md §38 (never ask what's already
determined by the repository), `state init` for this restart uses
`--workflow trunk` directly, without re-asking.

## Feature discovery & ordering (Step 5)

10 features upserted from `app-features.md` (all `EXPLICIT`, source
`docs/market-benchmark-roadmap.md`). `features order` (input ordered by
Tier priority as tie-break for independent nodes) resolved:

1. `parallel-worktree-execution`
2. `team-mode-parallel-workstreams` (depends on 1)
3. `speckit-tracker-orchestration`
4. `sast-quality-gate`
5. `local-dashboard`
6. `dedicated-mcp-server`
7. `context-delta-reporting`
8. `declarative-event-hooks`
9. `role-decision-memory`
10. `optional-pr-open-step`

No cycle detected. This is the execution order for Step 6.
