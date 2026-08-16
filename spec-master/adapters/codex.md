# OpenAI Codex CLI adapter

Two entrypoints, both real (not placeholders):

- **Per-project**: [`.agents/skills/spec-master/SKILL.md`](../../.agents/skills/spec-master/SKILL.md)
  — follows the same skills-based layout Spec Kit itself installs for Codex
  (`.agents/skills/<name>/SKILL.md`, invoked as `$spec-master <context-file>`
  in skills mode, matching Codex's `$speckit-<phase>` invocation style for
  the Spec Kit's own commands). Generated for any target repo by
  `init.sh link <path>`.
- **Global** (`init.sh`, no arguments): `~/.codex/skills/spec-master/SKILL.md`
  — Codex CLI's own personal/user-level skills directory, confirmed by
  inspecting a machine with Codex CLI installed (`~/.codex/skills/.system/`
  holds its built-in skills; personal ones live directly under
  `~/.codex/skills/<name>/SKILL.md`, outside `.system/`). Also mirrored to
  the shared `~/.agents/skills/spec-master/SKILL.md`, which Codex CLI scans
  in addition to `~/.codex/skills`. Once installed globally, `$spec-master
  <context-file>` works in every Codex CLI project on the machine without a
  per-repo copy.

Mapping to the core:

- The entrypoint is intentionally short: it points at
  [`../PROTOCOL.md`](../PROTOCOL.md) (the canonical protocol, shared with
  every adapter) and repeats only what's Codex-specific — how the
  context-file argument is resolved from the `$spec-master` invocation, and
  that ordinary turn-taking replaces `AskUserQuestion` for every gate (still
  batching every `clarify` question into one message, per §21 of the
  original spec).
- All structural decisions go through the same
  `python3 spec-master/lib/cli.py ...` calls as every other adapter — the
  core is plain Python 3 stdlib with no Claude-specific dependency, so it
  runs unchanged under Codex's shell tool.
- Executing an actual Spec Kit phase means reading the installed
  `.agents/skills/speckit-<phase>/SKILL.md` (Codex's default Spec Kit
  layout, invoked as `$speckit-<phase>`) and following it with the prompt
  generated from [`../templates/prompts/<phase>.md`](../templates/prompts)
  — Codex has no native "invoke this other skill" primitive, so the adapter
  inlines the target skill's own protocol instead of trying to call it.
- Templates and the deterministic core are **not duplicated** under
  `.agents/` — the Codex entrypoint reads them from this neutral
  `spec-master/` package directly, since that's just a repo-relative path
  any agent with file access can read regardless of which platform
  installed it.

## Resuming

Re-invoking `$spec-master <context-file>` follows the exact same Step 0
(state show + fingerprint compare) described in `../PROTOCOL.md` — no
Codex-specific resume logic exists or is needed.
