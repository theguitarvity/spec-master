# GitHub Copilot adapter

Two entrypoints, both real (not placeholders):

- **Per-project**: [`.github/skills/spec-master/SKILL.md`](../../.github/skills/spec-master/SKILL.md)
  — follows the same `speckit-<command>/SKILL.md` skills-based layout Spec
  Kit itself installs for Copilot (`.github/skills/<name>/SKILL.md`), so
  this package sits alongside a real Spec Kit installation the same way its
  own `speckit-*` skills do. Generated for any target repo by
  `init.sh link <path>`.
- **Global** (`init.sh`, no arguments): `~/.copilot/skills/spec-master/SKILL.md`
  and `~/.copilot/agents/spec-master.agent.md` — GitHub Copilot CLI's own
  personal/user-level skill directories, confirmed by inspecting a machine
  with Copilot CLI installed (other locally-installed skills already live
  there, in exactly this two-file pattern: a `SKILL.md` under
  `~/.copilot/skills/<name>/` and a matching `~/.copilot/agents/<name>.agent.md`
  with `description`/`tools`/`user-invocable` frontmatter). Once installed
  globally, `/spec-master <context-file>` works in every Copilot CLI project
  on the machine without a per-repo copy.

Mapping to the core:

- The entrypoint is intentionally short: it points at
  [`../PROTOCOL.md`](../PROTOCOL.md) (the canonical protocol, shared with
  every adapter) and repeats only what's Copilot-specific — how the
  context-file argument is resolved from the invocation, and that ordinary
  chat turn-taking replaces `AskUserQuestion` for every gate (still batching
  every `clarify` question into one message, per §21 of the original spec).
- All structural decisions go through the same
  `python3 spec-master/lib/cli.py ...` calls as every other adapter — the
  core is plain Python 3 stdlib with no Claude-specific dependency, so it
  runs unchanged under Copilot's shell/terminal tool.
- Executing an actual Spec Kit phase means reading the installed
  `.github/skills/speckit-<phase>/SKILL.md` (Copilot's default Spec Kit
  layout) and following it with the prompt generated from
  [`../templates/prompts/<phase>.md`](../templates/prompts) — Copilot has no
  native "invoke this other skill" primitive, so the adapter inlines the
  target skill's own protocol instead of trying to call it.
- Templates and the deterministic core are **not duplicated** under
  `.github/` — the Copilot entrypoint reads them from this neutral
  `spec-master/` package directly, since that's just a repo-relative path
  any agent with file access can read regardless of which platform
  installed it.

## Resuming

Re-invoking the skill with the same context-file argument follows the exact
same Step 0 (state show + fingerprint compare) described in
`../PROTOCOL.md` — no Copilot-specific resume logic exists or is needed.
