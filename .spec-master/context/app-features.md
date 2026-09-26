# App Features

## Context

Benchmark competitivo do mercado de spec-driven development (GitHub Spec Kit,
BMAD-METHOD, AWS Kiro, OpenSpec, Spec Kitty, Tessl, GSD, runtimes com
worktrees nativos) mapeado contra o roadmap e as limitações já declaradas
pelo próprio Spec Master (`README.md` §Roadmap,
`docs/spec-master/README.md` §"Limitations (this increment)"). Este
documento normaliza os 10 itens de Tier 1/Tier 2 do benchmark
(`docs/market-benchmark-roadmap.md`) como features candidatas a este
workflow. Os 3 itens de Tier 3 e o item explicitamente descartado (modelo
"spec-as-source" da Tessl) ficam em Non-goals, não como features.

## Scope

Evoluir o próprio pacote `spec-master/` (este repositório) — núcleo
determinístico Python (`spec-master/lib/`), templates, knowledge base e
adapters. Nenhuma mudança de escopo fora deste pacote foi solicitada.

## Features

### Feature 1 — parallel-worktree-execution

#### Objective

Executar features independentes do grafo de dependências em paralelo via git
worktrees, em vez de sequencialmente.

#### Expected behavior

- Dado um conjunto de features com dependências resolvidas
  (`features order`), features sem dependência mútua entre si podem ser
  executadas em worktrees isolados simultaneamente.
- Cada worktree roda seu próprio ciclo `specify -> clarify -> plan -> tasks
  -> analyze -> implement -> validate` isoladamente.
- Ao final, os resultados de cada worktree são integrados (merge) de volta
  ao branch de trabalho, com detecção de conflito reportada, nunca
  resolvida silenciosamente.
- Quando o git-strategy for `trunk`, a paralelização via worktree continua
  válida (worktrees não exigem branches de feature no Spec Kit); quando for
  `git-flow`, cada worktree usa o branch já planejado por `git-strategy
  plan`.

#### Acceptance criteria

- [ ] Uma nova função determinística decide, a partir do grafo de
      dependências já existente (`features order`), quais features do
      lote atual podem rodar em paralelo (nenhuma depende de outra ainda
      não `PASSED`/`COMPLETED`).
- [ ] Um novo comando do core (`git-strategy` ou grupo próprio) cria e
      remove worktrees isolados por feature, sem exigir dependências novas.
- [ ] A execução paralela nunca promove uma fase antes de sua dependência
      estar `PASSED`, preservando a guarda de state machine existente.
- [ ] Falha ou conflito em um worktree não derruba os demais worktrees em
      execução.
- [ ] O relatório final distingue quais features rodaram em paralelo e
      quais sequencialmente.
- [ ] Suíte de testes determinística cobrindo a nova lógica de agrupamento
      paralelo, sem depender de LLM.

#### Test scenarios

- Duas features sem dependência entre si → ambas elegíveis para execução
  paralela simultânea.
- Feature B depende de feature A ainda não concluída → B não entra no grupo
  paralelo com A.
- Conflito de merge ao integrar dois worktrees → reportado, não resolvido
  automaticamente.

### Feature 2 — team-mode-parallel-workstreams

#### Objective

Executar de fato, em paralelo, os workstreams do Team Mode usando o mesmo
mecanismo de worktrees da Feature 1, em vez de apenas planejá-los em
`.spec-master/workstreams.json` sem execução real.

#### Expected behavior

- Cada workstream com pacotes independentes entre si roda em seu próprio
  worktree, seguindo o dono (dev agent/role) já atribuído por `team
  workstreams`.
- Revisão por par (peer review) e validação de QA continuam obrigatórias
  antes da integração pelo Tech Lead, mesmo em execução paralela.

#### Acceptance criteria

- [ ] Workstreams sem dependência de arquivo/contrato compartilhado entre si
      são elegíveis para execução paralela via o mecanismo da Feature 1.
- [ ] Workstreams que compartilham arquivo/contrato permanecem sequenciais
      (nunca paralelizados às cegas).
- [ ] Peer review e QA continuam bloqueantes antes da integração, mesmo
      quando o pacote foi produzido em um worktree paralelo.
- [ ] `.spec-master/workstreams.json` passa a registrar o resultado real de
      execução (não apenas o plano), incluindo qual worktree rodou cada
      pacote.

#### Test scenarios

- Dois pacotes de dev agents diferentes, sem overlap de arquivos → rodam em
  paralelo.
- Dois pacotes que tocam o mesmo arquivo/contrato → forçados a sequencial.

#### Dependencies

- parallel-worktree-execution

### Feature 3 — speckit-tracker-orchestration

#### Objective

Detectar e orquestrar extensões/presets de tracker (Jira, Azure DevOps,
Linear, GitHub Issues) já existentes no ecossistema GitHub Spec Kit, em vez
de construir integrações próprias do zero.

#### Expected behavior

- `discovery scan` passa a detectar extensões de tracker instaladas no
  projeto-alvo (presença de configuração/preset de Jira, Azure DevOps,
  Linear ou GitHub Issues reconhecível no repositório).
- Quando uma extensão de tracker é detectada, o Spec Master a invoca (via a
  skill/comando que ela já expõe) em vez de reimplementar o fluxo de
  sincronização.
- Sem nenhuma extensão instalada, o comportamento atual (sem integração de
  tracker) é preservado — nunca falha por ausência.
- Reaproveita e estende a skill `speckit-taskstoissues` já presente no
  projeto, quando aplicável.

#### Acceptance criteria

- [ ] Nova detecção determinística em `discovery.py` reconhece ao menos uma
      extensão de tracker instalada, sem inventar presença.
- [ ] A orquestração nunca duplica lógica de sincronização já fornecida
      pela extensão — apenas invoca.
- [ ] Links/ids de issues sincronizados aparecem na matriz de
      rastreabilidade (`traceability`).
- [ ] Ausência de qualquer extensão de tracker não bloqueia o workflow.

#### Test scenarios

- Projeto-alvo com extensão de tracker Jira instalada → detectada e
  orquestrada.
- Projeto-alvo sem nenhuma extensão → workflow segue normalmente, sem
  integração de tracker.

### Feature 4 — sast-quality-gate

#### Objective

Promover a checagem de segurança estática (SAST) a quality gate
auto-detectado, no mesmo padrão de nunca hardcodar comando já usado para
build/test/lint, em vez de depender apenas da proposta manual de pentest
do Security Agent (Aegis Security) para apps críticos.

#### Expected behavior

- `gates detect` passa também a detectar scanners de segurança já
  configurados no repositório-alvo (ex.: configuração de Semgrep, workflow
  de CodeQL, outra ferramenta já presente).
- Quando detectado, o scanner vira um gate como qualquer outro
  (`{name, command, result, exit_code, blocking}`), sujeito ao mesmo
  `policy preflight` antes de execução.
- Quando nenhum scanner está configurado no projeto-alvo, nenhum gate de
  segurança é inventado — o Security Agent continua podendo propor
  ferramentas (como o Aegis Security) como recomendação, não como gate
  obrigatório inexistente.

#### Acceptance criteria

- [ ] `gates detect` reconhece configuração de scanner de segurança já
      presente no projeto-alvo, sem hardcodar nenhum comando específico.
- [ ] O gate de segurança detectado segue o mesmo contrato dos demais gates
      (`policy preflight`, bloqueante quando falha).
- [ ] Ausência de scanner configurado não gera um gate falso nem bloqueia o
      workflow.
- [ ] Comportamento existente do Security Agent (proposta de pentest para
      apps críticos) é preservado, não substituído.

#### Test scenarios

- Repositório com config de Semgrep presente → gate de segurança detectado
  e executado.
- Repositório sem nenhuma config de scanner → nenhum gate de segurança
  aparece, sem erro.

### Feature 5 — local-dashboard

#### Objective

Gerar um dashboard local, estático e sem dependências novas, a partir do
estado real do workflow (`.spec-master/state.json`,
`.spec-master/workstreams.json`, knowledge graph), fechando a primeira
metade do item de roadmap "Dashboard/UI e MCP dedicado".

#### Expected behavior

- Um novo comando do core gera um arquivo HTML autocontido (sem servidor,
  sem dependência externa) resumindo: features e seu status/fase atual,
  workstreams e seus donos, métricas de entrega, e um resumo visual do
  knowledge graph (reaproveitando `graph/maps.py::render_system_map`).
- O dashboard é regenerado a cada execução relevante do workflow (mesmo
  padrão de "nunca despejar output bruto", mas em formato navegável).

#### Acceptance criteria

- [ ] Novo comando determinístico gera um único arquivo HTML válido a
      partir de `state.json` + `workstreams.json` + grafo, sem servidor e
      sem nova dependência de terceiros.
- [ ] O HTML reflete corretamente o status de cada feature/fase no momento
      da geração (sem dados inventados).
- [ ] Geração é idempotente: rodar de novo sem mudança de estado produz o
      mesmo conteúdo (exceto timestamp).

#### Test scenarios

- Workflow com 2 features em fases diferentes → dashboard reflete
  corretamente ambos os status.
- Workflow recém-inicializado (sem features) → dashboard gera sem erro,
  mostrando estado vazio.

### Feature 6 — dedicated-mcp-server

#### Objective

Expor as capacidades de `spec-master/lib/cli.py` (state, traceability,
graph query, quality gates) como tools de um servidor MCP dedicado,
fechando a segunda metade do item de roadmap "Dashboard/UI e MCP dedicado".

#### Expected behavior

- Um servidor MCP, escrito com as mesmas restrições de dependência do core
  (ou isolado como um componente opcional claramente documentado, caso o
  protocolo MCP exija dependência externa), expõe leitura de estado,
  rastreabilidade, consulta ao grafo e execução de quality gates como
  tools MCP.
- Qualquer host MCP (não apenas os 30+ adapters de CLI já suportados) pode
  consultar o estado do Spec Master através dele.

#### Acceptance criteria

- [ ] O servidor MCP expõe, no mínimo, leitura de `state show`,
      `traceability render` e `graph query`/`graph neighbors` como tools.
- [ ] Nenhuma tool do servidor MCP escreve estado fora do que os comandos
      equivalentes do CLI já permitem (mesmo contrato de permissões).
- [ ] Documentação de instalação/uso do servidor MCP, consistente com os
      demais adapters já documentados.

#### Test scenarios

- Um cliente MCP genérico consulta o estado de uma feature em andamento via
  o servidor → recebe o mesmo dado que `state show` retornaria.

### Feature 7 — context-delta-reporting

#### Objective

Expor um relatório de delta explícito (estilo ADDED/MODIFIED/REMOVED) para
spec/plan/tasks a cada resume, complementando o `constitution diff` já
existente (que hoje só cobre a constitution).

#### Expected behavior

- Ao retomar um workflow com fingerprint divergente, além de decidir quais
  fases ficam stale, o Spec Master gera um resumo legível do que mudou nos
  documentos normalizados e nos artefatos de spec/plan/tasks desde a última
  execução.

#### Acceptance criteria

- [ ] Nova função determinística compara duas versões de spec/plan/tasks e
      classifica mudanças como ADDED/MODIFIED/REMOVED por seção.
- [ ] O relatório de delta é incluído no relatório final quando há resume
      com fingerprint divergente.
- [ ] Quando não há mudança (fingerprint idêntico), nenhum delta vazio é
      exibido.

#### Test scenarios

- Resume com uma seção nova adicionada ao spec → aparece como ADDED.
- Resume com uma seção removida → aparece como REMOVED.

### Feature 8 — declarative-event-hooks

#### Objective

Formalizar hooks declarativos orientados a evento (ex.: "quality gate
falhou → repair", "pacote mudou contrato público → revalidar
constitution"), reaproveitando a lógica de escalonamento já existente nos
playbooks de Team Mode.

#### Expected behavior

- Um conjunto de hooks nomeados, definidos deterministicamente, dispara
  ações já suportadas pelo core (ex.: iniciar um novo ciclo de analyze,
  marcar uma feature como stale) quando um evento correspondente ocorre
  durante o workflow.

#### Acceptance criteria

- [ ] Ao menos os dois hooks citados no contexto (`gate-failed -> repair`,
      `public-contract-changed -> revalidate-constitution`) existem como
      hooks nomeados e testáveis isoladamente.
- [ ] Hooks nunca executam uma ação fora do que o core já suporta via CLI
      (sem lógica nova de negócio embutida apenas no hook).
- [ ] Hooks disparados ficam registrados no relatório final (o que rodou,
      por qual evento).

#### Test scenarios

- Gate bloqueante falha → hook de repair dispara automaticamente.
- Pacote de dev agent altera um contrato público → hook revalida a
  constitution.

### Feature 9 — role-decision-memory

#### Objective

Registrar nós de decisão (quem decidiu o quê, por quê, quando) no knowledge
graph durante escalonamentos do Team Mode, consultáveis via
`knowledge for-role`.

#### Expected behavior

- Quando um escalonamento ocorre (dev agent → Architect → Tech Lead, por
  exemplo), a decisão final é registrada como nó de decisão no grafo, com
  proveniência e evidência apontando para o pacote/feature que a originou.

#### Acceptance criteria

- [ ] Novo tipo de nó de decisão é adicionado à ontologia existente
      (`ontology.yaml`), sem quebrar validação atual.
- [ ] Toda decisão de escalonamento resolvida pelo Tech Lead gera um nó de
      decisão rastreável até o pacote/feature de origem.
- [ ] `knowledge for-role`/consulta ao grafo permite recuperar decisões
      passadas relevantes a um papel.

#### Test scenarios

- Escalonamento de inconsistência arquitetural resolvido pelo Tech Lead →
  nó de decisão criado e consultável.

### Feature 10 — optional-pr-open-step

#### Objective

Oferecer, ao final de uma feature em Git Flow, um passo opcional de
abertura de PR — sempre mediante confirmação explícita do usuário, nunca
automático — anexando a matriz de rastreabilidade e o relatório final como
descrição.

#### Expected behavior

- Após uma feature atingir `validate: PASSED` em um workflow `git-flow`, o
  Spec Master pergunta ao usuário (via `AskUserQuestion`) se deseja abrir um
  PR para o branch da feature.
- Se sim, o PR é aberto com a matriz de rastreabilidade e o relatório final
  da feature como corpo da descrição.
- Se não, ou em workflow `trunk`, nenhuma ação de PR é tomada.

#### Acceptance criteria

- [ ] Pergunta explícita ao usuário antes de qualquer criação de PR, sem
      exceção.
- [ ] PR aberto inclui a rastreabilidade e o relatório final da feature.
- [ ] Em workflow `trunk`, o passo não se aplica (nenhuma pergunta sobre
      PR).

#### Test scenarios

- Feature `validate: PASSED` em `git-flow`, usuário confirma → PR aberto
  com descrição correta.
- Usuário recusa → nenhum PR é criado, workflow segue normalmente.

## Cross-feature requirements

- Toda nova decisão estrutural introduzida por essas features deve ser
  implementada no core determinístico (`spec-master/lib/`), exposta via
  `spec-master/lib/cli.py` como JSON em stdout, seguindo o padrão já
  estabelecido pelos módulos existentes (`git_strategy.py`,
  `quality_gates.py`, `graph/`).
- Nenhuma feature reimplementa um comando `speckit.*` já existente.

## Quality requirements

- Cobertura de testes determinística (sem LLM) para toda lógica nova do
  core, seguindo o padrão de `spec-master/tests/`.
- Nenhum comando de build/test/lint/security é hardcoded — sempre
  auto-detectado a partir do repositório-alvo.

## Non-goals

- Adotar o modelo "spec-as-source" da Tessl (spec como fonte única, código
  totalmente regenerável a partir dela) — contradiz o princípio
  anti-alucinação central do Spec Master.
- (Backlog Tier 3, não implementado neste workflow, apenas registrado para
  roadmap futuro): sintaxe estruturada tipo EARS para critérios de aceite;
  schema de export de métricas compatível com OpenTelemetry/JSON; "web
  bundle" portátil para chat UIs sem CLI.

## Dependencies

- team-mode-parallel-workstreams depende de parallel-worktree-execution.
- Demais features são independentes entre si.

## Open questions

- Nenhuma pendente no momento da geração deste documento — ambiguidades
  específicas de cada feature serão levantadas na fase `clarify`
  correspondente.

## Source traceability

| Requirement | Source | Classification |
|---|---|---|
| parallel-worktree-execution | docs/market-benchmark-roadmap.md, Tier 1 item 1 | EXPLICIT |
| team-mode-parallel-workstreams | docs/market-benchmark-roadmap.md, Tier 1 item 2 | EXPLICIT |
| speckit-tracker-orchestration | docs/market-benchmark-roadmap.md, Tier 1 item 3 | EXPLICIT |
| sast-quality-gate | docs/market-benchmark-roadmap.md, Tier 1 item 4 | EXPLICIT |
| local-dashboard | docs/market-benchmark-roadmap.md, Tier 1 item 5 | EXPLICIT |
| dedicated-mcp-server | docs/market-benchmark-roadmap.md, Tier 2 item 6 | EXPLICIT |
| context-delta-reporting | docs/market-benchmark-roadmap.md, Tier 2 item 7 | EXPLICIT |
| declarative-event-hooks | docs/market-benchmark-roadmap.md, Tier 2 item 8 | EXPLICIT |
| role-decision-memory | docs/market-benchmark-roadmap.md, Tier 2 item 9 | EXPLICIT |
| optional-pr-open-step | docs/market-benchmark-roadmap.md, Tier 2 item 10 | EXPLICIT |
| Detalhes de implementação (nomes de função, formato exato de CLI) | Inferidos a partir de `spec-master/lib/` existente | INFERRED |
