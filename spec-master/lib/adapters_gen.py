#!/usr/bin/env python3
"""Generate thin Spec Master entrypoint files for every agent integration
that GitHub Spec Kit (https://github.com/github/spec-kit) supports.

Single source of truth for the "long tail" of agents beyond the four with
hand-written, deeply-customized adapters (Claude Code, GitHub Copilot,
OpenAI Codex CLI, Qwen — see spec-master/adapters/{claude-code,copilot,
codex,qwen}.md). Those four keep their bespoke files untouched; this module
only ever writes files for the agents listed in AGENTS below.

The table below is transcribed from Spec Kit's own integration registry
(``specify_cli/integrations/*/__init__.py`` -> ``registrar_config``) and its
invocation-style module (``specify_cli/_invocation_style.py``), as of the
spec-kit commit inspected when this generator was written. If Spec Kit adds,
renames, or reconfigures an agent, update the table here — this file is the
only place that knowledge lives.

Each row is (key, dir, layout, ext, prefix, args_placeholder, note):
  key       -- Spec Kit integration key (matches ``specify integration list``)
  dir       -- project-relative directory Spec Kit itself writes into
  layout    -- "skill" (a speckit-<name>/SKILL.md-style scaffold) or
               "command" (a single file directly under ``dir``)
  ext       -- file extension for "command" layout (ignored for "skill")
  prefix    -- how the agent's own chat surface invokes it: "/", "$",
               or "/skill:"
  args      -- the raw-body placeholder token Spec Kit substitutes with the
               command argument for this agent (mostly "$ARGUMENTS")
  note      -- caveat surfaced in the generated file and in the README table

Usage:
    python3 spec-master/lib/adapters_gen.py generate --root . --engine-ref spec-master
    python3 spec-master/lib/adapters_gen.py generate --root <project> --engine-ref /home/u/.spec-master-engine
    python3 spec-master/lib/adapters_gen.py list
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

DESCRIPTION = (
    "Orquestrar autonomamente todo o workflow do Spec Kit (constitution -> "
    "specify -> clarify -> plan -> tasks -> analyze -> implement) a partir "
    "de um unico arquivo de contexto."
)


@dataclass(frozen=True)
class Agent:
    key: str
    dir: str
    layout: str  # "skill" | "command"
    ext: str
    prefix: str  # "/" | "$" | "/skill:"
    args: str
    note: str = ""
    label: str = ""

    def display(self) -> str:
        return self.label or self.key


# Agents with bespoke, hand-written adapters — never touched by this
# generator: claude, copilot, codex, qwen. "generic" has no fixed directory
# (bring-your-own-agent) and is intentionally excluded too.
AGENTS: list[Agent] = [
    Agent("agy", ".agents/skills", "skill", "", "/", "$ARGUMENTS",
          label="Antigravity (agy)"),
    Agent("alquimia", ".alquimia/skills", "skill", "", "/", "$ARGUMENTS",
          label="Alquimia AI"),
    Agent("amp", ".agents/commands", "command", ".md", "/", "$ARGUMENTS",
          label="Amp"),
    Agent("auggie", ".augment/commands", "command", ".md", "/", "$ARGUMENTS",
          label="Auggie CLI"),
    Agent("bob", ".bob/skills", "skill", "", "/", "$ARGUMENTS",
          label="IBM Bob"),
    Agent("cline", ".clinerules/workflows", "command", ".md", "/", "$ARGUMENTS",
          note="IDE-based: picked from Cline's workflow list, not typed as a slash command.",
          label="Cline"),
    Agent("codebuddy", ".codebuddy/commands", "command", ".md", "/", "$ARGUMENTS",
          label="CodeBuddy CLI"),
    Agent("command-code", ".commandcode/skills", "skill", "", "$", "$ARGUMENTS",
          label="Command Code"),
    Agent("cursor-agent", ".cursor/skills", "skill", "", "/", "$ARGUMENTS",
          label="Cursor"),
    Agent("devin", ".devin/skills", "skill", "", "/", "$ARGUMENTS",
          label="Devin for Terminal"),
    Agent("droid", ".factory/skills", "skill", "", "/", "$ARGUMENTS",
          label="Factory Droid"),
    Agent("firebender", ".firebender/commands", "command", ".mdc", "/", "$ARGUMENTS",
          note="IDE-based agent for Android Studio / IntelliJ.",
          label="Firebender"),
    Agent("forge", ".forge/commands", "command", ".md", "/", "{{parameters}}",
          label="Forge"),
    Agent("gemini", ".gemini/commands", "command", ".toml", "/", "{{args}}",
          label="Gemini CLI"),
    Agent("goose", ".goose/recipes", "command", ".yaml", "/", "{{args}}",
          note="Recipe format, run via 'goose run' rather than a typed slash command.",
          label="Goose"),
    Agent("grok", ".grok/skills", "skill", "", "/", "$ARGUMENTS",
          label="Grok Build"),
    Agent("hermes", "~/.hermes/skills", "skill", "", "/", "$ARGUMENTS",
          note="Hermes always installs skills globally to ~/.hermes/skills, never per-project.",
          label="Hermes"),
    Agent("junie", ".junie/commands", "command", ".md", "/", "$ARGUMENTS",
          label="Junie"),
    Agent("kilocode", ".kilo/commands", "command", ".md", "/", "$ARGUMENTS",
          label="Kilo Code"),
    Agent("kimi", ".kimi-code/skills", "skill", "", "/skill:", "$ARGUMENTS",
          label="Kimi Code"),
    Agent("kiro-cli", ".kiro/prompts", "command", ".md", "/", "$ARGUMENTS",
          note=("Kiro CLI does not substitute $ARGUMENTS in file-based prompts "
                "(see github/spec-kit#1926) — type the context-file path in "
                "the chat message itself, e.g. '/spec-master' then "
                "'CLAUDE.md' on the next line, rather than relying on the "
                "placeholder."),
          label="Kiro CLI"),
    Agent("lingma", ".lingma/skills", "skill", "", "/", "$ARGUMENTS",
          label="Lingma"),
    Agent("omp", ".omp/commands", "command", ".md", "/", "$ARGUMENTS",
          label="Oh My Pi"),
    Agent("opencode", ".opencode/commands", "command", ".md", "/", "$ARGUMENTS",
          label="opencode"),
    Agent("pi", ".pi/prompts", "command", ".md", "/", "$ARGUMENTS",
          label="Pi Coding Agent"),
    Agent("qodercli", ".qoder/commands", "command", ".md", "/", "$ARGUMENTS",
          label="Qoder CLI"),
    Agent("rovodev", ".rovodev/skills", "skill", "", "/", "$ARGUMENTS",
          label="RovoDev"),
    Agent("shai", ".shai/commands", "command", ".md", "/", "$ARGUMENTS",
          label="SHAI (OVHcloud)"),
    Agent("tabnine", ".tabnine/agent/commands", "command", ".toml", "/", "{{args}}",
          label="Tabnine CLI"),
    Agent("trae", ".trae/skills", "skill", "", "/", "$ARGUMENTS",
          label="Trae"),
    Agent("vibe", ".vibe/skills", "skill", "", "/", "$ARGUMENTS",
          label="Mistral Vibe"),
    Agent("zcode", ".zcode/skills", "skill", "", "$", "$ARGUMENTS",
          label="ZCode"),
    Agent("zed", ".agents/skills", "skill", "", "/", "$ARGUMENTS",
          label="Zed"),
]

AGENTS_BY_KEY = {a.key: a for a in AGENTS}

# Directories already owned by a hand-written, bespoke adapter (claude,
# copilot, codex, qwen — see spec-master/adapters/*.md). Even though those
# four keys are excluded from AGENTS above, other agents in the table share
# the *same* directory (e.g. agy/zed also use ".agents/skills", same as
# Codex) — never write into one of these, even indirectly, or a bespoke file
# gets silently clobbered.
BESPOKE_DIRS: frozenset[str] = frozenset({
    ".claude/skills", ".claude/commands",
    ".github/skills", ".github/commands",
    ".agents/skills",
    ".qwen/commands",
})


def _invocation_example(agent: Agent) -> str:
    name = "spec-master"
    if agent.prefix == "/skill:":
        return f"/skill:{name} <context-file>"
    return f"{agent.prefix}{name} <context-file>"


def _skill_body(agent: Agent, protocol: str, cli: str, templates: str) -> str:
    invoke = _invocation_example(agent)
    note = f"\n\n> **Note:** {agent.note}" if agent.note else ""
    return f"""---
name: spec-master
description: {DESCRIPTION}
---

# Spec Master ({agent.display()} entrypoint)

Generated entrypoint for **Spec Master**, following the same
`speckit-<command>/SKILL.md` skills-based layout Spec Kit itself installs
for {agent.display()} (`{agent.dir}/<name>/SKILL.md`), invoked as
`{invoke}`.{note}

The protocol, deterministic core, and templates are **not duplicated here**
— they live in the neutral, shared `spec-master/` package:

```
{protocol}   # protocol (source of truth) — read and follow in full
{cli}    # deterministic core CLI
{templates}    # normalized-doc + per-phase prompt templates
```

Platform specifics for this entrypoint:

1. **Argument**: the context-file path is whatever follows `{invoke.split()[0]}`
   in the invocation (e.g. `{agent.prefix}spec-master CLAUDE.md`). If missing
   or the file doesn't exist, stop and explain the usage: `{invoke}`.
2. **Deterministic core**: every structural decision goes through the shared
   core via your shell tool — the path is repo-relative and works the same
   regardless of which agent invoked it: `python3 {cli} <command> ...`.
   Never re-derive state machine, fingerprint, dependency ordering, git
   strategy, quality gates, constitution diffing, or traceability logic by
   hand — call the CLI and act on the JSON it returns.
3. **Asking the user**: use this agent's normal turn-taking in place of
   `AskUserQuestion` — but still batch every `USER_DECISION_REQUIRED` item
   from `clarify` into one message (never one question per turn), and still
   ask the Git Flow vs Trunk-Based question exactly once per workflow.
4. **Running an actual Spec Kit phase**: this repository's Spec Kit
   installation (if present) exposes `speckit-<phase>` skills under
   `{agent.dir}/speckit-<phase>/SKILL.md`. Read that skill and follow it with
   the prompt generated from `{templates}/prompts/<phase>.md` as the
   effective input. If no such skill exists for a phase, treat it as
   `FAILED — Spec Kit unavailable` per the stopping conditions in
   `{protocol}`.

See `spec-master/adapters/generic.md` for the shared rationale behind every
generated (non-bespoke) adapter, and this file's header in
`spec-master/lib/adapters_gen.py` for how it was produced.

## Resuming

Re-invoking `{invoke}` follows the exact same Step 0 (state show + fingerprint
compare) described in `{protocol}` — no agent-specific resume logic exists or
is needed.
"""


def _command_body_markdown(agent: Agent, protocol: str, cli: str, templates: str) -> str:
    invoke = _invocation_example(agent)
    note = f"\n\n> **Note:** {agent.note}" if agent.note else ""
    return f"""---
description: "{DESCRIPTION}"
---

<!-- Generated entrypoint for {agent.display()} — see spec-master/adapters/generic.md -->

Voce e o **Spec Master**: um orquestrador agentic baseado em estados que
converte um documento de contexto humano em constitution, specs, planos,
tasks e implementacao validada via GitHub Spec Kit, com o minimo de
interacao manual possivel.{note}

O protocolo completo, model-agnostic, esta em `{protocol}` — **leia e siga
esse arquivo integralmente antes de fazer qualquer outra coisa**. Este
arquivo existe apenas para amarrar as mecanicas especificas de
{agent.display()}:

1. **Argumento**: `{agent.args}` e o caminho do arquivo de contexto (ex.:
   `CLAUDE.md`, `docs/architecture-context.md`). Se vazio ou o arquivo nao
   existir, pare e explique o uso: `{invoke}`.
2. **Core deterministico**: toda decisao estrutural e delegada ao core
   Python via shell: `python3 {cli} <comando> ...`. Nunca reimplemente essa
   logica em prosa — chame o CLI e aja sobre o JSON retornado.
3. **Perguntas ao usuario**: use o turno normal de conversa desta ferramenta
   no lugar de `AskUserQuestion`, agrupando toda ambiguidade
   `USER_DECISION_REQUIRED` numa unica mensagem, e a checagem de Spec Kit +
   estrategia de Git numa unica pergunta batched.
4. **Executando uma fase real do Spec Kit**: leia o comando/skill
   `speckit-<fase>` que o Spec Kit instalou em `{agent.dir}/` para este
   agente e siga-o com o prompt gerado a partir de
   `{templates}/prompts/<fase>.md` como entrada efetiva. Se a fase nao
   existir, trate como `FAILED — Spec Kit unavailable` (ver `{protocol}`).

Execute agora, em ordem, os passos do `{protocol}`.
"""


def _command_body_toml(agent: Agent, protocol: str, cli: str, templates: str) -> str:
    body = _command_body_markdown(agent, protocol, cli, templates)
    body = body.split("---\n", 2)[-1]  # drop the yaml frontmatter block
    prompt = body.replace('"""', "'''")
    return (
        f'description = "{DESCRIPTION}"\n\n'
        f"# Generated entrypoint for {agent.display()} — see spec-master/adapters/generic.md\n\n"
        f'prompt = """\n{prompt}\n"""\n'
    )


def _command_body_yaml(agent: Agent, protocol: str, cli: str, templates: str) -> str:
    instructions = _command_body_markdown(agent, protocol, cli, templates)
    instructions = instructions.split("---\n", 2)[-1]
    indented = "\n".join(f"  {line}" if line else "" for line in instructions.splitlines())
    return (
        f"title: Spec Master\n"
        f"description: {DESCRIPTION}\n"
        f"# Generated entrypoint for {agent.display()} — see spec-master/adapters/generic.md\n"
        f"instructions: |\n{indented}\n"
    )


def render_files(agent: Agent, protocol: str, cli: str, templates: str) -> dict[str, str]:
    """Return {relative_path: content} for this agent, relative to its root."""
    if agent.layout == "skill":
        content = _skill_body(agent, protocol, cli, templates)
        return {f"{agent.dir}/spec-master/SKILL.md": content}

    if agent.ext == ".toml":
        content = _command_body_toml(agent, protocol, cli, templates)
    elif agent.ext == ".yaml":
        content = _command_body_yaml(agent, protocol, cli, templates)
    else:
        content = _command_body_markdown(agent, protocol, cli, templates)
    return {f"{agent.dir}/spec-master{agent.ext}": content}


def generate(
    root: Path,
    engine_ref: str,
    only: list[str] | None,
    home: Path | None,
) -> list[Path]:
    """Write every agent's entrypoint file(s) under *root*.

    Agents whose ``dir`` starts with ``~`` (currently only Hermes) are
    user-level-only in Spec Kit itself and are skipped unless *home* is
    explicitly passed — this generator defaults to *never* touching a real
    home directory when only ``--root`` is given, so a plain repo-generation
    run cannot write outside the target project by surprise. Pass
    ``--home`` explicitly (e.g. from ``init.sh``'s global-install path) to
    also materialize those.
    """
    engine_root = engine_ref  # repo-relative ("spec-master") or absolute path

    protocol = f"{engine_root}/PROTOCOL.md"
    cli = f"{engine_root}/lib/cli.py"
    templates = f"{engine_root}/templates"

    written: list[Path] = []
    seen_dirs: set[str] = set()
    agents = [AGENTS_BY_KEY[k] for k in only] if only else AGENTS
    for agent in agents:
        if agent.dir in BESPOKE_DIRS:
            # Owned by a hand-written adapter (see BESPOKE_DIRS docstring) —
            # never overwrite it from the generic table.
            continue
        if agent.dir.startswith("~"):
            if home is None:
                continue
            base = home
        else:
            base = root
        dir_key = agent.dir[2:] if agent.dir.startswith("~/") else agent.dir
        if agent.layout == "skill" and dir_key in seen_dirs:
            # Shared directory (e.g. .agents/skills used by agy/codex/zed) —
            # the file is already there for a previous agent in this run.
            continue
        seen_dirs.add(dir_key)

        for rel, content in render_files(agent, protocol, cli, templates).items():
            rel_path = rel[2:] if rel.startswith("~/") else rel
            dest = base / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
            written.append(dest)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    gen = sub.add_parser("generate", help="Write entrypoint files for every generated agent")
    gen.add_argument("--root", required=True, type=Path, help="Target project root")
    gen.add_argument("--home", type=Path, default=None,
                      help="Home dir for ~-rooted agents (e.g. Hermes). Omit to skip "
                           "them entirely — never defaults to the real $HOME.")
    gen.add_argument("--engine-ref", required=True,
                      help="'spec-master' for a vendored/local copy, or an absolute path "
                           "to the engine mirror (e.g. ~/.spec-master-engine)")
    gen.add_argument("--only", nargs="*", help="Restrict to these agent keys")

    lst = sub.add_parser("list", help="List every generated agent key")

    args = parser.parse_args(argv)

    if args.cmd == "list":
        for a in AGENTS:
            print(f"{a.key}\t{a.dir}\t{a.layout}{a.ext}\t{a.prefix}\t{a.display()}")
        return 0

    if args.cmd == "generate":
        root = args.root.resolve()
        written = generate(root, args.engine_ref, args.only, args.home)
        for p in written:
            print(p)
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
