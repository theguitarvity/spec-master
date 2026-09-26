# Contexto — Benchmark de mercado e roadmap do Spec Master

> Autor: Victor Silva (victor.silva@telefonica.com), via sessão de benchmark competitivo
> Data: 2026-09-26
> Escopo: evoluir o próprio projeto `spec-master` (este repositório) — não um
> produto de terceiros. Este documento é o `<context-file>` de entrada para
> `/spec-master`.

## Objetivo

Tornar o Spec Master mais completo e robusto incorporando os gaps identificados
em um benchmark competitivo contra o mercado de ferramentas de spec-driven
development (GitHub Spec Kit, BMAD-METHOD, AWS Kiro, OpenSpec, Spec Kitty,
Tessl, GSD, e os runtimes de agente com suporte nativo a worktrees — Claude
Code, Cursor 2.0, Grok Build). As features abaixo já estão priorizadas em
tiers por impacto/esforço/alinhamento com o roadmap que o próprio projeto já
declara em `README.md` e em `docs/spec-master/README.md` ("Limitations (this
increment)").

Restrições de arquitetura que devem ser respeitadas (`DISCOVERED_FROM_CODEBASE`,
já validadas na leitura do repositório):

- Núcleo determinístico em Python stdlib puro, zero dependências externas,
  testável sem LLM (`spec-master/lib/`).
- Princípio "nunca reimplementa comandos `speckit.*`, apenas orquestra" —
  vale também para integrações de terceiros (trackers, scanners).
- Toda decisão estrutural nova deve seguir o padrão já existente de módulos em
  `spec-master/lib/` expostos via `spec-master/lib/cli.py` (JSON em stdout),
  documentados em `spec-master/PROTOCOL.md`.
- Nenhum comando de build/test/lint/security é hardcoded — tudo é
  auto-detectado a partir do repositório-alvo (ver `quality_gates.py` como
  precedente para o padrão a seguir).

## Tier 1 — alta prioridade (implementar primeiro, nesta ordem de dependência sugerida)

1. **Paralelização real de features independentes via git worktrees.**
   Fecha o item já existente no roadmap ("Paralelização real de features
   independentes — o grafo de dependências já suporta; a execução hoje é
   sequencial") e acompanha o padrão dominante do setor em 2026 (worktrees
   nativos em Claude Code, Cursor 2.0, Grok Build; e o concorrente direto
   Spec Kitty é construído inteiramente em torno disso). O grafo de
   dependências e a ordenação topológica já existem em `feature_model.py`;
   falta o mecanismo de execução paralela isolada por worktree e a
   agregação/merge dos resultados.
2. **Execução real dos workstreams do Team Mode em paralelo, usando o mesmo
   mecanismo de worktrees do item 1.** Fecha o segundo item do roadmap
   declarado ("Execução real dos workstreams do Team Mode por subagentes
   conectados aos adapters, usando `.spec-master/workstreams.json` como
   contrato"). Depende do item 1.
3. **Orquestração das integrações de tracker já existentes no ecossistema
   Spec Kit (Jira, Azure DevOps, Linear, GitHub Issues) em vez de construir
   integrações próprias do zero.** O GitHub Spec Kit já tem um sistema de
   extensões/presets da comunidade cobrindo esses trackers. Fecha o item do
   roadmap ("Integrações Jira / Azure DevOps / GitHub Issues") com custo
   muito menor, mantendo o princípio de nunca reimplementar o que o Spec Kit
   já oferece — deve reaproveitar/estender a skill `speckit-taskstoissues`
   já existente em `.claude/skills/speckit-taskstoissues/`.
4. **Scan de segurança (SAST) como quality gate auto-detectado**, seguindo o
   mesmo padrão de detecção real (nunca hardcoded) já usado para
   build/test/lint em `quality_gates.py` — detectar scanners já configurados
   no repositório-alvo (ex.: config de Semgrep, workflow de CodeQL) e
   promovê-los a gate bloqueante, não apenas a sugestão manual do Security
   Agent (que hoje só propõe pentest via Aegis Security para apps críticos).
5. **Dashboard local leve, estático, sem dependências novas.** Fecha o item
   do roadmap ("Dashboard/UI e MCP dedicado" — parte 1). HTML autocontido
   gerado a partir de `.spec-master/state.json`, `workstreams.json` e do
   knowledge graph (reaproveitando `graph/maps.py::render_system_map`), sem
   servidor. Refinado em 2026-09-26 (sugestão do usuário) com duas decisões
   explícitas para não contradizer as próprias restrições do item:
   - **Estética "utility-first" sem Tailwind real.** Nada de CDN (exige rede
     no momento de abrir o arquivo, deixa de ser autocontido) nem CLI/build
     (assume Node/npm, contradiz o núcleo stdlib-only). Gerar um `<style>`
     inline com um pequeno conjunto de classes utilitárias escritas à mão
     (flex/grid, spacing, badges de status), reproduzindo a estética sem
     nenhuma chamada externa.
   - **"Ao vivo" sem servidor.** O HTML gerado se autorrecarrega (`meta
     refresh` ou `setTimeout(location.reload)`); o próprio gerador é
     rechamado a cada transição real de fase. Como MVP, plugar essa chamada
     direto no ponto onde `controller.py` já registra `transition_phase`
     (não precisa esperar o item 8). Quando o item 8 (hooks declarativos)
     existir, migrar essa chamada direta para um hook declarativo, para não
     duplicar lógica de escalonamento em dois lugares — mesmo cuidado do
     item 15.
   - **Visão de completude** vem da leitura direta de `state.json` (% de
     fases `PASSED` por feature e global) — `render_system_map` continua
     reservado só para o painel de mapa de dependências dentro do mesmo HTML,
     ele não expõe status de fase.

## Tier 2 — prioridade média (na sequência, após o Tier 1 estabilizar)

6. **Servidor MCP dedicado**, expondo as capacidades de `spec-master/lib/cli.py`
   (state, traceability, graph query, quality gates) como tools MCP. Fecha a
   segunda metade do item de roadmap "Dashboard/UI e MCP dedicado".
7. **Relatório de delta explícito a cada resume** (estilo ADDED/MODIFIED/REMOVED,
   inspirado no OpenSpec) para spec/plan/tasks entre execuções — hoje o
   fingerprint já decide staleness internamente, mas não expõe um diff
   legível ao usuário como já existe para a constitution (`constitution diff`).
8. **Hooks declarativos orientados a evento** (ex.: "quality gate falhou →
   repair", "pacote mudou contrato público → revalidar constitution"),
   reaproveitando a lógica de escalonamento que já existe nos playbooks de
   Team Mode.
9. **Memória de decisão por papel no knowledge graph** — registrar nós de
   decisão (quem decidiu o quê, por quê, quando) durante escalonamentos do
   Team Mode, consultáveis via `knowledge for-role`. A infraestrutura do
   grafo já suporta isso; falta escrever esses nós no momento certo do fluxo.
10. **Passo opcional de abertura de PR ao final de uma feature em Git Flow**,
    sempre mediante confirmação explícita do usuário (nunca automático) —
    anexando a matriz de rastreabilidade e o relatório final como descrição
    do PR.

## Tier 3 — baixa prioridade / backlog

> Originalmente "não implementar agora". Em 2026-09-26 o usuário decidiu
> juntar os roadmaps e implementar todos os itens, incluindo este tier — ver
> [Status de implementação](#status-de-implementação-2026-09-26).

11. Sintaxe estruturada opcional tipo EARS para critérios de aceite.
12. Schema de export de métricas compatível com OpenTelemetry/JSON para
    `.spec-master/metrics/`.
13. "Web bundle" portátil (contexto + prompt da fase atual em um único
    arquivo colável) para uso em chat UIs sem acesso a CLI/ferramentas.

## Adendo (2026-09-26) — Workflow adaptativo por risco

> Origem: sugestão externa recebida pelo usuário sobre tornar o ciclo do Spec
> Master adaptativo por porte/risco de mudança em vez de sempre aplicar
> ceremônia completa, refinada em sessão de conversa com o Claude. `EXPLICIT`,
> aprovado pelo usuário para entrar no roadmap nesta data.
>
> Importante: a numeração dos itens 1-13 acima é referenciada como âncora de
> `source_requirements` pelas 9 features já derivadas em `.spec-master/state.json`
> (ex.: `#tier-1-item-4`, `#tier-2-item-7`). Os itens abaixo por isso recebem
> numeração nova (14+) em vez de reordenar os existentes — a prioridade real
> de execução é descrita em prosa (dependências), não pela posição no tier.

14. **Rastreabilidade incremental por feature.** Hoje toda a matriz de
    rastreabilidade vive como um único array dentro de
    `.spec-master/state.json` (já ~200 linhas para apenas 2 das 9 features
    concluídas). Passar a gravar cada feature em
    `.spec-master/traceability/features/<feature-id>.json` e gerar
    `reports/traceability.md` como render sob demanda (nunca editado à mão,
    nunca fonte da verdade) a partir desses arquivos. Sem dependências — pode
    ser implementado imediatamente.
15. **Ciclo de ceremônia adaptativo por risco.** Classificar cada feature em
    dois eixos independentes — **escopo** (quanto trabalho: arquivos/camadas
    tocadas) e **sensibilidade** (o que é tocado: auth, pagamento, schema,
    contrato público, secrets, novo provider externo) — e derivar o perfil de
    ceremônia do maior dos dois, nunca só do escopo (uma mudança de 3 linhas em
    código de auth não pode virar ciclo mini só por ser pequena). A checagem de
    sensibilidade roda no intake e de novo antes do `implement` (o escopo real
    só fica claro depois de `plan`/`tasks`), e o usuário sempre pode forçar um
    tier acima do calculado — todo override fica registrado como sinal de
    calibração para o item 16. **Depende dos itens 7 e 8** (ambos ainda
    `PENDING`): o mecanismo de checagem de sensibilidade deve ser expresso como
    hooks declarativos do item 8, reaproveitando a lógica de escalonamento de
    Team Mode, e não um mecanismo de gatilho paralelo; a superfície de contexto
    consumida no intake (arquitetura vigente, decisões superseded) deve vir do
    delta de fingerprint do item 7 combinado aos nós de decisão do item 9, não
    de um novo "context pack" mantido à parte. Recomenda-se adiantar a execução
    dos itens 7 e 8 para antes ou em paralelo ao item 15, mesmo mantendo sua
    posição de numeração em Tier 2 — hoje nenhum dos dois foi iniciado, então o
    reordenamento de execução não quebra trabalho em andamento.
16. **Loop de calibração de métricas por tier.** `.spec-master/metrics/rounds.json`
    já existe e já registra dados por rodada; falta consumi-los para comparar
    custo estimado vs. real por tier do item 15 e sinalizar deriva (ex.: "XS
    está custando como S há 3 features seguidas"), ajustando os limiares
    automaticamente em vez de deixá-los estáticos. Não duplica o item 12
    (schema de export OpenTelemetry, Tier 3) — aquele é formato de exportação,
    este é a lógica de consumo/recalibração. Depende do item 15 existir para
    ter tiers para calibrar.

## Status de implementação (2026-09-26)

Os itens 1–3 foram entregues pelo próprio fluxo do Spec Master (features em
`.spec-master/state.json` e `specs/`). A partir do item 4 o ciclo foi pausado
por decisão do usuário: não usar o Spec Master para evoluir o Spec Master.
Os itens 4–16 foram implementados diretamente no código, de forma agêntica,
sem artefatos `specs/NNN` e seguindo as restrições de arquitetura acima (stdlib
pura, nada hardcoded, nunca reimplementar `speckit.*`).

| # | Item | Módulo | CLI |
|---|---|---|---|
| 1 | Worktrees para features independentes | `lib/worktree.py` | `worktree waves\|plan\|conflicts\|aggregate` |
| 2 | Workstreams do Team Mode em paralelo | `lib/team_workstreams.py` | `workstreams review\|integrate\|aggregate` |
| 3 | Orquestração de trackers do Spec Kit | `lib/tracker_orchestration.py` | `tracker orchestrate` |
| 4 | SAST/secrets como gate bloqueante | `lib/sast_gates.py` (via `quality_gates.py`) | `gates detect` |
| 5 | Dashboard HTML autocontido | `lib/dashboard.py` | `dashboard render\|model` + hook `dashboard-refresh` |
| 6 | Servidor MCP dedicado | `mcp/spec_master_mcp.py` | todos os comandos, como tools |
| 7 | Delta ADDED/MODIFIED/REMOVED por resume | `lib/context_delta.py` | `delta snapshot\|report` |
| 8 | Hooks declarativos por evento | `lib/hooks.py` | `hooks init\|list\|validate\|emit\|firings` |
| 9 | Memória de decisão por papel | `lib/decision_memory.py` | `team escalate\|resolve\|decisions\|routes`, `knowledge for-role` |
| 10 | PR opcional em Git Flow | `lib/pr_step.py` | `pr plan` |
| 11 | EARS opcional | `lib/ears.py` | `ears check` |
| 12 | Export de métricas OpenTelemetry/JSON | `lib/metrics_export.py`, `schemas/metrics-round.schema.json` | `metrics export\|validate` |
| 13 | Web bundle | `lib/web_bundle.py` | `bundle build` |
| 14 | Rastreabilidade por feature | `lib/traceability.py` | `traceability add\|render\|migrate` |
| 15 | Ceremônia adaptativa por risco | `lib/risk_profile.py` + hooks `sensitivity-*` | `risk classify\|override\|profiles\|work-packages` |
| 16 | Calibração de métricas por tier | `lib/calibration.py` | `metrics calibrate` |

Cada item tem testes unitários em `spec-master/tests/` e está documentado em
`spec-master/PROTOCOL.md`.

No `.spec-master/state.json` deste repositório, as 7 features derivadas dos
itens 4–10 estão com `status: COMPLETED` e `delivery.mode:
agentic-outside-spec-master`. As fases delas continuam `PENDING` de propósito,
porque o Spec Kit nunca rodou para elas. O workflow está `PAUSED`, e a
rastreabilidade inline foi migrada para `.spec-master/traceability/features/`.

## Explicitamente fora de escopo

- **Não** adotar o modelo "spec-as-source" da Tessl (spec como fonte única,
  código totalmente regenerável a partir dela). Contradiz o princípio central
  do Spec Master de nunca inventar estrutura não sustentada pelo contexto ou
  pelo codebase real — a disciplina anti-alucinação é o diferencial, não algo a
  trocar por regeneração especulativa.

## Classificação de fontes

Todos os itens acima são `EXPLICIT` — vieram diretamente da sessão de
benchmark solicitada pelo usuário e foram por ele aprovados para execução via
`/spec-master`. Detalhes de implementação (nomes exatos de módulos, assinaturas
de função, formato de CLI) que não estão explicitados aqui devem ser tratados
como `INFERRED` durante `specify`/`plan`, nunca promovidos silenciosamente a
critério de aceite sem review.
