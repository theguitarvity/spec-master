# Card: multi-agent dispatch (Standard and Critical lanes)

Use only when a wave has 2+ independent work packages. Patch never dispatches. The core never launches agents: the host's subagent tool does.

## Tech Lead (main session)
1. `dispatch manifest --feature F --wave N [--max-agents K]` -> batches of at most K agents (default 4, max 8).
2. `dispatch prepare --feature F --wave N` creates one worktree per package plus its governance scope.
3. Launch the `sm-implement` (or `sm-spec`) agents of the first batch in parallel, each given its manifest entry. Next batch when the previous one ends.
4. Per agent: `dispatch result --feature F --wave N --package P --agent-id ID --text-file out.txt`.
5. `dispatch prepare --phase review`, then launch the `sm-review` agents. The reviewer is never the owner.
6. `dispatch status` shows started/finished/tokens per agent. `dispatch aggregate` reports changed files and conflicts.
7. Integrate by hand with `workstreams review` then `workstreams integrate`. Nothing is merged automatically.

## Subagent contract
- Work only inside your worktree and `owned_paths`. Writes elsewhere are blocked (blocked mode) or logged (audit mode).
- `sm-implement`: failing test first, then code, then the package's checks.
- `sm-review`: read-only; report findings, never edit.
- Finish with ONE PhaseResult block under 2000 tokens: `artifact_updated | no_changes_required | user_decision_required | failed` plus summary, files and evidence.
- Never merge, rebase, push or remove a worktree.

## Hosts without subagents
Run the entries sequentially in one session (see `fallback_instructions` in the manifest).
