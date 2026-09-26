# Tech Stack

## Architecture Overview

Núcleo determinístico Python stdlib puro (`spec-master/lib/`) exposto via
CLI (`cli.py`, JSON em stdout), orquestrado por um agente (Claude Code /
Copilot / Codex / Qwen) que segue `spec-master/PROTOCOL.md`. Camada
semântica (specify/clarify/plan/tasks/analyze/implement) delegada aos
comandos/skills nativos do GitHub Spec Kit instalado no projeto-alvo.

## Languages

- Python (stdlib, sem dependências externas obrigatórias no core) —
  `DISCOVERED_FROM_CODEBASE`, `spec-master/lib/*.py`.

## Frameworks

- Nenhum framework externo no core — módulos próprios (`state.py`,
  `feature_model.py`, `git_strategy.py`, `quality_gates.py`,
  `graph/`, `knowledge/`, `controller.py`, `phase_runner.py`, etc.).

## Runtime

- Python 3 (ambiente local: 3.14.6) — `DISCOVERED_FROM_CODEBASE`.
- Execução via `Bash` + `python3 spec-master/lib/cli.py <comando>`.

## Infrastructure

- Nenhuma infraestrutura de CI configurada neste repositório
  (`ci_present: false` na última `discovery scan`).
- Execução local; estado persistido em `.spec-master/` (git-tracked).

## Components

### spec-master/lib/ (core determinístico)

Responsibilities:

- State machine (`state.py`), fingerprint/staleness (`fingerprint.py`),
  ordenação de dependências (`feature_model.py`), git strategy
  (`git_strategy.py`), quality gates (`quality_gates.py`), diff de
  constitution (`constitution_diff.py`), rastreabilidade
  (`traceability.py`), Team Mode (`team_model.py`), execution mode/guarded
  controller (`execution_mode.py`, `controller.py`, `phase_runner.py`,
  `phase_contracts.py`, `phase_result.py`), knowledge graph (`graph/`),
  concept knowledge base (`knowledge/`), métricas (`metrics.py`), policy
  preflight (`tool_policy.py`), context budget (`context_budget.py`),
  contrato de runtime (`runtime_contract.py`), harness evals (`evals.py`),
  adapters gerados (`adapters_gen.py`), runner específico OpenCode
  (`opencode_runner.py`).

Affected areas:

- As 10 novas features (Tier 1/Tier 2) adicionam módulos/comandos novos
  neste diretório, seguindo o padrão já estabelecido — nunca reescrevendo
  módulos existentes fora do necessário.

### spec-master/tests/ (suíte determinística)

Responsibilities:

- Um arquivo de teste por módulo do core (`test_<module>.py`), sem
  dependência de LLM — `python3 -m unittest discover -s spec-master/tests`.

## Integration Points

- GitHub Spec Kit instalado no projeto-alvo (`.specify/`) — comandos
  `speckit.<phase>` executados via o layout de skills do Claude Code
  (`.claude/skills/speckit-<phase>/SKILL.md`, ver nota de discovery).
- 30+ adapters de agente (Claude Code, Copilot CLI, Codex CLI, Qwen +
  gerados) — nenhuma das novas features deve quebrar esse contrato.

## Configuration

- Nenhum arquivo de configuração externo identificado além de
  `.specify/memory/constitution.md` e `.spec-master/state.json`.

## Technical Constraints

- Core permanece Python stdlib puro; qualquer dependência nova (ex.:
  eventual servidor MCP da Feature 6) deve ficar isolada e opcional, nunca
  no caminho crítico do core existente.
- Nenhum comando de build/test/lint/security hardcoded — sempre
  auto-detectado a partir do repositório-alvo (`quality_gates.py` como
  precedente).

## Architectural Principles

- Núcleo determinístico e testável sem LLM; camada semântica delegada ao
  agente.
- Nunca reimplementar um comando `speckit.*` já existente.
- Toda proveniência de fato classificada (`EXPLICIT`/`INFERRED`/
  `DISCOVERED_FROM_CODEBASE`/`UNRESOLVED`).

## Testing Strategy

### Unit

Um `test_<module>.py` por módulo novo do core, seguindo o padrão de
`spec-master/tests/test_*.py` existente.

### Component

Cobertura de comandos CLI novos via chamada direta ao `cli.py` nos testes
(mesmo padrão dos comandos existentes).

### Integration

Cenários de ponta a ponta dentro da suíte determinística existente, sem
LLM (ex.: `test_controller.py`, `test_phase_runner.py` como precedente).

### E2E

Fora de escopo automatizado nesta rodada — validação manual via execução
real do `/spec-master` neste próprio repositório (dogfooding).

## Quality Gates

- build: não aplicável a um pacote Python stdlib puro sem etapa de build
- lint: a detectar via `gates detect` no projeto-alvo
- tests: `python3 -m unittest discover -s spec-master/tests`
- coverage: a detectar via `gates detect`
- architecture checks: `graph validate`
- security checks: novo gate SAST auto-detectado (Feature 4)

## Repository Conventions

- Specs em `specs/<NNN-feature-id>/`.
- Contexto normalizado em `.spec-master/context/`.
- Relatórios em `.spec-master/reports/`.

## CI/CD

- Não configurado neste repositório (`ci_present: false`).

## Technical Non-goals

- Adicionar dependências externas obrigatórias ao core determinístico.
- Reimplementar qualquer comando `speckit.*`.

## Open Technical Questions

- Feature 6 (servidor MCP): linguagem/runtime do servidor e se ele pode
  reutilizar o mesmo processo Python do core ou precisa de um processo
  separado — a resolver na fase `clarify` dessa feature especificamente.

## Source Traceability

| Decision / Constraint | Source | Classification |
|---|---|---|
| Core Python stdlib puro, zero dependência | DISCOVERED_FROM_CODEBASE (spec-master/lib/) | DISCOVERED_FROM_CODEBASE |
| Layout de módulos existentes (state.py, git_strategy.py, etc.) | DISCOVERED_FROM_CODEBASE | DISCOVERED_FROM_CODEBASE |
| Nenhuma dependência nova obrigatória no core | docs/market-benchmark-roadmap.md | EXPLICIT |
| CI não configurado | DISCOVERED_FROM_CODEBASE (discovery scan) | DISCOVERED_FROM_CODEBASE |
