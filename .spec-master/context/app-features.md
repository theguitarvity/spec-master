# App Features

## Context

O Spec Master hoje delega ao agente toda a condução semântica e operacional
do fluxo `constitution → specify → clarify → plan → tasks → analyze →
implement → validate`. Modelos robustos sustentam esse comportamento
agentic, mas modelos locais menores ou menos confiáveis podem implementar
antes da fase `implement`, ignorar comandos `speckit.*`, imprimir chamadas
de ferramenta como texto, reentrar no skill, criar artefatos em caminhos
errados, declarar sucesso sem produzir o artefato obrigatório, perder a fase
atual após compactação, ou travar sem progresso.

## Scope

Ver `## Escopo` (Incluído/Fora do escopo) em
`docs/spec-master/guarded-mode-spec.md` — reproduzido nas seções abaixo.

## Features

### Feature 1 — guarded-mode-controller

#### Objective

Adicionar três modos de execução (`native`, `guarded`, `auto`, padrão
`auto`) e um controlador determinístico que, em modo `guarded`, conduza
todas as transições de fase e entregue ao modelo apenas uma fase por
sessão, validando artefatos antes de promover o estado.

#### Expected behavior

- `--mode native` preserva o comportamento agentic atual, sem alterações.
- `--mode guarded`: para cada fase, o controlador lê `.spec-master/state.json`,
  confirma que a fase anterior está `PASSED`, cria snapshot dos arquivos
  relevantes, renderiza um prompt curto específico da fase, inicia uma sessão
  nova sem histórico de fases anteriores, desabilita skills/subagentes/
  continuação automática, executa somente o comando `speckit.<fase>`
  correspondente, aplica timeout, coleta transcript/ferramentas/alterações no
  filesystem, valida os artefatos obrigatórios e só então promove a fase para
  `PASSED`; se inválido, registra a causa e repete até o limite de
  tentativas, marcando `BLOCKED` ao esgotar.
- `--mode auto` começa em `native` e migra irreversivelmente para `guarded`
  ao detectar qualquer evento crítico ou dois eventos recuperáveis (lista em
  `project-goals.md`/spec original §9), registrando `mode_transition` no
  estado e retomando da primeira fase ainda não validada.
- Allowlist de escrita por fase (tabela §6 da spec original) é aplicada:
  apenas os caminhos definidos por fase podem ser escritos; motor global,
  credenciais, arquivos fora do projeto, `.git/`, `.spec-master/state.json` e
  transcripts de tentativas anteriores são sempre protegidos.
- O adaptador inicial do modo guarded usa OpenCode (`opencode run --pure
  --format json --dir <project> --agent spec-phase --model <model> --command
  speckit.<phase> <phase-prompt>`), com um agente dedicado `spec-phase` sem
  skill loading, sem auto-continue, web desabilitada por padrão, uma fase por
  sessão, modelo explícito, filesystem/shell disponíveis, diretório do
  projeto fixado, saída JSONL arquivada.
- CLI determinística exposta via `python3 spec-master/lib/controller.py run
  --project . --context <arquivo> --mode guarded --integration opencode
  --model <modelo>`, mais `resume --project .` e `status --project .`.
- Retomada idempotente: fases `PASSED` com fingerprint válido não são
  repetidas; execução interrompida retoma da primeira fase não validada;
  `run.lock` abandonado é reconhecido como stale após o timeout configurado;
  artefatos de tentativa inválida vão para `.spec-master/failed-attempts/`
  ou são revertidos por estratégia recuperável — nunca `git reset --hard` ou
  apagar trabalho não atribuído à tentativa atual.
- Observabilidade: eventos curtos por tentativa/fase e relatório final que
  separa resultado do workflow, resultado de cada quality gate, contribuição
  efetiva do modelo, tentativas rejeitadas, mudança de modo e arquivos
  preservados para diagnóstico — nunca apresentar um projeto implementado
  por fallback/controlador como aprovação do modelo avaliado.

#### Acceptance criteria

- [ ] `--mode` aceita exatamente `native`, `guarded`, `auto`; ausência de
      `--mode` resolve para `auto` (GM-001, GM-002).
- [ ] Em modo `guarded`, cada fase roda em uma sessão isolada, sem histórico
      de fases anteriores (GM-003).
- [ ] Nenhuma fase é promovida a `PASSED` sem validação de artefato
      obrigatório presente e não vazio, e sem placeholders de template
      restantes (GM-004).
- [ ] Escrita fora da allowlist da fase corrente é rejeitada e a tentativa
      falha com causa registrada (GM-005).
- [ ] Código criado antes da fase `implement` é detectado e rejeita a
      tentativa (GM-006).
- [ ] Chamadas de ferramenta impressas como texto (`<function=`,
      `<tool_call>` ou equivalentes) são detectadas e rejeitam a tentativa
      (GM-007).
- [ ] Timeout (`phase_timeout_seconds`, padrão 600) e limite de tentativas
      (`max_attempts_per_phase`, padrão 2) são aplicados; ao esgotar
      tentativas a fase fica `BLOCKED` e o workflow para (GM-008).
- [ ] Modo `auto` migra irreversivelmente para `guarded` conforme a política
      de eventos críticos/recuperáveis definida, sem retorno automático a
      `native` no mesmo workflow (GM-009).
- [ ] `resume` retoma um workflow protegido sem repetir fases já `PASSED`
      com fingerprint válido (GM-010).
- [ ] Transcripts e causas de falha de cada tentativa são preservados
      (GM-011).
- [ ] O adaptador OpenCode funciona fim a fim sem quebrar `--mode native`
      nem os adaptadores já existentes (GM-012).
- [ ] `python3 -m unittest discover -s spec-master/tests -v` passa
      integralmente, incluindo os novos testes unitários e de integração
      com agente falso listados na spec original (§16).
- [ ] Um agente falso não consegue marcar `constitution` como `PASSED`
      mantendo o template original (critério de aceite 3 da spec original).
- [ ] Um agente falso não consegue criar código durante `constitution`,
      `specify`, `clarify`, `plan`, `tasks` ou `analyze` sem a tentativa ser
      rejeitada (critério de aceite 4).
- [ ] O relatório final diferencia claramente `workflow SUCCESS` de `model
      FAILED` (critério de aceite 8).

#### Test scenarios

Ver `## Testes obrigatórios` da spec original
(`docs/spec-master/guarded-mode-spec.md` §16): 14 casos unitários, 8 casos
de integração com agente falso, e um smoke test opcional não bloqueante com
`qwen-todo-api`.

## Cross-feature requirements

- Não há outras features nesta execução — a spec descreve uma única
  entrega coesa (o controlador guarded + os três modos).

## Quality requirements

- Testes unitários não devem depender de Ollama, OpenCode ou rede (RNF).
- Processos externos devem ser mockáveis (RNF).
- Paths devem ser resolvidos e validados antes de qualquer operação (RNF).
- Snapshots devem ignorar `.venv`, caches, dependências instaladas e logs do
  próprio controlador (RNF).
- A adição não deve alterar o comportamento de `--mode native` (RNF).
- O controlador deve usar Python stdlib sempre que possível (RNF).

## Non-goals

- Escolher ou baixar modelos automaticamente.
- Avaliar qualidade literária dos documentos por heurística subjetiva.
- Substituir o GitHub Spec Kit.
- Executar duas fases simultaneamente.
- Corrigir automaticamente decisões de produto ambíguas.
- Garantir que qualquer modelo local consiga completar o projeto.
- Suportar, neste primeiro incremento, todos os agentes do registro do Spec
  Kit em modo protegido (apenas OpenCode inicialmente; arquitetura não deve
  impedir adaptadores futuros).

## Dependencies

- GitHub Spec Kit já inicializado neste repositório (`.specify/`,
  confirmado nesta execução via `specify init --here`).
- OpenCode CLI disponível no ambiente para o adaptador inicial
  (`spec-master/lib/opencode_runner.py`, já presente e não commitado, a ser
  integrado ao novo contrato de fases per §19 da spec original).
- `spec-master/lib/discovery.py` já estendido (não commitado) para localizar
  comandos `speckit.*` em `.opencode/commands` além de `.claude/commands`.

## Open questions

- A spec original não define o nome do arquivo de lock (`run.lock`)
  explicitamente além de citá-lo em §12 — assumir
  `.spec-master/run.lock`, alinhado ao padrão de state em
  `.spec-master/state.json` (INFERRED).
- A spec não define um valor padrão para o timeout de "lock abandonado" além
  de reutilizar "o timeout configurado" (§12) — assumir
  `phase_timeout_seconds` como esse valor até haver evidência em contrário
  (INFERRED).

## Source traceability

| Requirement | Source | Classification |
|---|---|---|
| Três modos `native`/`guarded`/`auto`, padrão `auto` | guarded-mode-spec.md §2 | EXPLICIT |
| Fluxo do modo guarded (13 passos por fase) | guarded-mode-spec.md §5 | EXPLICIT |
| Contrato por fase (artefatos/escritas permitidas) | guarded-mode-spec.md §6 | EXPLICIT |
| Validações gerais e estruturais | guarded-mode-spec.md §7 | EXPLICIT |
| Política de tentativas (defaults) | guarded-mode-spec.md §8 | EXPLICIT |
| Política de migração automática (eventos críticos/recuperáveis) | guarded-mode-spec.md §9 | EXPLICIT |
| Estrutura de `state.json.execution` | guarded-mode-spec.md §10 | EXPLICIT |
| Isolamento OpenCode via agente `spec-phase` | guarded-mode-spec.md §11 | EXPLICIT |
| Retomada e idempotência | guarded-mode-spec.md §12 | EXPLICIT |
| Observabilidade e relatório | guarded-mode-spec.md §13 | EXPLICIT |
| Requisitos funcionais GM-001..GM-012 | guarded-mode-spec.md §14 | EXPLICIT |
| Requisitos não funcionais | guarded-mode-spec.md §15 | EXPLICIT |
| Testes obrigatórios | guarded-mode-spec.md §16 | EXPLICIT |
| Critérios de aceite | guarded-mode-spec.md §17 | EXPLICIT |
| `opencode_runner.py` e discovery multi-integração já existem no repo | leitura do repositório (`git status`, `git diff`) | DISCOVERED_FROM_CODEBASE |
| Nome/local do `run.lock` e do timeout de stale-lock | inferência a partir de §12 | INFERRED |
