---
name: spec-master
description: Orquestrar autonomamente todo o workflow do Spec Kit (constitution -> specify -> clarify -> plan -> tasks -> analyze -> implement) a partir de um único arquivo de contexto.
---

# Spec Master (Claude Code skill pointer)

This file exists only so Claude Code's skill auto-discovery
(`.claude/skills/*/SKILL.md`) finds Spec Master. The actual entrypoint users
invoke is the slash command
[`.claude/commands/spec-master.md`](../../commands/spec-master.md)
(`/spec-master <context-file>`, `$ARGUMENTS`).

Neither this file nor the command duplicates the protocol. The full
model-agnostic protocol, the deterministic core, and the templates all live
in the **neutral, top-level `spec-master/` package** (not inside `.claude/`)
so that it isn't tied to any single platform:

```
../../../spec-master/PROTOCOL.md   # protocol (source of truth)
../../../spec-master/lib/cli.py    # deterministic core CLI
../../../spec-master/templates/    # normalized-doc + per-phase prompt templates
```

Read and follow `../../../spec-master/PROTOCOL.md` in full; see
`../../../spec-master/adapters/claude-code.md` for the Claude-specific notes
(argument resolution via `$ARGUMENTS`, `AskUserQuestion` for every gate).
