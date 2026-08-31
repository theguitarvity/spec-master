<div align="center">

# Spec Master

**Orquestrador agentic para o [GitHub Spec Kit](https://github.com/github/spec-kit).**
Um único comando — `/spec-master <arquivo-de-contexto>` — conduz todo o
ciclo *Specification-Driven Development*: `constitution → specify → clarify
→ plan → tasks → analyze (+repair) → implement → validate`. Se você ainda
não tem contexto, `/spec-master new` guia a descoberta da ideia por chat e
gera o contexto inicial.

`55 testes automatizados` · `Python 3 stdlib, zero dependências` · `Team Mode multiagente` · `Compatível com os 30+ agentes suportados pelo GitHub Spec Kit`

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
- [Estratégias de Git](#estratégias-de-git)
- [Retomada e idempotência](#retomada-e-idempotência)
- [Team Mode](#team-mode)
- [Métricas de entrega](#métricas-de-entrega)
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
python3 -m unittest discover -s spec-master/tests -v   # 55 testes, ~10ms
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
| `gates detect` | detecta os comandos reais de build/test/lint/coverage do projeto |
| `constitution diff` | diff estrutural (heading a heading) entre constitution existente e proposta |
| `traceability add\|render` | acumula e renderiza a matriz de rastreabilidade |
| `team roles\|intake\|adopt\|workstreams` | define papeis multiagente, perguntas guiadas, adoção incremental e work packages com peer review |
| `metrics record-round\|summarize` | registra tokens, duração e velocidade de entrega por rodada |

```bash
python3 spec-master/lib/cli.py discovery scan --path .
python3 spec-master/lib/cli.py gates detect --path .
python3 spec-master/lib/cli.py git-strategy plan --strategy trunk --feature-name "Demo feature"
python3 spec-master/lib/cli.py team intake
python3 spec-master/lib/cli.py team adopt
```

Referência completa de cada subcomando: [`spec-master/lib/cli.py`](spec-master/lib/cli.py) (docstring de topo) e [`spec-master/PROTOCOL.md`](spec-master/PROTOCOL.md) §0.

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

## Métricas de entrega

Ao final de cada rodada significativa, Spec Master registra métricas em:

```text
.spec-master/metrics/rounds.json
```

Cada rodada guarda fase, início/fim, tokens de entrada/saída quando o adapter
expor esses dados, pacotes/features concluídos e velocidade calculada. O
relatório final inclui total de tokens, tokens por minuto, pacotes por hora,
features por hora e observações quando a plataforma não expõe contagem exata
de tokens.

## Arquitetura

```text
spec-master/                    engine neutro, na raiz — fora de .claude/, .github/
│                                e .agents/ porque é compartilhado por todos os adapters
├── PROTOCOL.md                 protocolo model-agnostic (fonte da verdade)
├── adapters/{claude-code,copilot,codex,qwen,generic}.md
├── templates/                  templates dos 3 docs normalizados + prompts por fase
├── lib/                        core determinístico, Python 3 stdlib, zero deps
│   ├── cli.py                  state · fingerprint · discovery · features ·
│   │                           git-strategy · gates · constitution ·
│   │                           traceability · team
│   ├── team_model.py           Team Mode: papeis, intake, adoção, workstreams,
│   │                           Tech Lead ownership e peer review
│   ├── metrics.py              rodadas, tokens e velocidade de entrega
│   └── adapters_gen.py         gera os entrypoints dos 30+ agentes não-bespoke
│                                (tabela == registro de integrações do Spec Kit)
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

Para o detalhamento completo de cada arquivo do core (`state.py`,
`fingerprint.py`, `discovery.py`, `feature_model.py`, `git_strategy.py`,
`quality_gates.py`, `constitution_diff.py`, `traceability.py`), veja
[`docs/spec-master/README.md`](docs/spec-master/README.md).

## Testes

```bash
python3 -m unittest discover -s spec-master/tests -v
```

55 testes, sem depender de nenhum LLM: transições de estado (incluindo o
teto de 3 ciclos de repair e a regra de que uma fase não começa antes da
anterior ter `PASSED`), propagação de staleness por fingerprint, discovery
de repositório (nunca inventa comando para uma stack sem manifest),
ordenação de dependências (com detecção de ciclo), idempotência e
preservação de identificador na estratégia de git, detecção de quality gate
por stack, diff estrutural de constitution, renderização de rastreabilidade,
Team Mode com intake guiado, adoção incremental, papeis, workstreams e peer
review, além de métricas de tokens e velocidade de entrega.

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

- Paralelização real de features independentes (o grafo de dependências já
  suporta; a execução hoje é sequencial).
- Execução real dos workstreams do Team Mode por subagentes conectados aos
  adapters, usando `.spec-master/workstreams.json` como contrato.
- Integrações Jira / Azure DevOps / GitHub Issues.
- Dashboard/UI e MCP dedicado.
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
python3 -m unittest discover -s spec-master/tests -v
```

## Créditos

Construído sobre o [GitHub Spec Kit](https://github.com/github/spec-kit) —
Spec Master orquestra, mas nunca reimplementa, os comandos `speckit.*`.
</content>
