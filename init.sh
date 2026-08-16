#!/usr/bin/env bash
# Spec Master — global installer.
#
# 1. Mirrors this repo's spec-master/ engine (protocol + deterministic core +
#    templates) into ~/.spec-master-engine, so every project on this machine
#    can use it without vendoring a copy.
# 2. Registers GLOBAL entrypoints for the documented adapters, each agent's own
#    documented personal/user-level skill directory:
#      - Claude Code:  ~/.claude/commands, ~/.claude/skills
#      - GitHub Copilot CLI: ~/.copilot/skills, ~/.copilot/agents (*.agent.md)
#      - OpenAI Codex CLI:   ~/.codex/skills
#      - Hermes: ~/.hermes/skills (the one other agent Spec Kit itself only
#        ever installs globally — see spec-master/lib/adapters_gen.py)
#      - shared fallback (both Copilot CLI and Codex CLI also scan this):
#        ~/.agents/skills
#    /spec-master (or $spec-master, or @spec-master, depending on the agent)
#    becomes available in every project on this machine automatically, the
#    same way any other user-level skill does for each tool.
# 3. `link` additionally generates lightweight PROJECT-level pointer files
#    for Copilot/Codex under the target repo (`.github/skills/`,
#    `.agents/skills/`) — useful for teammates who haven't run init.sh
#    themselves, or when the skill should be committed to a repo — PLUS every
#    other agent GitHub Spec Kit supports (Gemini, Cursor, Bob, Trae, Goose,
#    Kilo Code, ~25 more), generated from the table in
#    spec-master/lib/adapters_gen.py so it stays in sync with Spec Kit's own
#    integration registry instead of being hand-maintained per agent.
# 4. Checks whether the target project already has Spec Kit initialized
#    (.specify/) and, if not, offers to run `specify init --here` now.
#
# Usage:
#   ./init.sh                      install engine + all global entrypoints,
#                                   then run the project steps against $PWD
#   ./init.sh --project <path>     same, but target <path> instead of $PWD
#   ./init.sh --engine-only        only (re)install the global engine +
#                                   entrypoints, skip project steps
#   ./init.sh link [path]          only run the project steps (Copilot/Codex
#                                   per-project pointers + Spec Kit check)
#                                   against [path] or $PWD, without touching
#                                   the global engine
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
ENGINE_SRC="$SCRIPT_DIR/spec-master"
ENGINE_DST="$HOME/.spec-master-engine"
MARKER_FILE="$ENGINE_DST/.managed-by-spec-master-init"

CLAUDE_COMMANDS_DIR="$HOME/.claude/commands"
CLAUDE_SKILLS_DIR="$HOME/.claude/skills/spec-master"
COPILOT_SKILLS_DIR="$HOME/.copilot/skills/spec-master"
COPILOT_AGENTS_DIR="$HOME/.copilot/agents"
CODEX_SKILLS_DIR="$HOME/.codex/skills/spec-master"
AGENTS_SHARED_SKILLS_DIR="$HOME/.agents/skills/spec-master"

log()  { printf '[spec-master init] %s\n' "$1"; }
warn() { printf '[spec-master init] WARNING: %s\n' "$1" >&2; }
die()  { printf '[spec-master init] ERROR: %s\n' "$1" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Step 1 — mirror the engine to ~/.spec-master-engine
# ---------------------------------------------------------------------------
install_engine() {
  [ -f "$ENGINE_SRC/PROTOCOL.md" ] || die "spec-master/PROTOCOL.md not found next to this script ($SCRIPT_DIR). Run init.sh from the ai-sdd-master-skill repo root."

  if [ -d "$ENGINE_DST" ] && [ ! -f "$MARKER_FILE" ]; then
    warn "$ENGINE_DST already exists and wasn't created by this script."
    read -r -p "  Overwrite it with the Spec Master engine anyway? [y/N] " reply || reply="n"
    case "$reply" in
      [yY]|[yY][eE][sS]) ;;
      *) die "aborted — remove or rename $ENGINE_DST and re-run." ;;
    esac
  fi

  mkdir -p "$ENGINE_DST"
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete --exclude ".managed-by-spec-master-init" "$ENGINE_SRC"/ "$ENGINE_DST"/
  else
    rm -rf "${ENGINE_DST:?}"/*
    cp -a "$ENGINE_SRC"/. "$ENGINE_DST"/
  fi
  printf 'installed from %s on %s\n' "$SCRIPT_DIR" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$MARKER_FILE"
  log "engine mirrored to $ENGINE_DST"
}

# ---------------------------------------------------------------------------
# Step 2 — global Claude Code entrypoint (~/.claude/commands, ~/.claude/skills)
# ---------------------------------------------------------------------------
install_claude_global() {
  mkdir -p "$CLAUDE_COMMANDS_DIR" "$CLAUDE_SKILLS_DIR"

  cat > "$CLAUDE_COMMANDS_DIR/spec-master.md" <<EOF
---
description: "Orquestrar autonomamente todo o workflow do Spec Kit (constitution -> specify -> clarify -> plan -> tasks -> analyze -> implement) a partir de um único arquivo de contexto"
---

Você é o **Spec Master**: um orquestrador agentic baseado em estados que
converte um documento de contexto humano em constitution, specs, planos,
tasks e implementação validada via GitHub Spec Kit, com o mínimo de
interação manual possível.

Este comando é instalado **globalmente** (\`~/.claude/commands/spec-master.md\`,
gerado por \`init.sh\`) e funciona em qualquer projeto Claude Code desta
máquina — não depende de nenhum arquivo local do projeto atual.

O protocolo completo, model-agnostic, está em:

    $ENGINE_DST/PROTOCOL.md

**Leia e siga esse arquivo integralmente antes de fazer qualquer outra
coisa.** Este comando existe apenas para amarrar as mecânicas específicas do
Claude Code:

1. **Argumento**: \`\$ARGUMENTS\` é o caminho do arquivo de contexto (ex.:
   \`CLAUDE.md\`, \`docs/architecture-context.md\`), resolvido relativo ao
   diretório do projeto atual (\$PWD), não ao engine. Se vazio ou o arquivo
   não existir, pare e explique o uso: \`/spec-master <context-file>\`.
2. **Core determinístico**: toda decisão estrutural é delegada ao core
   Python via \`Bash\`:
   \`python3 $ENGINE_DST/lib/cli.py <comando> ...\`
   Nunca reimplemente essa lógica em prosa — chame o CLI e aja sobre o JSON
   retornado.
3. **Perguntas ao usuário**: use \`AskUserQuestion\` exatamente nos gates
   descritos no PROTOCOL.md (Spec Kit não inicializado + estratégia Git,
   batched em uma única chamada; ambiguidades \`USER_DECISION_REQUIRED\`
   agrupadas; conflitos de constitution; resume vs restart).

Templates ficam em \`$ENGINE_DST/templates/\`. Execute agora, em ordem, os
passos descritos em \`$ENGINE_DST/PROTOCOL.md\`, contra o projeto onde este
comando foi invocado (\$PWD) — nunca contra o próprio diretório do engine.
EOF

  cat > "$CLAUDE_SKILLS_DIR/SKILL.md" <<EOF
---
name: spec-master
description: Orquestrar autonomamente todo o workflow do Spec Kit (constitution -> specify -> clarify -> plan -> tasks -> analyze -> implement) a partir de um único arquivo de contexto.
---

# Spec Master (global Claude Code skill pointer)

Installed globally by \`init.sh\` so Claude Code's skill auto-discovery
finds Spec Master in every project on this machine. The real entrypoint is
the global slash command at \`~/.claude/commands/spec-master.md\`
(\`/spec-master <context-file>\`).

Protocol, core, and templates all live in the engine mirror, not here:

    $ENGINE_DST/PROTOCOL.md
    $ENGINE_DST/lib/cli.py
    $ENGINE_DST/templates/

Read \`$ENGINE_DST/PROTOCOL.md\` in full before acting.
EOF

  log "Claude Code entrypoint installed globally:"
  log "  $CLAUDE_COMMANDS_DIR/spec-master.md"
  log "  $CLAUDE_SKILLS_DIR/SKILL.md"
}

# ---------------------------------------------------------------------------
# Step 3 — global GitHub Copilot CLI entrypoint
# Copilot CLI reads personal skills from ~/.copilot/skills/<name>/SKILL.md;
# on this family of setups it also picks up ~/.copilot/agents/<name>.agent.md
# (the format already used by other locally-installed agents), so both are
# written for maximum compatibility across Copilot CLI versions.
# ---------------------------------------------------------------------------
install_copilot_global() {
  mkdir -p "$COPILOT_SKILLS_DIR" "$COPILOT_AGENTS_DIR"

  cat > "$COPILOT_SKILLS_DIR/SKILL.md" <<EOF
---
name: spec-master
description: Orquestrar autonomamente todo o workflow do Spec Kit (constitution -> specify -> clarify -> plan -> tasks -> analyze -> implement) a partir de um único arquivo de contexto.
---

# Spec Master (global GitHub Copilot CLI skill pointer)

Installed globally by \`init.sh\` (\`~/.copilot/skills/spec-master/SKILL.md\`)
so Copilot CLI finds Spec Master in every project on this machine, the same
way any other personal skill does.

Protocol, core, and templates all live in the engine mirror, not here:

    $ENGINE_DST/PROTOCOL.md   # protocol — read and follow in full
    $ENGINE_DST/lib/cli.py    # deterministic core CLI
    $ENGINE_DST/templates/    # normalized-doc + per-phase prompt templates

Argument: the context-file path is whatever the user typed after invoking
this skill (e.g. \`/spec-master CLAUDE.md\`), resolved relative to the
current project, not the engine. Ask via normal chat turn-taking in place of
\`AskUserQuestion\`, batching every \`USER_DECISION_REQUIRED\` item into one
message. Read \`$ENGINE_DST/PROTOCOL.md\` in full before acting.
EOF

  cat > "$COPILOT_AGENTS_DIR/spec-master.agent.md" <<EOF
---
description: "Orquestrar autonomamente todo o workflow do Spec Kit (constitution -> specify -> clarify -> plan -> tasks -> analyze -> implement) a partir de um único arquivo de contexto. Instalado globalmente por init.sh."
tools: ["codebase", "editFiles", "runCommands", "new", "changes"]
user-invocable: true
---

# @spec-master — Orquestrador Spec Kit

Você é o **Spec Master**: um orquestrador agentic baseado em estados que
converte um documento de contexto humano em constitution, specs, planos,
tasks e implementação validada via GitHub Spec Kit, com o mínimo de
interação manual possível.

**Fonte única de verdade**: \`$ENGINE_DST/PROTOCOL.md\`. Leia-o por inteiro
antes de qualquer ação — este arquivo é apenas o ponto de invocação global
para o Copilot; todo o protocolo (discovery, normalização de contexto,
constitution, workflow por feature, quality gates, rastreabilidade) vive lá
e pode evoluir. Nunca duplique aquele conteúdo aqui.

1. **Argumento**: o caminho do arquivo de contexto é o que o usuário digitou
   ao invocar (\`/spec-master CLAUDE.md\`), resolvido relativo ao projeto
   atual — nunca ao diretório do engine.
2. **Core determinístico**: \`python3 $ENGINE_DST/lib/cli.py <comando> ...\`
   para toda decisão estrutural — nunca reimplemente essa lógica em prosa.
3. **Perguntas ao usuário**: use turnos normais de chat no lugar de
   \`AskUserQuestion\`, agrupando toda ambiguidade \`USER_DECISION_REQUIRED\`
   numa única mensagem, e a checagem de Spec Kit + estratégia de Git numa
   única pergunta batched, conforme o PROTOCOL.md.
EOF

  log "GitHub Copilot CLI entrypoint installed globally:"
  log "  $COPILOT_SKILLS_DIR/SKILL.md"
  log "  $COPILOT_AGENTS_DIR/spec-master.agent.md"
}

# ---------------------------------------------------------------------------
# Step 4 — global OpenAI Codex CLI entrypoint (~/.codex/skills)
# ---------------------------------------------------------------------------
install_codex_global() {
  mkdir -p "$CODEX_SKILLS_DIR"

  cat > "$CODEX_SKILLS_DIR/SKILL.md" <<EOF
---
name: spec-master
description: Orquestrar autonomamente todo o workflow do Spec Kit (constitution -> specify -> clarify -> plan -> tasks -> analyze -> implement) a partir de um único arquivo de contexto.
---

# Spec Master (global OpenAI Codex CLI skill pointer)

Installed globally by \`init.sh\` (\`~/.codex/skills/spec-master/SKILL.md\`)
so Codex CLI finds Spec Master in every project on this machine, invoked as
\`\$spec-master <context-file>\`.

Protocol, core, and templates all live in the engine mirror, not here:

    $ENGINE_DST/PROTOCOL.md   # protocol — read and follow in full
    $ENGINE_DST/lib/cli.py    # deterministic core CLI
    $ENGINE_DST/templates/    # normalized-doc + per-phase prompt templates

Argument: the context-file path is whatever follows \$spec-master in the
invocation, resolved relative to the current project, not the engine. Ask
via normal turn-taking in place of \`AskUserQuestion\`, batching every
\`USER_DECISION_REQUIRED\` item into one message. Read
\`$ENGINE_DST/PROTOCOL.md\` in full before acting.
EOF

  log "OpenAI Codex CLI entrypoint installed globally:"
  log "  $CODEX_SKILLS_DIR/SKILL.md"
}

# ---------------------------------------------------------------------------
# Step 4b — shared fallback location: both Copilot CLI and Codex CLI also
# scan ~/.agents/skills for personal skills. Cheap, additive redundancy in
# case either tool's primary directory (~/.copilot/skills, ~/.codex/skills)
# changes across versions. Never touches ~/.agents/.skill-lock.json, which
# may be owned by a different, unrelated skill-installer tool.
# ---------------------------------------------------------------------------
install_agents_shared_global() {
  mkdir -p "$AGENTS_SHARED_SKILLS_DIR"

  cat > "$AGENTS_SHARED_SKILLS_DIR/SKILL.md" <<EOF
---
name: spec-master
description: Orquestrar autonomamente todo o workflow do Spec Kit (constitution -> specify -> clarify -> plan -> tasks -> analyze -> implement) a partir de um único arquivo de contexto.
---

# Spec Master (shared global skill pointer — ~/.agents/skills)

Installed globally by \`init.sh\`. Both GitHub Copilot CLI and OpenAI Codex
CLI also scan \`~/.agents/skills\` for personal skills, in addition to their
own dedicated directories (\`~/.copilot/skills\`, \`~/.codex/skills\`) — this
file is redundant-by-design, not the primary copy.

Protocol, core, and templates all live in the engine mirror, not here:

    $ENGINE_DST/PROTOCOL.md
    $ENGINE_DST/lib/cli.py
    $ENGINE_DST/templates/

Read \`$ENGINE_DST/PROTOCOL.md\` in full before acting.
EOF

  log "shared global pointer installed:"
  log "  $AGENTS_SHARED_SKILLS_DIR/SKILL.md"
}

# ---------------------------------------------------------------------------
# Step 4c — Hermes is the one other agent Spec Kit itself only ever installs
# globally (~/.hermes/skills, never per-project) — see
# spec-master/lib/adapters_gen.py. Every other non-bespoke agent is
# per-project only (Step 5b, via 'init.sh link'), since Spec Kit has no
# documented global convention for them and guessing one would be unverified.
# ---------------------------------------------------------------------------
install_hermes_global() {
  if ! command -v python3 >/dev/null 2>&1; then
    warn "python3 not found; skipping the Hermes global entrypoint."
    return 0
  fi
  python3 "$ENGINE_DST/lib/adapters_gen.py" generate \
    --root "$ENGINE_DST" --engine-ref "$ENGINE_DST" --home "$HOME" --only hermes >/dev/null
  log "Hermes entrypoint installed globally:"
  log "  $HOME/.hermes/skills/spec-master/SKILL.md"
}

# ---------------------------------------------------------------------------
# Step 5 — per-project pointers for Copilot / Codex. Global install (above)
# already covers every project automatically; this is for teammates who
# haven't run init.sh, or repos that want the pointer committed.
# ---------------------------------------------------------------------------
link_project_agents() {
  local project_dir="$1"

  if [ "$project_dir" = "$SCRIPT_DIR" ]; then
    log "skipping per-project pointers: $project_dir is this engine's own source repo."
    log "  it already ships portable, self-contained entrypoints (.claude/, .github/, .agents/,"
    log "  .qwen/, plus the ~30 generated ones under spec-master/lib/adapters_gen.py) that"
    log "  reference spec-master/ by relative path, not the machine-local ~/.spec-master-engine"
    log "  mirror — overwriting them would break the repo for anyone else who clones it."
    log "  Run 'init.sh link <other-project>' to link a *different* project."
    return 0
  fi

  local copilot_dir="$project_dir/.github/skills/spec-master"
  local codex_dir="$project_dir/.agents/skills/spec-master"

  mkdir -p "$copilot_dir" "$codex_dir"

  cat > "$copilot_dir/SKILL.md" <<EOF
---
name: spec-master
description: Orquestrar autonomamente todo o workflow do Spec Kit (constitution -> specify -> clarify -> plan -> tasks -> analyze -> implement) a partir de um único arquivo de contexto.
---

# Spec Master (GitHub Copilot entrypoint, generated by init.sh)

Follows the \`speckit-<command>/SKILL.md\` skills-based layout Spec Kit
itself uses for Copilot. Points at the globally-installed engine — nothing
in this project directory is duplicated:

    $ENGINE_DST/PROTOCOL.md   # protocol — read and follow in full
    $ENGINE_DST/lib/cli.py    # deterministic core CLI
    $ENGINE_DST/templates/    # normalized-doc + per-phase prompt templates

Argument: the context-file path is whatever the user typed after invoking
this skill, resolved relative to this project's root. Ask via normal chat
turn-taking in place of \`AskUserQuestion\`, batching every
\`USER_DECISION_REQUIRED\` item into one message.
EOF

  cat > "$codex_dir/SKILL.md" <<EOF
---
name: spec-master
description: Orquestrar autonomamente todo o workflow do Spec Kit (constitution -> specify -> clarify -> plan -> tasks -> analyze -> implement) a partir de um único arquivo de contexto.
---

# Spec Master (OpenAI Codex CLI entrypoint, generated by init.sh)

Follows the skills-based layout Spec Kit itself uses for Codex, invoked as
\`\$spec-master <context-file>\`. Points at the globally-installed engine —
nothing in this project directory is duplicated:

    $ENGINE_DST/PROTOCOL.md   # protocol — read and follow in full
    $ENGINE_DST/lib/cli.py    # deterministic core CLI
    $ENGINE_DST/templates/    # normalized-doc + per-phase prompt templates

Argument: the context-file path is whatever follows \$spec-master in the
invocation, resolved relative to this project's root. Ask via normal
turn-taking in place of \`AskUserQuestion\`, batching every
\`USER_DECISION_REQUIRED\` item into one message.
EOF

  log "per-project pointers linked in $project_dir:"
  log "  ${copilot_dir#"$project_dir"/}/SKILL.md"
  log "  ${codex_dir#"$project_dir"/}/SKILL.md"

  link_generated_agents "$project_dir"
}

# ---------------------------------------------------------------------------
# Step 5b — every other agent Spec Kit supports (Gemini, Cursor, Bob, Trae,
# Kilo Code, Goose, ~25 more — see spec-master/lib/adapters_gen.py). Uses the
# generator so the long tail stays in sync with Spec Kit's own integration
# registry instead of ~30 hand-maintained files.
# ---------------------------------------------------------------------------
link_generated_agents() {
  local project_dir="$1"

  if ! command -v python3 >/dev/null 2>&1; then
    warn "python3 not found; skipping the generated (non-bespoke) agent entrypoints."
    return 0
  fi

  local written
  written="$(python3 "$ENGINE_DST/lib/adapters_gen.py" generate \
    --root "$project_dir" --engine-ref "$ENGINE_DST")"

  local count
  count="$(printf '%s\n' "$written" | grep -c . || true)"
  log "generated $count additional agent entrypoint(s) in $project_dir (Gemini, Cursor, Bob, ...)."
  log "  full list: python3 $ENGINE_DST/lib/adapters_gen.py list"
}

# ---------------------------------------------------------------------------
# Step 6 — Spec Kit initialization check for the target project
# ---------------------------------------------------------------------------
check_spec_kit() {
  local project_dir="$1"

  if [ "$project_dir" = "$SCRIPT_DIR" ]; then
    return 0
  fi

  if [ -d "$project_dir/.specify" ]; then
    log "Spec Kit já inicializado em $project_dir (.specify/ encontrado)."
    return 0
  fi

  warn "Spec Kit não parece estar inicializado em $project_dir (.specify/ não encontrado)."
  if ! command -v specify >/dev/null 2>&1; then
    warn "o CLI 'specify' não foi encontrado no PATH."
    if command -v uvx >/dev/null 2>&1; then
      log "você pode rodar sem instalar nada:"
      log "  cd \"$project_dir\" && uvx --from git+https://github.com/github/spec-kit.git specify init --here"
    else
      log "instale o Spec Kit primeiro: https://github.com/github/spec-kit"
    fi
    log "/spec-master vai reportar FAILED — Spec Kit unavailable até que isso seja resolvido."
    return 0
  fi

  read -r -p "  Inicializar o Spec Kit agora em $project_dir com 'specify init --here'? [y/N] " reply || reply="n"
  case "$reply" in
    [yY]|[yY][eE][sS])
      (cd "$project_dir" && specify init --here)
      log "Spec Kit inicializado."
      ;;
    *)
      log "ok, pulando. /spec-master vai reportar FAILED — Spec Kit unavailable até que isso seja resolvido."
      ;;
  esac
}

# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
MODE="install"
PROJECT_DIR="$PWD"
ENGINE_ONLY=0

while [ $# -gt 0 ]; do
  case "$1" in
    link)
      MODE="link"
      shift
      if [ $# -gt 0 ]; then PROJECT_DIR="$1"; shift; fi
      ;;
    --project)
      PROJECT_DIR="${2:?--project requires a path}"
      shift 2
      ;;
    --engine-only)
      ENGINE_ONLY=1
      shift
      ;;
    -h|--help)
      sed -n '2,26p' "$0"
      exit 0
      ;;
    *)
      die "unknown argument: $1 (see --help)"
      ;;
  esac
done

PROJECT_DIR="$(cd -- "$PROJECT_DIR" &>/dev/null && pwd)" || die "project path not found: $PROJECT_DIR"

if [ "$MODE" = "install" ]; then
  install_engine
  install_claude_global
  install_copilot_global
  install_codex_global
  install_agents_shared_global
  install_hermes_global
  [ "$ENGINE_ONLY" -eq 1 ] && { log "done (--engine-only, project steps skipped)."; exit 0; }
fi

link_project_agents "$PROJECT_DIR"
check_spec_kit "$PROJECT_DIR"

log "done. In any project on this machine: '/spec-master <context-file>' works for Claude Code, GitHub Copilot CLI, and OpenAI Codex CLI (\$spec-master), plus Hermes (installed globally at ~/.hermes/skills). Qwen-compatible shells use the same core via the adapter docs, but do not have a global installer path here. Run 'init.sh link <path>' to commit per-project pointers for Copilot/Codex plus ~30 other Spec Kit agents (Gemini, Cursor, Bob, Trae, Goose, Kilo Code, ...) in a repo — see 'python3 $ENGINE_DST/lib/adapters_gen.py list' for the full set."
