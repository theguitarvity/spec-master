# Project Goals

## Purpose

Tornar o Spec Master (este repositório) mais completo e robusto frente ao
estado atual do mercado de spec-driven development, fechando gaps que o
próprio projeto já reconhece no seu roadmap (`README.md`) e nas suas
"Limitations (this increment)" (`docs/spec-master/README.md`).

## Business / Product Context

Spec Master é um orquestrador agentic, construído sobre o GitHub Spec Kit,
com núcleo determinístico Python zero-dependência. Um benchmark competitivo
contra GitHub Spec Kit, BMAD-METHOD, AWS Kiro, OpenSpec, Spec Kitty, Tessl e
GSD identificou 10 melhorias priorizadas (ver
`docs/market-benchmark-roadmap.md`), organizadas em Tier 1 (alta
prioridade, alinhadas ao roadmap já declarado) e Tier 2 (prioridade média).

## Problem Statement

O roadmap atual do Spec Master lista paralelização real, execução real dos
workstreams do Team Mode, integrações de tracker e dashboard/MCP como
trabalho futuro ainda não construído; o mercado já validou soluções para a
maioria desses gaps (worktrees nativos, extensões de tracker do próprio
Spec Kit, dashboards locais), tornando essas features implementáveis agora
com baixo risco arquitetural.

## Desired Outcome

As 10 features do Tier 1/Tier 2 implementadas, testadas
deterministicamente (sem depender de LLM para a lógica estrutural), e
integradas ao core existente sem reimplementar nenhum comando `speckit.*`.

## Target Scope

Pacote `spec-master/` deste repositório (core Python, templates, knowledge
base, protocolo). Fora de escopo: qualquer produto/projeto de terceiros.

## Delivery Approach

Workflow `trunk`-based (conforme já usado neste repositório), uma feature
por vez seguindo `specify -> clarify -> plan -> tasks -> analyze ->
implement -> validate`, na ordem de dependência resolvida por `features
order`. Item 1 do Tier 1 (`parallel-worktree-execution`) é pré-requisito
direto do item 2 (`team-mode-parallel-workstreams`).

## What "Done" Means

1. Cada feature aprovada tem spec, plano, tasks, análise sem findings
   bloqueantes, implementação e validação `PASSED`.
2. Toda nova lógica estrutural vive no core determinístico
   (`spec-master/lib/`) e é testável sem LLM.
3. Nenhuma capacidade já oferecida pelo GitHub Spec Kit (extensões de
   tracker, comandos `speckit.*`) é reimplementada.

## Success Criteria

- Testes determinísticos novos passam junto com a suíte existente
  (`python3 -m unittest discover -s spec-master/tests`).
- `graph validate` e os harness evals (`evals run`) passam ao final.
- Rastreabilidade completa entre os itens do benchmark e a implementação
  final.

## Constraints

- Núcleo determinístico permanece Python stdlib puro, sem novas
  dependências externas obrigatórias (uma exceção documentada é aceitável
  apenas se o protocolo MCP da Feature 6 exigir, e deve ficar isolada,
  nunca no caminho crítico do core).
- Nenhum comando de build/test/lint/security hardcoded.
- Compatibilidade retroativa com o estado já `COMPLETED` das features
  `guarded-mode-controller` e `guarded-noop-phase-validation` (código já
  implementado por elas não deve ser quebrado).

## Governance

- Constitution existente em `.specify/memory/constitution.md` é a fonte de
  princípios ratificados; qualquer `CONFLICT`/`REMOVAL_CANDIDATE` detectado
  por `constitution diff` pausa o workflow para decisão do usuário.

## Risks

- Escopo grande (10 features): risco de exceder o budget de uma única
  sessão — mitigado executando na ordem de prioridade (Tier 1 primeiro) e
  parando de forma transparente em `PARTIAL` se necessário, nunca
  simulando conclusão.
- `parallel-worktree-execution` introduz complexidade de merge — mitigado
  por reportar conflitos em vez de resolvê-los automaticamente.

## Stakeholders

- Victor Silva (victor.silva@telefonica.com) — solicitante, mantenedor do
  projeto.

## Non-goals

- Modelo "spec-as-source" (Tessl) — ver `app-features.md`.
- Itens de Tier 3 do benchmark (EARS, export OpenTelemetry, web bundle) —
  registrados como backlog futuro, não implementados neste workflow.

## Stopping Conditions

O workflow deve ser considerado concluído quando:

- Todas as 10 features atingirem `validate: PASSED`, ou
- O relatório final classificar como `PARTIAL`/`BLOCKED` com justificativa
  clara por feature não concluída.

## Source Traceability

| Goal / Constraint | Source | Classification |
|---|---|---|
| 10 features priorizadas em Tier 1/Tier 2 | docs/market-benchmark-roadmap.md | EXPLICIT |
| Backlog Tier 3 e exclusão do modelo Tessl | docs/market-benchmark-roadmap.md | EXPLICIT |
| Núcleo determinístico zero-dependência | DISCOVERED_FROM_CODEBASE (spec-master/lib/, docs/spec-master/README.md) | DISCOVERED_FROM_CODEBASE |
| Workflow trunk-based | DISCOVERED_FROM_CODEBASE (.spec-master/state.json anterior) | DISCOVERED_FROM_CODEBASE |
