# Discovery Report

Data: 2026-08-17

## Repositório

- `spec-master` (este próprio repositório) — motor de orquestração do
  GitHub Spec Kit, Python 3 stdlib, zero dependências.
- Linguagem/framework: Python (CLI, `lib/`), Bash (`init.sh`).
- CI: não detectada (`ci_present: false`).
- Git: repositório git válido, branch `main`.

## Spec Kit

- `spec_kit_present`: `false` no início do run → inicializado nesta sessão
  com `specify init --here --integration claude --script sh --force`.
- Integração instalada: Claude Code, via **Skills** (não commands):
  `.claude/skills/speckit-constitution`, `speckit-specify`,
  `speckit-clarify`, `speckit-plan`, `speckit-tasks`, `speckit-analyze`,
  `speckit-implement`, `speckit-checklist`, `speckit-converge`,
  `speckit-taskstoissues`.
- `constitution_present`: `true` (template padrão copiado por
  `specify init`, ainda com placeholders — a preencher na fase
  `constitution`).
- `specs_dir_present`: `false` — nenhuma feature spec existente ainda.
- Nota de compatibilidade: a versão instalada do Spec Kit usa Skills com
  nomes em kebab-case (`speckit-<fase>`), não commands em dot-case
  (`speckit.<fase>`) como o `PROTOCOL.md` assume como exemplo para Claude
  Code. As fases deste workflow serão executadas invocando a Skill
  correspondente (ex.: `speckit-constitution`) via `Skill` tool.

## Documentação existente

- `README.md` presente (documenta o próprio Spec Master).
- `docs/spec-master/guarded-mode-spec.md` — contexto desta execução:
  especificação de um modo de execução "guarded" (controlador
  determinístico de fases para modelos locais menos robustos), com modos
  `native | guarded | auto`.
- Sem `CLAUDE.md`/`AGENTS.md` na raiz (o `CLAUDE.md` do protocolo do Spec
  Master vive no motor global, não neste repositório-alvo).

## Código relevante já presente (pré-existente a este workflow)

- `spec-master/lib/discovery.py`: já modificado (não commitado) para
  descobrir comandos `speckit.*` em `.claude/commands`, `.opencode/commands`
  e `.qwen/commands`, e expor `speckit_command_paths` por integração.
- `spec-master/lib/opencode_runner.py` (novo, não commitado, 191 linhas) +
  `spec-master/tests/test_opencode_runner.py` (novo, 53 linhas): runner
  inicial para invocar `opencode run` — infraestrutura prévia relevante
  para o requisito GM-012 (adaptador OpenCode) da spec guarded-mode.
- `init.sh`: já modificado (não commitado) para instalar um entrypoint
  global do Spec Master para OpenCode (`~/.config/opencode/commands`).
- Não existem ainda: `controller.py`, `execution_mode.py`,
  `phase_contracts.py`, `phase_runner.py` (estrutura sugerida na §18 da
  spec guarded-mode) — este é o trabalho principal desta feature.

## Estratégia de Git

- Definida pelo usuário: **Trunk-Based Development**. Nenhuma branch de
  feature será criada; o trabalho ocorre em `main`, com a feature separada
  logicamente em `specs/<feature>/`.

## Quality gates candidatos (a confirmar na fase de gates)

- `python3 -m unittest discover -s spec-master/tests -v` (suíte existente,
  citada explicitamente como critério de aceite na spec guarded-mode).
