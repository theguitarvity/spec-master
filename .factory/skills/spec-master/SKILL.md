---
name: spec-master
description: Orquestrar autonomamente todo o workflow do Spec Kit (constitution -> specify -> clarify -> plan -> tasks -> analyze -> implement) a partir de um unico arquivo de contexto.
---

# Spec Master (Factory Droid entrypoint)

Generated entrypoint for **Spec Master**, following the same
`speckit-<command>/SKILL.md` skills-based layout Spec Kit itself installs
for Factory Droid (`.factory/skills/<name>/SKILL.md`), invoked as
`/spec-master <context-file>`.

The protocol, deterministic core, and templates are **not duplicated here**
— they live in the neutral, shared `spec-master/` package:

```
spec-master/PROTOCOL.md   # protocol (source of truth) — read and follow in full
spec-master/lib/cli.py    # deterministic core CLI
spec-master/templates    # normalized-doc + per-phase prompt templates
```

Platform specifics for this entrypoint:

1. **Argument**: the context-file path is whatever follows `/spec-master`
   in the invocation (e.g. `/spec-master CLAUDE.md`). If missing
   or the file doesn't exist, stop and explain the usage: `/spec-master <context-file>`.
2. **Deterministic core**: every structural decision goes through the shared
   core via your shell tool — the path is repo-relative and works the same
   regardless of which agent invoked it: `python3 spec-master/lib/cli.py <command> ...`.
   Never re-derive state machine, fingerprint, dependency ordering, git
   strategy, quality gates, constitution diffing, or traceability logic by
   hand — call the CLI and act on the JSON it returns.
3. **Asking the user**: use this agent's normal turn-taking in place of
   `AskUserQuestion` — but still batch every `USER_DECISION_REQUIRED` item
   from `clarify` into one message (never one question per turn), and still
   ask the Git Flow vs Trunk-Based question exactly once per workflow.
4. **Running an actual Spec Kit phase**: this repository's Spec Kit
   installation (if present) exposes `speckit-<phase>` skills under
   `.factory/skills/speckit-<phase>/SKILL.md`. Read that skill and follow it with
   the prompt generated from `spec-master/templates/prompts/<phase>.md` as the
   effective input. If no such skill exists for a phase, treat it as
   `FAILED — Spec Kit unavailable` per the stopping conditions in
   `spec-master/PROTOCOL.md`.

See `spec-master/adapters/generic.md` for the shared rationale behind every
generated (non-bespoke) adapter, and this file's header in
`spec-master/lib/adapters_gen.py` for how it was produced.

## Resuming

Re-invoking `/spec-master <context-file>` follows the exact same Step 0 (state show + fingerprint
compare) described in `spec-master/PROTOCOL.md` — no agent-specific resume logic exists or
is needed.
