# Project Goals

## Purpose

Oferecer um controlador determinístico opcional para o Spec Master que
mantenha modelos locais menores ou menos confiáveis restritos a uma fase
por execução, porque hoje o fluxo agentic delega a condução semântica e
operacional inteira ao modelo, e modelos menos robustos podem implementar
cedo demais, ignorar comandos `speckit.*`, simular chamadas de ferramenta
como texto, reentrar no skill, escrever em caminhos errados, declarar
sucesso falso, perder a fase atual após compactação, ou travar sem
progresso.

## Business / Product Context

Ver `[[app-features]]`: repositório é o próprio motor Spec Master
(`ai-sdd-master-skill`), que orquestra o GitHub Spec Kit para qualquer
projeto-alvo. Esta feature estende o próprio motor, não um projeto
consumidor dele.

## Problem Statement

Modelos robustos conseguem manter a fase atual, chamar ferramentas reais e
atualizar o estado; modelos menores frequentemente não conseguem. Sem um
controlador externo, não há garantia determinística de que uma fase só é
promovida quando de fato produziu o artefato exigido, com o conteúdo
mínimo esperado.

## Desired Outcome

Três modos de execução disponíveis (`native`, `guarded`, `auto`, com `auto`
como padrão), em que `guarded` isola cada fase em sessão própria e só
promove estado após validar artefatos, e `auto` decide automaticamente e de
forma irreversível quando degradar de `native` para `guarded` dentro do
mesmo workflow.

## Target Scope

Ver `## Escopo` — Incluído / Fora do escopo em
`docs/spec-master/guarded-mode-spec.md` §3, reproduzido em
`[[app-features]]`. Primeiro incremento suporta apenas a integração
OpenCode; a arquitetura não deve impedir adaptadores futuros.

## Delivery Approach

Trunk-based: trabalho direto em `main`, feature isolada logicamente em
`specs/<feature>/` (decisão do usuário nesta execução, sem branch
dedicada). Implementação seguirá a estrutura sugerida em
`docs/spec-master/guarded-mode-spec.md` §18
(`controller.py`, `execution_mode.py`, `phase_contracts.py`,
`phase_runner.py`, `opencode_runner.py` — este último já presente) e a
migração faseada descrita em §19: preservar `native` como está, incorporar
o runner OpenCode existente ao novo contrato de fases, adicionar `guarded`
sem mudar o padrão inicialmente, validar com agentes falsos e com
`qwen-todo-api`, só então trocar o padrão para `auto`, e por fim atualizar
README/adapters/instalador global.

## What "Done" Means

1. Os três modos estão disponíveis e `--mode auto` é aceito como padrão
   quando `--mode` não é informado.
2. O controlador protegido nunca promove uma fase para `PASSED` sem
   validação real do artefato obrigatório.
3. A retomada funciona de forma idempotente, sem repetir fases já `PASSED`
   com fingerprint válido.
4. Todos os testes determinísticos (`python3 -m unittest discover -s
   spec-master/tests -v`) passam, incluindo os novos casos unitários e de
   integração com agente falso.
5. O case pequeno (`qwen-todo-api`) produz um relatório que distingue
   corretamente o sucesso do workflow do desempenho do modelo avaliado.

## Success Criteria

Ver `docs/spec-master/guarded-mode-spec.md` §17 (Critérios de aceite,
9 itens) — reproduzidos como acceptance criteria em `[[app-features]]`.

## Constraints

- Controlador deve usar Python stdlib sempre que possível.
- Testes unitários não podem depender de Ollama, OpenCode ou rede.
- Processos externos devem ser mockáveis.
- A adição não pode alterar o comportamento de `--mode native`.
- `.spec-master/state.json` só pode ser promovido pelo controlador.
- O controlador nunca deve executar `git reset --hard` nem apagar trabalho
  não atribuído à tentativa atual.

## Governance

- Este repositório já possui `.specify/memory/constitution.md` (template
  padrão recém-copiado por `specify init --here`, ainda com placeholders).
  A fase `constitution` deste workflow deve preenchê-la a partir dos
  documentos normalizados e das convenções já existentes no repositório
  (README, estrutura de `spec-master/lib`, testes stdlib-only).

## Risks

- Divergência entre o exemplo de caminho do `PROTOCOL.md`
  (`.claude/commands/speckit.<phase>.md`) e a instalação real do Spec Kit
  neste repositório, que usa Skills em `.claude/skills/speckit-<phase>/`
  (kebab-case, sem ponto) — ver nota em `discovery.md`. Mitigação: cada fase
  deste workflow será executada invocando a Skill Claude Code
  correspondente pelo nome real instalado.
- A spec original é extensa (20 seções, 12 requisitos funcionais); o maior
  risco de escopo é tentar implementar tudo em uma única passada de
  `implement` sem tarefas suficientemente granulares — mitigado pela fase
  `tasks` do próprio Spec Kit.

## Stakeholders

- Usuário (mantenedor do Spec Master), único stakeholder identificado no
  contexto fornecido.

## Non-goals

Ver `[[app-features]]` — idêntico ao `## Fora do escopo` da spec original.

## Stopping Conditions

O workflow deve ser considerado concluído quando:

- os três modos estiverem disponíveis e testáveis;
- o controlador protegido impedir promoção falsa de fases (constitution
  com placeholder, código antes de `implement`, ferramenta simulada como
  texto, escrita fora da allowlist);
- a retomada funcionar sem repetir fases válidas;
- `python3 -m unittest discover -s spec-master/tests -v` passar
  integralmente;
- o case pequeno (`qwen-todo-api`) puder ser iniciado com um único comando
  documentado e produzir um relatório que distinga `workflow SUCCESS` de
  desempenho do modelo.

## Source Traceability

| Goal / Constraint | Source | Classification |
|---|---|---|
| Contexto e motivação (§1) | guarded-mode-spec.md §1 | EXPLICIT |
| Objetivo: três modos, padrão auto (§2) | guarded-mode-spec.md §2 | EXPLICIT |
| Migração faseada de implementação (§19) | guarded-mode-spec.md §19 | EXPLICIT |
| Definição de pronto (§20) | guarded-mode-spec.md §20 | EXPLICIT |
| Requisitos não funcionais (§15) | guarded-mode-spec.md §15 | EXPLICIT |
| Trunk-based, sem branch de feature | decisão do usuário nesta sessão (AskUserQuestion) | EXPLICIT |
| Divergência de path das Skills instaladas | leitura do repositório (`.claude/skills/`) | DISCOVERED_FROM_CODEBASE |
