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

### Feature 2 — guarded-noop-phase-validation

#### Objective

Corrigir o controlador guarded para que fases de inspeção (`clarify`,
`analyze`) possam ser aprovadas sem alterar arquivo quando o artefato
preexistente já satisfizer validações determinísticas específicas da
fase — sem enfraquecer nenhuma proteção existente contra falso sucesso.
Bug real encontrado ao rodar o case `qwen-greeting-api` em modo `guarded`:
`clarify` foi incorretamente bloqueado (`missing_artifact`) mesmo com um
`spec.md` completo e sem ambiguidades, porque o controlador hoje exige
`required_artifact_changed` para toda fase, sem distinguir "falso
sucesso" de "no-op válido".

#### Expected behavior

- Cada fase ganha uma política explícita em `phase_contracts.py`:
  `produce-or-update` (`constitution`, `specify`, `plan`, `tasks`,
  `validate` — exige alteração), `inspect-or-update` (`clarify`,
  `analyze` — pode concluir sem alteração sob condições determinísticas),
  `execute` (`implement` — critérios próprios, não a regra genérica).
- `clarify` só passa sem alteração quando TODAS as 11 condições da spec
  original §5 forem verdadeiras (sem timeout, exit 0, sem escrita
  proibida, sem ferramenta simulada, exatamente uma feature ativa
  resolvida via `.specify/feature.json`, `spec.md` existe/preenchido/sem
  placeholder/sem `[NEEDS CLARIFICATION`, resultado estruturado
  reconhecível de "nenhuma mudança necessária", sem pedido de decisão do
  usuário, sem erro/bloqueio declarado).
- `analyze` só passa sem alteração quando spec/plan/tasks da feature
  ativa existirem/estiverem preenchidos, sem placeholders bloqueantes,
  sem timeout/erro/escrita proibida/ferramenta simulada, resultado
  estruturado `no_changes_required` com zero achados `CRITICAL`/`HIGH` e
  sem `USER_DECISION_REQUIRED`/`SPEC_DRIFT` aberto.
- Resultado estruturado obrigatório para promover um no-op: bloco JSON
  `{"phase_result": ..., ...}` emitido como texto comum no transcript,
  com valores aceitos `artifact_updated | no_changes_required |
  user_decision_required | failed`; o controlador extrai o último bloco
  válido — texto fora dele nunca promove uma fase; o bloco é evidência
  complementar, nunca substitui as verificações de filesystem.
- Resolução do artefato ativo por `.specify/feature.json`
  (`feature_directory`), não por glob `specs/*/spec.md`: validar que é
  relativo ao projeto, rejeitar `..`/caminho absoluto/symlink que escape,
  resolver `<feature_directory>/spec.md`. Ausente/inválido →
  `active_feature_unresolved`.
- Fases produtoras continuam exigindo criação/alteração na primeira
  execução válida; só podem passar sem alteração numa tentativa
  subsequente se os artefatos já existentes forem integralmente
  validados, associados ao mesmo fingerprint de contexto, e sem evidência
  de terem vindo de uma tentativa rejeitada por escrita proibida ou
  escape de diretório.
- Motivos de resultado padronizados (`missing_artifact`,
  `placeholder_artifact`, `unchanged_artifact`, `valid_noop`,
  `phase_result_missing`, `phase_result_invalid`,
  `user_decision_required`, `forbidden_write`, `fake_tool_marker`,
  `timeout`, `tool_error`). `valid_noop` é sucesso;
  `user_decision_required` pausa o workflow (`PAUSED`) sem consumir uma
  nova tentativa automaticamente.
- `resume` reavalia (sem apagar histórico) uma última tentativa
  bloqueada quando a versão do contrato de fase mudou, o motivo anterior
  foi `missing_artifact`/`unchanged_artifact`, o artefato existe, e o
  fingerprint do contexto não mudou — registrando uma nova entrada de
  tentativa (`source: contract_revalidation`) sem reescrever a antiga.
- Estado de tentativa ganha `contract_version`, `policy`, `outcome`,
  `active_artifacts`, `artifact_hashes_before/after`, `structured_result`.

#### Acceptance criteria

- [ ] NPV-001: cada fase é classificada como `produce-or-update`,
      `inspect-or-update` ou `execute`.
- [ ] NPV-002: `clarify` pode passar sem alteração quando o spec ativo
      estiver completo e sem ambiguidades.
- [ ] NPV-003: `analyze` pode passar sem alteração quando não houver
      achados bloqueantes.
- [ ] NPV-004: resultado estruturado é exigido para promover um no-op.
- [ ] NPV-005: o artefato é resolvido pela feature ativa
      (`.specify/feature.json`), nunca por glob ambíguo.
- [ ] NPV-006: fases produtoras continuam exigindo alteração.
- [ ] NPV-007: `missing_artifact`, `unchanged_artifact` e `valid_noop`
      são distinguidos.
- [ ] NPV-008: `user_decision_required` pausa imediatamente sem
      desperdiçar tentativas.
- [ ] NPV-009: allowlists, proteção de paths e detecção de ferramenta
      simulada continuam intactas.
- [ ] NPV-010: uma tentativa bloqueada pelo contrato antigo pode ser
      revalidada de forma recuperável.
- [ ] NPV-011: política, versão do contrato, outcome e hashes são
      registrados no estado.
- [ ] NPV-012: workflows já concluídos continuam compatíveis (nenhuma
      migração destrutiva de estado existente).
- [ ] A suíte de testes atual (feature 1) continua passando integralmente.
- [ ] O case `qwen-greeting-api` consegue sair do bloqueio de `clarify`
      sem edição artificial no spec.
- [ ] O relatório final diferencia `artifact_updated` de
      `no_changes_required`.

#### Test scenarios

Ver `docs/spec-master/../..` — na verdade ver
`specs/002-guarded-noop-phase-validation/spec.md` §15 (cenários A-G) e
§16 (testes obrigatórios: 6 casos em `test_phase_contracts.py`, 7 em
`test_phase_runner.py`, 5 em `test_controller.py`, incluindo o cenário de
regressão G baseado no case real `qwen-greeting-api`).

## Cross-feature requirements

- Feature 2 (`guarded-noop-phase-validation`) depende da Feature 1
  (`guarded-mode-controller`): ela modifica `phase_contracts.py` e
  `phase_runner.py` já criados pela Feature 1 e não pode regredir nenhum
  dos testes/garantias já entregues por ela.

## Quality requirements

- Testes unitários não devem depender de Ollama, OpenCode ou rede (RNF).
- Processos externos devem ser mockáveis (RNF).
- Paths devem ser resolvidos e validados antes de qualquer operação (RNF).
- Snapshots devem ignorar `.venv`, caches, dependências instaladas e logs do
  próprio controlador (RNF).
- A adição não deve alterar o comportamento de `--mode native` (RNF).
- O controlador deve usar Python stdlib sempre que possível (RNF).
- Toda validação de no-op deve ser determinística e testável sem LLM (RNF,
  Feature 2).
- O parser do resultado estruturado não deve executar conteúdo do
  transcript; JSON inválido deve ser rejeitado com segurança; paths
  informados pelo agente são não confiáveis (RNF, Feature 2).
- A correção da Feature 2 não pode reduzir as proteções de fases
  produtoras já entregues pela Feature 1 (RNF, Feature 2).

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
- (Feature 2) Confiar irrestritamente na resposta textual do modelo;
  aprovar automaticamente ambiguidades de produto; alterar comandos do
  GitHub Spec Kit; remover allowlists ou snapshots; considerar timeout
  como no-op válido; reavaliar semanticamente toda a especificação usando
  outro LLM; mudar a política de tentativas global.

## Dependencies

- GitHub Spec Kit já inicializado neste repositório (`.specify/`,
  confirmado nesta execução via `specify init --here`).
- OpenCode CLI disponível no ambiente para o adaptador inicial
  (`spec-master/lib/opencode_runner.py`, já presente e não commitado, a ser
  integrado ao novo contrato de fases per §19 da spec original).
- `spec-master/lib/discovery.py` já estendido (não commitado) para localizar
  comandos `speckit.*` em `.opencode/commands` além de `.claude/commands`.
- Feature 2 depende inteiramente dos módulos entregues pela Feature 1
  (`controller.py`, `execution_mode.py`, `phase_contracts.py`,
  `phase_runner.py`, `opencode_runner.py`) e da suíte de testes existente
  (95 testes) permanecer verde.

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
| Bug real: `clarify` bloqueado com `missing_artifact` apesar de spec completo | specs/002-guarded-noop-phase-validation/spec.md §1 | EXPLICIT |
| Classificação de fases: `produce-or-update`/`inspect-or-update`/`execute` | specs/002-guarded-noop-phase-validation/spec.md §4 | EXPLICIT |
| Regras de no-op para `clarify` (11 condições) | specs/002-guarded-noop-phase-validation/spec.md §5 | EXPLICIT |
| Resultado estruturado (`phase_result`) e extração do último bloco válido | specs/002-guarded-noop-phase-validation/spec.md §6 | EXPLICIT |
| Resolução do artefato ativo via `.specify/feature.json` | specs/002-guarded-noop-phase-validation/spec.md §7 | EXPLICIT |
| Regras de no-op para `analyze` | specs/002-guarded-noop-phase-validation/spec.md §8 | EXPLICIT |
| Regras para fases produtoras (não regredir) | specs/002-guarded-noop-phase-validation/spec.md §9 | EXPLICIT |
| Motivos de resultado padronizados | specs/002-guarded-noop-phase-validation/spec.md §10 | EXPLICIT |
| Retomada após bloqueio incorreto (revalidação de contrato) | specs/002-guarded-noop-phase-validation/spec.md §11 | EXPLICIT |
| Novos campos de estado por tentativa | specs/002-guarded-noop-phase-validation/spec.md §12 | EXPLICIT |
| Requisitos funcionais NPV-001..NPV-012 | specs/002-guarded-noop-phase-validation/spec.md §13 | EXPLICIT |
| Requisitos não funcionais | specs/002-guarded-noop-phase-validation/spec.md §14 | EXPLICIT |
| Cenários de aceite A-G | specs/002-guarded-noop-phase-validation/spec.md §15 | EXPLICIT |
| Testes obrigatórios | specs/002-guarded-noop-phase-validation/spec.md §16 | EXPLICIT |
| Módulos afetados/novos já existem em `spec-master/lib/` (Feature 1) | leitura do repositório | DISCOVERED_FROM_CODEBASE |
