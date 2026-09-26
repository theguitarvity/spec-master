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
   servidor.

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

## Tier 3 — baixa prioridade / backlog (não implementar agora; registrar como itens futuros no roadmap)

11. Sintaxe estruturada opcional tipo EARS para critérios de aceite.
12. Schema de export de métricas compatível com OpenTelemetry/JSON para
    `.spec-master/metrics/`.
13. "Web bundle" portátil (contexto + prompt da fase atual em um único
    arquivo colável) para uso em chat UIs sem acesso a CLI/ferramentas.

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
