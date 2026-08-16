# Claude Code adapter

Entrypoints (both thin pointers, no logic of their own):

- [`.claude/commands/spec-master.md`](../../.claude/commands/spec-master.md)
  — the slash command users actually invoke (`/spec-master <context-file>`,
  `$ARGUMENTS` holds the path).
- [`.claude/skills/spec-master/SKILL.md`](../../.claude/skills/spec-master/SKILL.md)
  — exists only so Claude Code's skill auto-discovery
  (`.claude/skills/*/SKILL.md`) also finds Spec Master.

Neither file duplicates the protocol or the core; both point back at
[`../PROTOCOL.md`](../PROTOCOL.md) and [`../lib/cli.py`](../lib/cli.py),
which live in this neutral, top-level `spec-master/` package — not inside
`.claude/` — precisely so they aren't Claude-specific, since the same core
also backs the [Copilot](copilot.md) and [Codex](codex.md) adapters.

Mapping to the core:

- The command body is intentionally short: it points at `spec-master/PROTOCOL.md`
  as the protocol to follow and repeats only the two Claude-specific
  mechanics — how `$ARGUMENTS` is resolved and that `AskUserQuestion` is the
  tool to use for every gate (§7 git-strategy question, §21 batched
  clarifications, §16 constitution conflicts).
- All structural decisions go through `Bash` calls to
  `python3 spec-master/lib/cli.py ...` — identical to every other adapter,
  so the tested behavior (state machine, fingerprint, ordering, git
  strategy, quality gates, traceability) is shared, not reimplemented in the
  prompt.
- Reading/writing files uses Claude Code's `Read`/`Write`/`Edit` tools.
- Executing an actual Spec Kit phase means reading the installed
  `.claude/commands/speckit.<phase>.md` file (created by the Spec Kit's own
  installer) and following its instructions with the prompt generated from
  `spec-master/templates/prompts/<phase>.md` as the effective argument —
  Claude Code has no way to programmatically invoke another slash command,
  so the adapter inlines the target command's own protocol instead of
  trying to "call" it.

## Resuming

Claude Code re-invokes `/spec-master <context-file>` the same way on a fresh
session; Step 0 of `PROTOCOL.md` (state show + fingerprint compare) handles
resume/restart without any Claude-specific logic.
