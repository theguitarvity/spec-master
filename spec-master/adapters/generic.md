# Generic adapter — every other agent Spec Kit supports

Claude Code, GitHub Copilot, OpenAI Codex CLI, and Qwen each have a
hand-written adapter (`claude-code.md`, `copilot.md`, `codex.md`, `qwen.md`)
because they warrant deeper, tool-specific mechanics (e.g. `AskUserQuestion`,
Copilot's dual skills/commands layout, Codex's `$speckit-<phase>` invocation
style). Every **other** agent [GitHub Spec Kit](https://github.com/github/spec-kit)
supports gets a *generated* entrypoint instead — same protocol, same core,
same stopping conditions, rendered into that agent's own install location
and file format.

## Why generated, not hand-written

Spec Kit supports 30+ coding agents (`specify integration list`). Hand-writing
and maintaining one bespoke `adapters/<agent>.md` per agent would drift out of
sync with Spec Kit's own integration registry the moment it adds, renames, or
reconfigures one. Instead:

- [`spec-master/lib/adapters_gen.py`](../lib/adapters_gen.py) holds a single
  table — one row per agent — transcribed from Spec Kit's own
  `specify_cli/integrations/*/__init__.py` (`registrar_config`: install
  directory, file layout, extension) and `specify_cli/_invocation_style.py`
  (chat invocation prefix: `/`, `$`, or `/skill:`).
- Running it renders every agent's real entrypoint file, in that agent's own
  format (Markdown `SKILL.md`, Markdown command, TOML, or YAML recipe) —
  content equivalent to the hand-written adapters, just generated instead of
  copy-pasted 30 times.
- When Spec Kit changes an agent's directory or invocation style, update one
  row in that table and re-run the generator — not 30 files by hand.

## What every generated file says

Regardless of format, each generated entrypoint carries the same four points
the bespoke adapters do:

1. **Argument resolution** — the context-file path comes from that agent's
   own argument-passing convention (`$ARGUMENTS`, `{{args}}`, or
   `{{parameters}}`, per that agent's actual template substitution token),
   resolved relative to the project, never the engine.
2. **Deterministic core** — every structural decision goes through
   `python3 spec-master/lib/cli.py <command> ...`, never reimplemented in
   prose.
3. **Asking the user** — that agent's own normal turn-taking replaces
   `AskUserQuestion`, still batching every `clarify` question into one
   message and asking the Git Flow vs Trunk-Based question exactly once.
4. **Invoking a real Spec Kit phase** — read the `speckit-<phase>`
   command/skill Spec Kit itself installed in that agent's own directory and
   follow it with the prompt generated from
   `spec-master/templates/prompts/<phase>.md`.

## Regenerating

```bash
# List every agent in the table (key, dir, layout, invocation prefix):
python3 spec-master/lib/adapters_gen.py list

# (Re)write every generated agent's entrypoint into a project, pointing at a
# local/vendored spec-master/ copy:
python3 spec-master/lib/adapters_gen.py generate --root . --engine-ref spec-master

# ...or at a globally-mirrored engine (what `init.sh link` does):
python3 spec-master/lib/adapters_gen.py generate --root <project> --engine-ref ~/.spec-master-engine

# Regenerate just one agent:
python3 spec-master/lib/adapters_gen.py generate --root . --engine-ref spec-master --only gemini
```

The generator never writes into a directory owned by a bespoke adapter
(`.claude/`, `.github/skills`, `.agents/skills`, `.qwen/commands` —
see `BESPOKE_DIRS` in `adapters_gen.py`), and never writes outside the
target `--root` unless `--home` is passed explicitly (needed only for
Hermes, which Spec Kit installs to `~/.hermes/skills` unconditionally).

## Caveats worth knowing before relying on one of these

- **Kiro CLI** does not substitute `$ARGUMENTS` in file-based prompts
  ([github/spec-kit#1926](https://github.com/github/spec-kit/issues/1926)) —
  its generated file says so and tells the user to pass the context-file
  path in the chat message itself.
- **Goose** (`.goose/recipes/spec-master.yaml`) is a recipe, run with
  `goose run`, not a typed slash command.
- **Cline** and **Firebender** are IDE-based; their file is picked from a
  workflow/command list inside the IDE rather than typed.
- **Hermes** always installs skills globally (`~/.hermes/skills`), never
  per-project — pass `--home` to the generator (or run `init.sh`, once it
  gains a Hermes global step) to materialize it.
