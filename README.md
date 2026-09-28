<div align="center">

# Spec Master

**Orquestrador agentic para o [GitHub Spec Kit](https://github.com/github/spec-kit).**
Um único comando — `/spec-master <arquivo-de-contexto>` — conduz todo o
ciclo *Specification-Driven Development*: `constitution → specify → clarify
→ plan → tasks → analyze (+repair) → implement → validate`. Se você ainda
não tem contexto, `/spec-master new` guia a descoberta da ideia por chat e
gera o contexto inicial.

`886 testes automatizados` · `Python 3 stdlib, zero dependências` · `Team Mode multiagente` · `Compatível com os 30+ agentes suportados pelo GitHub Spec Kit`

</div>

---

## Índice

- [Por quê](#por-quê)
- [Como funciona](#como-funciona)
- [Instalação](#instalação)
  - [Uso local (só este repo)](#uso-local-só-este-repo)
  - [Instalação global (todos os projetos)](#instalação-global-todos-os-projetos)
- [Uso rápido](#uso-rápido)
- [Referência de comandos](#referência-de-comandos)
  - [Servidor MCP](#servidor-mcp)
- [Estratégias de Git](#estratégias-de-git)
- [Retomada e idempotência](#retomada-e-idempotência)
- [Team Mode](#team-mode)
- [Métricas de entrega](#métricas-de-entrega)
- [Modo guarded (opt-in, experimental)](#modo-guarded-opt-in-experimental)
- [Harness (opt-in): lanes, hooks e plugin](#harness-opt-in-lanes-hooks-e-plugin)
- [Arquitetura](#arquitetura)
- [Estrutura do repositório](#estrutura-do-repositório)
- [Testes](#testes)
- [Condições de parada](#condições-de-parada)
- [FAQ / Troubleshooting](#faq--troubleshooting)
- [Roadmap](#roadmap)
- [Contribuindo](#contribuindo)
- [Créditos](#créditos)

---

## Por quê

O [Spec Kit](https://github.com/github/spec-kit) trouxe disciplina para
desenvolvimento orientado a especificação, mas o operador humano ainda
precisa costurar sete comandos manualmente, decidir quando avançar, quando
corrigir, quando parar e perguntar — e repetir tudo isso por feature.

```text
/speckit.constitution
/speckit.specify
/speckit.clarify
/speckit.plan
/speckit.tasks
/speckit.analyze
/speckit.implement
```

**Spec Master** é a camada de orquestração acima disso. Você aponta para um
único documento de contexto — `CLAUDE.md`, `AGENTS.md`, uma ADR, um
discovery, uma spec preliminar, o que já existir — e ele:

1. entende o projeto (discovery read-only do repositório);
2. normaliza o contexto em três documentos rastreáveis (`app-features.md`,
   `project-goals.md`, `tech-stack.md`);
3. constrói ou evolui a constitution;
4. identifica uma ou mais features e resolve a ordem de dependência entre
   elas;
5. executa o workflow completo do Spec Kit para cada uma, com um repair loop
   automático no `analyze` (máx. 3 ciclos);
6. roda os quality gates reais do projeto (nunca um comando inventado);
7. entrega uma matriz de rastreabilidade e um relatório final.

No **Team Mode**, esse mesmo fluxo ganha uma camada de organização de equipe:
PO, Scrum Master, Architect, Tech Lead, UI/UX + Brand, Backend Dev, Frontend
Dev, Fullstack Dev, QA, DevOps, Infra e Security. O Spec Master continua
orquestrando o Spec Kit; o Tech Lead quebra o trabalho, resolve conflitos
técnicos e aprova integração; os dev agents implementam pacotes específicos;
e todo pacote passa por code review de outro dev agent antes da validação.

Sem inventar requisito, critério de aceite, dependência ou tecnologia que
não esteja sustentado pelo contexto fornecido ou pelo código existente — toda
inferência é marcada como `EXPLICIT`, `INFERRED`, `DISCOVERED_FROM_CODEBASE`
ou `UNRESOLVED`.

## Como funciona

```text
Context (.md)
  │
  ▼
Guided intake, se nao houver contexto
  PO · UI/UX + Brand · Architect · Scrum Master
  │
  ▼
Discovery (read-only)
  │
  ▼
Spec Kit check + Git strategy         ◄── única pergunta obrigatória,
  (uma única pergunta, batched)           batched, nunca uma de cada vez
  │
  ▼
Normalized context layer
  project-goals.md · app-features.md · tech-stack.md
  │
  ▼
Constitution (gerada ou evoluída, nunca sobrescrita às cegas)
  │
  ▼
Feature discovery + dependency ordering
  │
  ▼
Team Mode workstreams
  Tech Lead quebra packages · dev agents implementam · peer review obrigatório
  │
  ▼
┌─────────────────────────────────────────────────────────┐
│  por feature, em ordem de dependência:                   │
│  Specify → Clarify → Plan → Tasks →                       │
│  Analyze ⟲ repair (máx. 3) → Implement → Validate          │
└─────────────────────────────────────────────────────────┘
  │
  ▼
Quality gates reais do projeto (build/test/lint/coverage)
  │
  ▼
Traceability matrix + Final report
  SUCCESS · PARTIAL · BLOCKED · FAILED
```

A lógica **estrutural** (máquina de estados, fingerprint de contexto,
ordenação de dependências, estratégia de git, detecção de quality gates,
diff de constitution, rastreabilidade) fica num **core Python determinístico
e testado sem LLM**. A lógica **semântica** (ler o contexto, escrever specs,
resolver ambiguidade) fica no prompt do agente. Veja [Arquitetura](#arquitetura).

## Instalação

### Uso local (só este repo)

Clone (ou já estando neste repo) — nada para instalar, é tudo Python 3
stdlib:

```bash
python3 -m unittest discover -s spec-master/tests   # 886 testes
```

Os entrypoints locais mantidos na raiz deste repositório são só os que
precisam funcionar imediatamente aqui: adapters dedicados, com mecânicas
próprias documentadas em [`spec-master/adapters/`](spec-master/adapters/):

| Agente | Entrypoint | Invocação |
|---|---|---|
| Claude Code | [`.claude/commands/spec-master.md`](.claude/commands/spec-master.md) | `/spec-master <context-file>` |
| GitHub Copilot | [`.github/skills/spec-master/SKILL.md`](.github/skills/spec-master/SKILL.md) | `/spec-master <context-file>` |
| OpenAI Codex CLI | [`.agents/skills/spec-master/SKILL.md`](.agents/skills/spec-master/SKILL.md) | `$spec-master <context-file>` |
| Qwen-compatible shells | [`.qwen/commands/spec-master.md`](.qwen/commands/spec-master.md) | `/spec-master <context-file>` |
| Antigravity (`agy`) | [`.agents/agents/spec-master/agent.md`](.agents/agents/spec-master/agent.md) | selecione via `/agents` |

Todos os **demais agentes que o [GitHub Spec Kit](https://github.com/github/spec-kit)
suporta** (30+ — Gemini CLI, Cursor, IBM Bob, Trae, Kilo Code, Goose, Cline,
Auggie, Devin, Factory Droid, Grok Build, RovoDev, ZCode, Zed, Antigravity
`agy`, Kiro CLI, Tabnine, Forge, Kimi Code, e mais) continuam cobertos, mas
não ficam mais materializados na raiz do repo-fonte. Eles são gerados sob
demanda pela tabela em
[`spec-master/lib/adapters_gen.py`](spec-master/lib/adapters_gen.py) para o
projeto alvo, no diretório e formato que cada agente realmente lê
(`SKILL.md`, custom agent, comando Markdown, TOML ou recipe YAML):

```bash
python3 spec-master/lib/adapters_gen.py list
python3 spec-master/lib/adapters_gen.py generate --root ~/code/projeto --engine-ref ~/.spec-master-engine
```

Ver [`spec-master/adapters/generic.md`](spec-master/adapters/generic.md) para
o racional completo, incluindo ressalvas específicas (Kiro CLI não substitui
`$ARGUMENTS` em prompts de arquivo; Goose roda via `goose run`; Hermes só
instala globalmente).

### Instalação global (todos os projetos)

Um script, uma vez por máquina — depois disso, `/spec-master` existe em
**qualquer** projeto para os agentes com convenção pessoal/de-usuário
confirmada, sem copiar nada:

```bash
./init.sh
```

Isso:

- espelha o engine (`spec-master/`) para `~/.spec-master-engine`;
- registra um entrypoint **global** para cada agente, no diretório
  pessoal/de usuário que cada um já documenta para skills próprias:

  | Agente | Entrypoint global |
  |---|---|
  | Claude Code | `~/.claude/commands/spec-master.md`, `~/.claude/skills/spec-master/` |
  | GitHub Copilot CLI | `~/.copilot/skills/spec-master/`, `~/.copilot/agents/spec-master.agent.md` |
  | OpenAI Codex CLI | `~/.codex/skills/spec-master/` |
  | Hermes | `~/.hermes/skills/spec-master/` (Spec Kit só instala Hermes globalmente) |
  | fallback compartilhado (Copilot CLI e Codex CLI também leem) | `~/.agents/skills/spec-master/` |

- roda os passos de projeto (abaixo) contra o diretório atual.

Confirmado inspecionando uma máquina real com os CLIs instalados —
`~/.copilot/agents/` e `~/.codex/skills/` já tinham outras skills nesse
exato formato antes do Spec Master chegar; nada nesses diretórios foi
sobrescrito, o Spec Master só adiciona sua própria entrada ao lado. Os
**demais 30+ agentes** do Spec Kit não têm convenção pessoal/global
documentada pelo próprio Spec Kit — instalar um diretório `~/.<agente>` para
eles seria um chute não verificado, então ficam de fora do passo global e
entram apenas via `link` (por-projeto, abaixo), que espelha exatamente o
diretório que cada integração do Spec Kit já usa no projeto.

Para gerar também um pointer **por-projeto** — útil para colega de time sem
`init.sh` rodado, ou repositório que quer o pointer versionado — cobrindo
Copilot, Codex **e todos os 30+ agentes gerados**, ou pular a reinstalação
do engine:

```bash
./init.sh link ~/code/outro-projeto   # pointers Copilot/Codex + os 30+ gerados ali
./init.sh --engine-only               # só atualiza o engine + os globais confirmados
./init.sh --project ~/code/projeto    # instala tudo mirando outro diretório
```

`init.sh` também verifica se o **Spec Kit** já está inicializado no projeto
alvo (`.specify/`); se não estiver e o CLI `specify` (ou `uvx`) estiver
disponível, oferece rodar `specify init --here` na hora. Sem terminal
interativo, ele degrada de forma segura (pula e imprime o comando manual, em
vez de travar).

## Uso rápido

```bash
/spec-master CLAUDE.md
```

```bash
/spec-master docs/architecture-context.md
```

```bash
/spec-master new
```

Quando chamado sem um contexto pronto, Spec Master entra no modo guiado:
pergunta tipo de projeto, usuario, MVP, direcao de experiencia/marca, stack
e estrategia de entrega por multiplas escolhas, gera
`.spec-master/context.generated.md` e entao continua o fluxo normal.

O arquivo de contexto pode ter qualquer organização — Spec Master interpreta
semanticamente, não exige headings específicos. Numa primeira execução, ele
pergunta **uma única vez**, numa única mensagem:

> 1. Spec Kit ainda não inicializado neste projeto — inicializar agora?
> 2. Qual estratégia de desenvolvimento este projeto utiliza?
>    **Git Flow / Feature Branches** ou **Trunk-Based Development**?

Depois disso, roda de ponta a ponta sem interromper — a menos que encontre
uma ambiguidade de negócio, um conflito de constitution, ou outra condição
genuinamente bloqueante (veja [Condições de parada](#condições-de-parada)).

## Referência de comandos

O core determinístico é exposto via CLI e pode ser chamado diretamente —
tanto pelo agente quanto por você, para depurar ou inspecionar o estado:

| Comando | O que faz |
|---|---|
| `state init\|show\|set-workflow\|transition\|analyze-cycle` | máquina de estados e checkpoint (`.spec-master/state.json`) |
| `fingerprint compute\|compare` | hash dos documentos normalizados e propagação de staleness |
| `discovery scan` | varre o repositório (linguagem, build/test/lint, CI, Spec Kit, constitution) sem alterar nada |
| `features order` | ordenação topológica de features por dependência, com detecção de ciclo |
| `git-strategy plan` | decide branch/idempotência para Git Flow vs Trunk-Based |
| `gates detect` | detecta os comandos reais de build/test/lint/coverage do projeto, e scanners SAST/secrets já configurados (Semgrep, Bandit, Gitleaks, CodeQL) como gates bloqueantes |
| `constitution diff` | diff estrutural (heading a heading) entre constitution existente e proposta |
| `traceability add\|render\|migrate` | matriz de rastreabilidade gravada por feature (`.spec-master/traceability/features/<id>.json`); o relatório é só render |
| `delta snapshot\|report` | delta ADDED/MODIFIED/REMOVED de spec/plan/tasks (e constitution/contexto) entre execuções, com fases que ficaram stale |
| `hooks init\|list\|validate\|emit\|firings` | hooks declarativos por evento (`.spec-master/hooks.json`): gate falhou → repair, contrato mudou → revalidar constitution, escalonamentos, sensibilidade de risco |
| `team roles\|intake\|adopt\|workstreams\|escalate\|resolve\|decisions\|routes` | papeis multiagente, intake guiado, adoção incremental, work packages com peer review, rotas de escalonamento e memória de decisão (nós `Decision` + ADR) |
| `metrics record-round\|summarize` | registra tokens, duração e velocidade de entrega por rodada (`--append` grava em `rounds.json` com lock) |
| `telemetry locate\|ingest` | lê o uso medido pelo host (transcript do Claude Code ou JSON do `claude -p`) e monta a rodada |
| `baseline plan\|run\|summarize` | baseline medido: fluxo do Spec Master × braço agentic direto (`run` exige `--yes`) |
| `lane triage` · `step next\|begin\|end\|widen\|pause\|resume` | fluxo por lane (opt-in): triagem e mudança patch fechada só com evidência |
| `state evidence` | mostra ou checa a evidência por trás das fases de uma feature |
| `harness install-hooks\|mode` · `doctor run` | liga os hooks do host ao kernel · autoverificação para CI |
| `risk classify\|override\|profiles\|work-packages` | tier de cerimônia XS–XL por feature = max(escopo, sensibilidade via hooks, override); decide se clarify é pulável, profundidade do analyze, revisores e work packages por papel em L/XL; reclassifica antes do implement |
| `metrics calibrate` | compara custo real × orçamento de cada tier, detecta drift e propõe (ou, com `--apply`, grava) novos limites em `.spec-master/risk/thresholds.json` |
| `metrics validate\|export` | valida `rounds.json` contra `schemas/metrics-round.schema.json` e exporta como OTLP/JSON (`/v1/metrics`) ou JSONL; nunca envia nada sozinho |
| `bundle build` | gera um único Markdown colável (prompt da fase + artefatos + contexto, dentro do orçamento de tokens) para chats sem acesso a arquivos |
| `worktree waves\|plan\|conflicts\|aggregate` | execução paralela de features independentes em git worktrees |
| `workstreams review\|integrate\|aggregate` | vereditos de peer review/integração dos work packages do Team Mode executados em paralelo |
| `tracker orchestrate` | detecta extensões de tracker do Spec Kit já instaladas (Jira, Azure DevOps, Linear, GitHub Issues) e diz qual invocar |
| `dashboard render\|model` | dashboard HTML autocontido (`.spec-master/reports/dashboard.html`), re-renderizado por hook a cada fase; recarrega sozinho enquanto o ciclo roda |
| `pr plan` | passo opcional de PR no fim de uma feature Git Flow: gera o corpo em `.spec-master/reports/pr-<id>.md` e só devolve o comando `gh`/`glab`/`az` depois de confirmação explícita; nunca executa nada |
| `ears check` | lint opcional de critérios de aceite no formato EARS (EN/PT), consultivo por padrão; `--strict` quando a constitution exigir |

```bash
python3 spec-master/lib/cli.py discovery scan --path .
python3 spec-master/lib/cli.py gates detect --path .
python3 spec-master/lib/cli.py git-strategy plan --strategy trunk --feature-name "Demo feature"
python3 spec-master/lib/cli.py team intake
python3 spec-master/lib/cli.py team adopt
```

Referência completa de cada subcomando: [`spec-master/lib/cli.py`](spec-master/lib/cli.py) (docstring de topo) e [`spec-master/PROTOCOL.md`](spec-master/PROTOCOL.md) §0.

### Servidor MCP

Agentes que falam MCP podem chamar o core como tools, sem shell:
[`spec-master/mcp/spec_master_mcp.py`](spec-master/mcp/spec_master_mcp.py) é um
servidor MCP stdio (só stdlib) que expõe **todos** os comandos do `cli.py`. A lista
de tools é introspectada do parser — `state show` vira `state_show`,
`traceability render` vira `traceability_render` — então um grupo novo da CLI
aparece no MCP sem mudar o servidor. Cada chamada roda o próprio `cli.py` em
subprocesso: mesmo JSON, mesmos códigos de saída, mesmas regras do protocolo.

O repositório não cria `.mcp.json` sozinho; para registrar no projeto:

```json
{"mcpServers": {"spec-master": {"type": "stdio", "command": "python3",
  "args": ["spec-master/mcp/spec_master_mcp.py"],
  "env": {"SPEC_MASTER_MCP_TIMEOUT": "120"}}}}
```

Com o engine global, aponte para `~/.spec-master-engine/mcp/spec_master_mcp.py`
e passe `--project <repo>` (ou `SPEC_MASTER_PROJECT`). `--list-tools` imprime o
catálogo. Detalhes em [`spec-master/mcp/README.md`](spec-master/mcp/README.md).

## Estratégias de Git

Perguntado uma única vez por workflow, nunca de novo:

| Estratégia | Comportamento |
|---|---|
| **Git Flow / Feature Branches** | cada feature ganha uma branch (`feature/<slug>`, ou um identificador explícito como `APP-1234` preservado verbatim). Reaproveita a extensão git do Spec Kit se já existir — nunca reinstala. |
| **Trunk-Based Development** | nenhuma branch é criada automaticamente. O trabalho continua na branch atual; features são separadas logicamente via `specs/<feature>/`. |

## Retomada e idempotência

```bash
/spec-master CLAUDE.md
```

Se `.spec-master/state.json` já existir, Spec Master compara o fingerprint
do contexto:

- **Idêntico** → retoma sozinho, da primeira fase que não estiver
  `PASSED`/`COMPLETED` — sem perguntar nada.
- **Diferente** → pergunta **Resume** vs **Restart**; se retomar, só refaz as
  fases que o fingerprint marcou como stale (uma mudança em `tech-stack.md`
  nunca invalida `specify`; nenhuma mudança invalida `implement`
  automaticamente — o impacto é avaliado, não presumido).

Toda fase administrativa é idempotente: Spec Kit já instalado não é
reinstalado, extensão git já presente não é readicionada, constitution já
compatível não é reescrita, feature já validada não é reimplementada.

## Team Mode

Team Mode adiciona uma organização multiagente sobre o fluxo canônico do
Spec Kit, sem substituir suas fases:

| Papel | Responsabilidade principal |
|---|---|
| Spec Master | orquestra processo, estado, rastreabilidade e gates |
| PO Agent | escopo, valor, MVP, prioridade e decisões de negócio |
| Scrum Master Agent | bloqueios, dependências e paralelismo seguro |
| Architect Agent | arquitetura macro, integrações e riscos técnicos |
| Tech Lead Agent | quebra técnica, ownership, conflitos de código e integração |
| UI/UX + Brand Agent | experiência, fluxos, identidade visual e design system inicial |
| Backend Dev Agent | APIs, dados, regras de negócio, integrações e testes backend |
| Frontend Dev Agent | telas, componentes, estado, acessibilidade e testes UI |
| Fullstack Dev Agent | slices ponta a ponta e costura front/back |
| QA / DevOps / Infra / Security | validação, entrega operacional, ambientes e riscos |

Em projeto novo, `/spec-master new` usa `team intake` para gerar o contexto.
Em projeto que já está rodando Spec Master, `team adopt` adequa o workflow de
forma incremental: preserva estado, constitution, decisões e fases já
concluídas, cria `.spec-master/workstreams.json` e aplica os novos gates só
daquele ponto em diante.

### Playbooks de agente

Cada papel do Team Mode tem um playbook próprio em
`spec-master/knowledge/playbooks/<papel>.md`: mandato, direitos de decisão,
práticas obrigatórias (convenção de testes unitários e de integração, layout
de pacotes hexagonal, WireMock/Cypress, IaC/CI-CD por tecnologia), o que
evitar, e para quem escalar cada tipo de decisão (ex.: Backend Dev detecta
inconsistência arquitetural → Architect Agent → Tech Lead cria o pacote de
remediação → Scrum Master registra métricas e replaneja). O Knowledge Router
(`knowledge for-role` / `knowledge route`) prioriza o playbook do papel
antes de qualquer outro módulo de conhecimento — ver §6 do `PROTOCOL.md`.
GoF design patterns (quando usar cada um, por sintoma no código) ficam em
`knowledge/design/gof-patterns.md`.

## Métricas de entrega

Ao final de cada rodada significativa, Spec Master registra métricas em:

```text
.spec-master/metrics/rounds.json
```

Cada rodada guarda fase, início/fim, tokens, pacotes/features concluídos e
velocidade calculada. Os números vêm do próprio host, nunca da memória do
agente, e cada linha diz de onde vieram (`source`):

```bash
# Claude Code: lê só usage e timestamps do transcript da sessão (nunca o conteúdo)
python3 spec-master/lib/cli.py telemetry ingest --path . --latest --since <início da rodada> \
  --round-id r12 --phase plan --feature-id <id> --append
# execução headless: o JSON de `claude -p --output-format json` traz o custo medido
python3 spec-master/lib/cli.py telemetry ingest --headless-json result.json --ended-at <fim> \
  --round-id r13 --phase implement --append
# host sem contabilidade: fica registrado como manual-unverified
python3 spec-master/lib/cli.py metrics record-round --round-id r14 --phase tasks \
  --started-at <início> --ended-at <fim> --source manual --append
```

`--append` valida a linha e grava de forma atômica, com lock. `metrics
validate` acusa como erro uma linha medida pelo host com 0 tokens ou que
termina no futuro, e avisa sobre linhas sem fonte verificada; a calibração
ignora linhas não medidas. As saídas de subagentes gravadas no transcript são
um retrato do começo do stream, então `output_tokens` vira um limite inferior
e a linha diz isso nas `notes`; o custo exato vem do modo headless.

**Baseline medido.** `baseline plan|run|summarize` compara o fluxo do Spec
Master com um braço agentic direto nos mesmos casos (worktree limpo por
execução, checagens reais, custo do próprio host). `plan` não executa nada e
mostra o gasto no pior caso; `run` gasta dinheiro de verdade e só roda com
`--yes`, depois da concordância explícita do usuário.

## Modo guarded (opt-in, experimental)

O comportamento padrão de `/spec-master` documentado acima — o agente
conduz o workflow inteiro — **não muda**. Existe, além dele, um
controlador determinístico opcional que conduz cada fase do Spec Kit
(`constitution` → `specify` → `clarify` → `plan` → `tasks` → `analyze` →
`implement` → `validate`) em uma sessão isolada, validando o artefato
obrigatório de cada fase antes de promovê-la — pensado para modelos
locais menos confiáveis (que podem implementar cedo demais, simular
chamadas de ferramenta como texto, ou declarar sucesso sem produzir o
artefato esperado). Hoje ele é acionado diretamente, não pelo comando
`/spec-master`:

```bash
python3 spec-master/lib/controller.py run \
  --project . --context context.md \
  --mode guarded --integration opencode --model <modelo>

python3 spec-master/lib/controller.py resume --project .
python3 spec-master/lib/controller.py status --project .
```

Suporta apenas a integração OpenCode nesta primeira versão. Detalhes de
design, contrato de fases e escopo em
[`docs/spec-master/guarded-mode-spec.md`](docs/spec-master/guarded-mode-spec.md)
e [`specs/001-guarded-mode-controller/`](specs/001-guarded-mode-controller/).

## Harness (opt-in): lanes, hooks e plugin

O fluxo padrão de `/spec-master` descrito acima **não muda**. Ao lado dele há
um kernel de harness ([`spec-master/lib/kernel/`](spec-master/lib/kernel/),
stdlib) que decide quanto processo cada mudança precisa e faz o host
(Claude Code) cumprir essas decisões por hooks, em vez de depender de o
agente seguir um protocolo longo. Motivação, medições e ondas seguintes em
[`docs/harness-reformulation/`](docs/harness-reformulation/).

### Lanes

| Lane | Quando | O que roda |
|---|---|---|
| `patch` | até 3 arquivos de produção, 1 módulo, ~50 linhas, com teste declarado e gate executável, sem caminho sensível | `step begin` → implementar → `step end` |
| `standard` | maior que patch (até 12 arquivos, 3 camadas, 800 linhas) | ciclo completo do `/spec-master` |
| `critical` | auth, pagamentos, segredos, schema/migração, ações irreversíveis (push, publish, deploy, CI), ou repositório sem gate de teste | ciclo completo do `/spec-master` |

A triagem só sobe de lane: o pedido do usuário (`--lane`) e o
`min_lane` de `.spec-master/policy.json` nunca baixam o lane calculado. Sinais
que só aparecem no texto do pedido (ex.: "abrir um PR") viram uma pergunta de
confirmação, respondida com `--confirm <sinal>` / `--deny <sinal>`, em vez de
mudar o lane sozinhos.

```bash
/spec-master --lane add() deve aceitar strings numéricas

python3 spec-master/lib/cli.py lane triage --path . --intent "..." --paths src/calc.py,tests/test_calc.py
python3 spec-master/lib/cli.py step begin  --path . --intent "..." --paths src/calc.py,tests/test_calc.py
python3 spec-master/lib/cli.py step end    --path .
```

`step end` só grava `PASSED` com evidência: uma nota curta
(`.spec-master/changes/<id>.md`) com `Intent: ... [EXPLICIT]` e cada critério
apontando o teste que o cobre, os gates reais passando, nenhuma escrita fora
dos arquivos declarados, e toda citação `[DISCOVERED_FROM_CODEBASE]`
apontando um `arquivo:linha` que existe. Um bugfix
(`--kind bugfix --regression-test <teste> --test-command "<cmd>"`) exige que o
teste de regressão falhe no commit base (num worktree temporário) e passe na
árvore. Se o diff crescer além do patch, a mudança vira `ESCALATED` e o card
seguinte manda para o ciclo completo. `step widen`, `step pause` e
`step resume` cobrem o resto.

### Hooks e plugin

[`hookd`](spec-master/lib/kernel/hookd.py) responde aos eventos do host:

- **PreToolUse** — comandos Bash passam pela política por argv (nega
  `git reset --hard`, `git clean -f`, qualquer force push, `curl ... | sh`,
  `sudo`; pergunta antes de `git push`, publish de pacote, `gh pr create`,
  `terraform apply`); escritas nos arquivos do core (`state.json`,
  `changes/*.json`, `metrics/rounds.json`, `policy.json`, `gates.json`,
  `.git/`) são negadas; com uma mudança patch em andamento, escritas fora dos
  arquivos declarados são negadas (testes sempre permitidos); no fluxo
  padrão, escrever código antes do `analyze` `PASSED` é negado.
- **PostToolUse** — avisa quando o diff saiu do lane patch.
- **Stop** — uma mudança patch em andamento precisa passar por `step end`
  (no máximo 2 reentradas; depois ela fica `PAUSED`).
- **SessionStart** — reinjeta o card atual depois de um restart ou
  compactação.

O modo padrão é `audit`: decide e registra em
`.spec-master/hooks/decisions.jsonl` sem interferir, para medir falsos
positivos antes de ligar o bloqueio. `{"hooks_mode": "block"}` em
`.spec-master/policy.json` passa a aplicar as decisões. Projetos sem
`.spec-master/` nunca recebem escrita.

```bash
# por projeto: mescla as entradas em .claude/settings.json (idempotente)
python3 spec-master/lib/cli.py harness install-hooks --project . --mode audit

# ou como plugin do Claude Code (hooks + skill de lane); o modo, então, só pela política
claude plugin marketplace add theguitarvity/spec-master
claude plugin install spec-master@spec-master
python3 spec-master/lib/cli.py harness mode --project . --mode block
```

### Doctor

```bash
python3 spec-master/lib/cli.py doctor run --path .
```

Autoverificação para CI (sai com código 1 se houver erro): toda invocação
de `cli.py` nos documentos lidos por agentes existe no parser; orçamentos do
kernel (≤2500 linhas), do caminho do PreToolUse (≤1500 linhas importadas e
≤100 ms p50, medidos) e dos cards; versão do Spec Kit fixada; fases `PASSED`
sem evidência verificada; `rounds.json`, `policy.json` e `gates.json` válidos.

### O que mudou no fluxo padrão

- `state transition ... --status PASSED` exige evidência: artefatos da fase
  presentes e sem placeholder, `tasks.md` todo marcado no `implement`, ao
  menos uma linha de rastreabilidade no `validate`. Histórico que nunca rodou
  pelo Spec Master entra com `--import-unverified --reason "..."` e fica
  registrado como não verificado; `state evidence --feature <id>` mostra ou
  checa a evidência.
- `state upsert-feature` grava só metadados: `phases`, `evidence`,
  `attempts`, `risk` e `analyze_repair_cycles` pertencem ao core (mudam por
  `transition`), com a mesma válvula `--import-unverified`.
- Escritas em `state.json` são atômicas e serializadas por lock.
- A saída JSON é compacta; `--pretty` (ou `SPEC_MASTER_PRETTY=1`) formata.
  `state transition` devolve um ack curto (`--full` para o registro inteiro)
  e `context budget file` devolve só ids (`--with-content` para o conteúdo).
- Contratos de fase e tentativas são por feature (`specs/<dir>/...`,
  `<feature>/<fase>`).
- O tier de risco não é mais inflado pelo texto das tasks; ações
  irreversíveis (push, PR, publish, deploy) elevam o piso para M.
- Gates declarados em `.spec-master/gates.json` têm precedência sobre os
  detectados; suítes `unittest` são detectadas.
- O Spec Kit é fixado em `v0.16.4` (`SPEC_KIT_REF` no `init.sh`).

## Arquitetura

```text
spec-master/                    engine neutro, na raiz — fora de .claude/, .github/
│                                e .agents/ porque é compartilhado por todos os adapters
├── PROTOCOL.md                 protocolo model-agnostic (fonte da verdade)
├── adapters/{claude-code,copilot,codex,qwen,generic}.md
├── templates/                  templates dos 3 docs normalizados + prompts por fase
├── lib/                        core determinístico, Python 3 stdlib, zero deps
│   ├── cli.py                  todos os grupos de comando, JSON no stdout
│   ├── kernel/                 harness: lanes, step, política, hookd, doctor
│   ├── evidence.py             evidência exigida para promover uma fase
│   ├── team_model.py           Team Mode: papeis, intake, adoção, workstreams,
│   │                           Tech Lead ownership, peer review e escalonamento
│   ├── decision_memory.py      decisões de escalonamento no grafo + ADR
│   ├── metrics.py              rodadas, tokens e velocidade de entrega
│   ├── calibration.py          calibração dos tiers de risco a partir das rodadas
│   ├── metrics_export.py       export OpenTelemetry/JSON das métricas
│   ├── risk_profile.py         tiers de ceremônia por escopo × sensibilidade
│   ├── hooks.py                hooks declarativos por evento
│   ├── context_delta.py        delta de spec/plan/tasks entre execuções
│   ├── traceability.py         rastreabilidade por feature + render
│   ├── worktree.py             ondas paralelas em git worktrees
│   ├── sast_gates.py           scanners SAST/secrets como gate
│   ├── tracker_orchestration.py  extensões de tracker do Spec Kit
│   ├── pr_step.py · ears.py    PR opcional (Git Flow) · lint EARS
│   ├── dashboard.py            dashboard HTML autocontido
│   ├── web_bundle.py           bundle de arquivo único para chat UIs
│   └── adapters_gen.py         gera os entrypoints dos 30+ agentes não-bespoke
│                                (tabela == registro de integrações do Spec Kit)
├── cards/                      instruções curtas por passo do fluxo por lane
├── hooks/hooks.json · skills/  componentes do plugin do Claude Code
├── .claude-plugin/plugin.json  manifesto do plugin
├── mcp/spec_master_mcp.py      servidor MCP stdio (todos os comandos como tools)
├── schemas/                    JSON schema do registro de rodada de métricas
└── tests/                      suíte unittest, sem LLM

.claude/commands/spec-master.md      entrypoint Claude Code — $ARGUMENTS, AskUserQuestion
.claude/skills/spec-master/          pointer de auto-discovery do Claude Code
.github/skills/spec-master/          entrypoint GitHub Copilot
.agents/skills/spec-master/          entrypoint OpenAI Codex CLI
.agents/agents/spec-master/agent.md  custom agent Antigravity (agy)
.qwen/commands/spec-master.md        entrypoint Qwen-compatible shells

init.sh                         instalador global (~/.spec-master-engine +
                                 entrypoint global para os 4 agentes confirmados,
                                 ver abaixo) + `link` para os 30+ restantes por projeto
```

Nenhum diretório de plataforma contém Python, template ou protocolo próprio
— cada um é um arquivo fino que diz "leia `spec-master/PROTOCOL.md`, chame
`spec-master/lib/cli.py`, e aqui está como *esta* plataforma pergunta ao
usuário / resolve seu argumento de invocação". Um único core testado, quatro
adapters escritos à mão (Claude, Copilot, Codex, Qwen), um custom agent local
para Antigravity, e mais 30+ adapters gerados sob demanda a partir de uma
única tabela. Depois de `./init.sh`, há registro global nos agentes com
convenção pessoal confirmada; depois de `./init.sh link <projeto>`, os
entrypoints da longa cauda são materializados no projeto alvo.

## Estrutura do repositório

```text
.
├── README.md                   você está aqui
├── CLAUDE.md                   especificação original da skill
├── init.sh                     instalador global
├── spec-master/                engine (protocolo + core + templates + testes)
├── docs/spec-master/README.md  referência técnica detalhada
├── .claude/                    entrypoints Claude Code
├── .github/                    entrypoint GitHub Copilot
├── .agents/                    entrypoint OpenAI Codex CLI + custom agent Antigravity
└── .qwen/                      entrypoint Qwen-compatible shells
```

Para o detalhamento completo de cada arquivo do core, veja
[`docs/spec-master/README.md`](docs/spec-master/README.md).

## Testes

```bash
python3 -m unittest discover -s spec-master/tests
```

O core e a suíte são stdlib pura (Princípios II e III da constitution); o
`PyYAML`, se instalado, é só um parser mais rápido para o front matter de
grafo/knowledge.

886 testes, sem depender de nenhum LLM: transições de estado (incluindo o
teto de 3 ciclos de repair e a regra de que uma fase não começa antes da
anterior ter `PASSED`), propagação de staleness por fingerprint, discovery
de repositório (nunca inventa comando para uma stack sem manifest),
ordenação de dependências (com detecção de ciclo), idempotência e
preservação de identificador na estratégia de git, detecção de quality gate
por stack, diff estrutural de constitution, renderização de rastreabilidade,
Team Mode com intake guiado, adoção incremental, papeis, workstreams e peer
review, métricas de tokens e velocidade de entrega, e cada item do roadmap:
SAST/secrets, dashboard, servidor MCP, delta entre execuções, hooks, memória
de decisão, PR opcional, EARS, export OpenTelemetry, web bundle,
rastreabilidade por feature, tiers de risco e calibração. O harness tem
evals de replay determinísticas: o lane patch de ponta a ponta num
repositório git temporário com gate real (inclusive bugfix que precisa
falhar no commit base), e o `hookd` recebendo os eventos que o host mandaria
(implementar antes do analyze, editar `state.json`, comando destrutivo, parar
sem verificar, retomar após compactação), em modo audit e block.

## Condições de parada

| Status | Quando |
|---|---|
| `SUCCESS` | constitution válida, todas as features implementadas, todo critério de aceite rastreado, analyze sem findings bloqueantes, todos os quality gates bloqueantes passando, nenhum `SPEC_DRIFT` não resolvido |
| `BLOCKED` | ambiguidade não resolvível, conflito constitucional, decisão arquitetural destrutiva pendente de aprovação, dependência/credencial/serviço faltando, quality gate falhando repetidamente sem correção segura, spec drift exigindo decisão de produto |
| `FAILED` | Spec Kit indisponível (usuário recusou inicializar, ou `specify`/`uvx` não encontrado), repositório inconsistente além de reparo seguro, implementação não consegue satisfazer os critérios de aceite, testes críticos continuam falhando |
| `PARTIAL` | algumas features `SUCCESS`, outras `BLOCKED`/`FAILED` — reportado por feature |

## FAQ / Troubleshooting

<details>
<summary><strong>Rodei <code>/spec-master</code> e ele parou dizendo <code>FAILED — Spec Kit unavailable</code></strong></summary>

O projeto não tem `.specify/` e você recusou (ou não pôde) inicializar. Rode
`specify init --here` no projeto (ou `./init.sh link .` para deixar o
Spec Master oferecer isso de novo) e invoque `/spec-master` outra vez — ele
retoma do ponto em que parou, não reinicia o workflow.
</details>

<details>
<summary><strong>Preciso reinstalar/atualizar o engine global depois de mudar algo em <code>spec-master/</code></strong></summary>

```bash
./init.sh --engine-only
```

Reflete as mudanças em `~/.spec-master-engine` sem tocar em nenhum projeto.
</details>

<details>
<summary><strong>Como uso em um projeto Copilot ou Codex depois de instalar globalmente?</strong></summary>

```bash
./init.sh link /caminho/do/projeto
```

Gera só os dois arquivos-pointer (`.github/skills/spec-master/SKILL.md`,
`.agents/skills/spec-master/SKILL.md`) apontando para o engine global — nada
do core é copiado para lá.
</details>

<details>
<summary><strong>Por que existem <code>spec-master/</code> e <code>.spec-master/</code>?</strong></summary>

`spec-master/` (sem ponto) é o código-fonte do orquestrador, versionado.
`.spec-master/` (com ponto) é gerado em runtime por cada execução — estado,
relatórios, logs. Propositalmente parecidos (um é a ferramenta, o outro é a
saída dela), mas são diretórios diferentes.
</details>

## Roadmap

O roadmap de benchmark de mercado
([`docs/market-benchmark-roadmap.md`](docs/market-benchmark-roadmap.md), itens
1–16) está implementado: worktrees paralelos, workstreams do Team Mode,
trackers via extensões do Spec Kit, SAST como gate, dashboard, MCP, delta por
resume, hooks, memória de decisão, PR opcional, EARS, export de métricas, web
bundle, rastreabilidade por feature, ceremônia adaptativa por risco e
calibração por tier. A tabela de status com módulo e comando de cada item fica
no próprio documento.

Próximos passos:

- Validar ponta a ponta num projeto real com Spec Kit inicializado (hoje a
  cobertura é de core, testes unitários e smoke tests de CLI).
- Acompanhar mudanças nos diretórios globais de Copilot CLI/Codex CLI (ainda
  evoluindo rápido nesses agentes) e ajustar `init.sh` se algum deles mudar
  de convenção.

## Contribuindo

Este repositório é a fonte de um único artefato: a skill `/spec-master`.

- Lógica estrutural nova → `spec-master/lib/`, com teste `unittest`
  correspondente em `spec-master/tests/` (sem depender de LLM).
- Mudança de protocolo/prompt → `spec-master/PROTOCOL.md` e
  `spec-master/templates/prompts/*.md`.
- Mudança específica de um dos 4 agentes com adapter dedicado (Claude,
  Copilot, Codex, Qwen) → o `adapters/*.md` correspondente, mantendo o
  entrypoint real (`.claude/`, `.github/`, `.agents/`, `.qwen/`) como um
  pointer fino, nunca uma cópia do protocolo.
- Spec Kit adicionou/renomeou/reconfigurou um agente do outro grupo (os 30+
  gerados) → atualize a tabela `AGENTS` em
  [`spec-master/lib/adapters_gen.py`](spec-master/lib/adapters_gen.py) e
  rode `python3 spec-master/lib/adapters_gen.py generate --root . --engine-ref spec-master`
  para regenerar os entrypoints afetados — nunca edite um arquivo gerado à
  mão, a próxima regeneração o sobrescreveria.

Depois de qualquer mudança:

```bash
python3 -m unittest discover -s spec-master/tests
python3 spec-master/lib/cli.py doctor run --path .
```

## Créditos

Construído sobre o [GitHub Spec Kit](https://github.com/github/spec-kit) —
Spec Master orquestra, mas nunca reimplementa, os comandos `speckit.*`.
</content>
