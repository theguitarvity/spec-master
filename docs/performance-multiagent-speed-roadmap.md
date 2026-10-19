# Contexto — Performance, Multi-agente, Modo Speed e Observabilidade de Tokens

> Autor: Victor Silva (victor.silva@telefonica.com), via sessão `/spec-master` com agentes de mercado
> Data: 2026-10-19
> Escopo: evoluir o próprio `spec-master` (este repositório). Este documento é a
> avaliação + o plano com opções. Depois que as opções forem escolhidas, ele
> serve como `<context-file>` de entrada para `/spec-master` (ou para execução
> agêntica direta, como nos itens 4–16 de `docs/market-benchmark-roadmap.md`).

Fontes desta sessão (três agentes em paralelo):

- **Agente de mercado**: Spec Kit, BMAD v6, OpenSpec, Kiro, GSD, Spec Kitty, Tessl,
  Claude Code (subagents, agent teams, worktrees, OTel, statusline), Cursor 2.0,
  Codex, ccusage, dashboards de observabilidade (disler, Agents Observe, Langfuse).
- **Agente de auditoria do código**: leitura de `spec-master/lib`, `PROTOCOL.md`,
  constitution, testes e medições reais de tempo.
- **Agente de telemetria**: fontes de tokens no Claude Code, Codex e Copilot.

Classificação: `EXPLICIT` = pedido do usuário nesta sessão; `DISCOVERED_FROM_CODEBASE`
= medido/lido no repo; `MARKET` = evidência externa (URL); `INFERRED` = proposta
de design ainda não aprovada.

---

## 1. Pedido (EXPLICIT)

1. Avaliação de compatibilidade do Spec Master com projetos **brownfield** e **greenfield**.
2. Ganho de **performance**.
3. **Modo multi-agente**.
4. **Modo speed**: implementação "XGH do bem", rápida mas com qualidade e **TDD first**.
5. **Consumo de tokens** das sessões do Spec Master sempre visível ao operador.
6. **Dashboard React em tempo real** para acompanhar a execução.
7. Plano de implementação **com opções** de abordagem para o usuário escolher.

---

## 2. Avaliação de compatibilidade

### 2.1 Placar

| Dimensão | Greenfield | Brownfield | Evidência |
|---|---|---|---|
| Intake de contexto | 🟢 bom | 🔴 fraco | `team intake` (`lib/team_model.py:379`) só pergunta "que projeto quer criar"; `team adopt` (`:388-456`) é adoção do *Spec Master*, não de código legado |
| Discovery do repo | 🟡 n/a | 🔴 raso | `discovery.scan` (`lib/discovery.py:106-193`) só lê manifests na raiz; sem monorepo, sem layout de código, sem arquitetura. No próprio repo retorna `stacks: []` |
| Constitution | 🟢 | 🟡 | `constitution diff` é estrutural por heading; não deriva princípios das convenções de código existentes |
| Delta entre execuções | 🟡 | 🟢 | `context_delta.py` já faz ADDED/MODIFIED/REMOVED por artefato |
| Specs delta / living spec | 🔴 | 🔴 | Não existe modelo de "change delta" estilo OpenSpec sobre specs vivas |
| Testes de caracterização antes de mexer | n/a | 🔴 | Nenhuma fase cria golden-master antes de `implement` |
| Scaffolding / escolha de stack | 🔴 | n/a | `templates/tech-stack.md` tem 785 bytes, nenhuma pergunta de stack no intake |
| Gates de qualidade | 🔴 repo vazio = zero gates | 🟢 auto-detectados | Princípio VIII: só detecta, nunca cria → greenfield começa sem gate |
| Adoção parcial (um módulo/subdir) | n/a | 🔴 | Tudo é escopado na raiz |
| Converge loop pós-implement | 🔴 | 🔴 | Spec Kit já tem `/speckit.converge` (skill instalada aqui), mas o protocolo não o usa |

**Veredito**: o Spec Master é hoje um orquestrador **greenfield-first com bom
suporte a "re-execução" (resume/delta)**, mas **não a "código legado"**. O mercado
(OpenSpec, BMAD `document-project`, Kiro steering, GSD `map-codebase`, guia
oficial do Spec Kit para projetos existentes) trata brownfield como trilha
própria: **mapear → constitution por evidência → mudança delimitada → converge**.

### 2.2 Achados colaterais da auditoria (corrigir independentemente das opções)

| # | Achado | Local |
|---|---|---|
| H1 | 21 módulos de teste importam `pytest` → `unittest discover` falha; viola Princípios II/III | `spec-master/tests/test_graph_*`, `test_knowledge_*`, `test_traceability_graph` |
| H2 | `pytest` a partir da raiz falha com `No module named '_pathfix'` (precisa `-o pythonpath=spec-master/tests`) | config de testes |
| H3 | Discovery não detecta o próprio repo (sem `pyproject.toml` raiz) → nenhum gate roda no dogfood | `lib/discovery.py` |
| H4 | `_infer_owner` casa substring ("ui" ∈ "build", "api" ∈ "capital") | `lib/team_model.py:472-506` |
| H5 | Tarefas encadeadas em série por padrão → mata as lanes paralelas | `lib/team_model.py:547-549` |
| H6 | Analyze "light" (tiers XS/S) é só rótulo; nenhum código o consome | `lib/risk_profile.py` |
| H7 | Tokens sempre `0` em `rounds.json` (9/9 linhas) → calibração cai para duração | `lib/metrics.py`, `lib/calibration.py` |
| H8 | `metrics record-round` só imprime a linha; o agente precisa fazer append manual | `lib/cli.py:455-472` |

---

## 3. Diagnóstico de performance (DISCOVERED_FROM_CODEBASE)

O gargalo **não é CPU**: cada chamada da CLI custa ~75 ms (import ansioso de todos
os módulos) e a suíte roda 631 testes em ~2 s. O custo real está em:

1. **Round-trips do agente**: ~35–60 chamadas sequenciais de CLI por feature
   (14 `state transition`, `metrics record-round` + append manual, `traceability add`
   por requisito, `knowledge get` por papel…). Cada chamada é um turno de tool do LLM.
2. **Tokens de protocolo**: `PROTOCOL.md` tem 49,8 KB (~12,5k tokens) e o SKILL
   manda ler inteiro antes de agir; `README.md` 31,6 KB; playbooks ~45 KB.
3. **Snapshot O(repo) por tentativa de fase**: `phase_contracts.snapshot()` faz
   `rglob("*")` + sha256 de todo arquivo antes e depois de cada fase guardada,
   filtrando `node_modules/.git/.venv` só *depois* de percorrer; `dist/ build/ target/`
   nem são ignorados (`lib/phase_contracts.py:93-140`). É o hotspot em brownfield grande.
4. **Dashboard re-renderiza o grafo inteiro a cada evento** (`lib/hooks.py:162-166`,
   `lib/dashboard.py:385-403`).
5. **MCP server sobe um `python cli.py` por tool call** (`mcp/spec_master_mcp.py:613-615`).
6. **Sem roteamento de modelo/effort por fase**: tudo roda no modelo da sessão.
   O mercado (`code.claude.com/docs/en/costs`) recomenda Haiku/effort baixo para
   tarefas rotineiras, Sonnet para workers, Opus só para plano/arquitetura, e
   `subagentPromptCacheTtl: 1h` em fan-outs longos.

---

## 4. Estado do multi-agente (DISCOVERED_FROM_CODEBASE)

- `worktree.py` cria worktrees reais, mas **nunca lança agente**.
- `team_workstreams.py` é contabilidade de review/integração.
- Único spawn real: `opencode run` em `phase_runner.py`/`opencode_runner.py`,
  dirigido por `controller.py` **estritamente em sequência**.
- `runtime_contract.py` declara `subagent_concurrency: "host_optional"` → a
  paralelização hoje depende do agente host "obedecer à prosa" do protocolo.

**Mercado (MARKET)**: multi-agente rende em trabalho largo e independente
(pesquisa, reviews com lentes diferentes, features em camadas distintas) e
queima tokens em trabalho sequencial no mesmo arquivo. Anthropic reporta ~4× tokens
para agentes e ~15× para multi-agente; Opus lead + Sonnet workers foi +90,2% no
eval interno (anthropic.com/engineering/multi-agent-research-system). Agent teams
recomendam 3–5 teammates, 5–6 tarefas cada, ownership de arquivos por teammate.

---

## 5. Telemetria de tokens (DISCOVERED + MARKET)

| Fonte | Tempo real | Atribuição por fase/agente | Estabilidade | Setup |
|---|---|---|---|---|
| Transcript JSONL `~/.claude/projects/<slug>/<session>.jsonl` (+ `<session>/subagents/agent-*.jsonl`) | sim (tail) | via janela de tempo + `agent_id` | **formato interno**, pode mudar | zero |
| Hooks `SubagentStop` (`agent_transcript_path`), `PostToolUse` do Agent | na fronteira do subagente | **exata por subagente** | documentado | hook |
| OTel `claude_code.api_request` / `claude_code.token.usage` (`skill.name`, `agent.name`, `query_source`) | 5 s logs / métricas configurável | por skill/agente | **documentado e versionado** | env vars + receptor |
| Statusline JSON (`cost.total_cost_usd`, `context_window.*`) | 300 ms | só sessão | documentado | script |
| Codex: `[otel]` em config.toml, `codex exec --json` (`token_count`) | sim | por turno | parcialmente verificado | config |
| Copilot CLI: OTel do SDK | ? | ? | **não verificado** | — |

Verificado localmente nesta sessão: o JSONL atual traz `message.usage` com
`input_tokens`, `output_tokens`, `cache_creation_input_tokens`,
`cache_read_input_tokens` e `message.model`.

Restrições: o schema `schemas/metrics-round.schema.json` é fechado
(`additionalProperties: false`) → incluir cache/model exige bump de versão.
`cost_usd` do Claude Code é estimativa client-side, não faturamento.

---

## 6. Plano de implementação com opções

Ordem recomendada: **medir antes de otimizar** → a telemetria (Onda 1) entra
antes de performance (Onda 2), para que cada ganho seja comprovado em tokens/min.

### Onda 0 — Higiene (sem opção, pré-requisito)

H1–H8 da seção 2.2. Destaques: converter testes pytest → unittest; `record-round
--append`; ignorar diretórios durante o walk; corrigir `_infer_owner` por token.

### Onda 1 — Ledger de tokens + visibilidade sempre ligada

Escolha a **fonte** (T):

| Opção | Descrição | Prós | Contras |
|---|---|---|---|
| **T1** Transcript tail | `lib/token_ledger.py` (stdlib) lê JSONL incrementalmente com offset em `.spec-master/metrics/ledger.state.json`; atribui por janela de fase (`started_at/ended_at`) e `agent_id` | zero setup, funciona hoje, retroativo | formato interno do Claude Code |
| **T2** OTel receiver | `lib/otel_receiver.py` (stdlib `http.server`, OTLP/HTTP **JSON**) recebe `api_request`; Spec Master injeta `OTEL_*` nas sessões que lança | documentado, atribui por `skill.name`, serve Codex também | exige env vars; latência de export |
| **T3** Híbrido ⭐ | Hooks `SubagentStart/Stop` gravam eventos de atribuição (fase/feature/agente) em `.spec-master/events.jsonl`; números vêm do T1 por padrão e do T2 quando OTel estiver ligado; adapters por runtime (claude-code, codex, opencode) atrás de uma interface | atribuição exata + zero setup + caminho documentado | mais peças |

Em qualquer opção: `metrics record-round --from-ledger` preenche tokens reais
(schema v2 com `cache_read_tokens`, `cache_creation_tokens`, `model`, `cost_usd_estimate`);
**statusline do Spec Master** (`feature · fase · tier · tokens · $ · cache hit · ctx%`)
sempre visível no terminal; `calibration.py` volta a calibrar por tokens reais.

### Onda 2 — Performance

Itens independentes (pode escolher vários):

| Id | Item | Ganho esperado | Esforço |
|---|---|---|---|
| P1 | **Comando composto** `step` (transition + record-round + traceability + delta numa chamada, entrada JSON) | −60–70% das chamadas de CLI por feature | M |
| P2 | **Protocolo fatiado**: `PROTOCOL.md` vira núcleo curto (~3k tokens) + seções sob demanda (`protocol get --section team-mode`) | −~9k tokens por sessão | M |
| P3 | **Roteamento modelo/effort por fase** declarado em `risk_profile` (ex.: tasks/analyze → Sonnet/effort baixo; plan/architecture → Opus) emitido como dica no prompt/frontmatter do subagente | custo/fase ↓, cache ↑ | S |
| P4 | Snapshot com poda no walk (`os.walk` + ignore antes de descer, inclui `dist/ build/ target/`) e cache por mtime | brownfield grande: segundos → ms | S |
| P5 | Dashboard incremental (debounce + grafo em cache) | menos I/O por evento | S |
| P6 | MCP in-process (importa `lib/` em vez de subprocess) + imports lazy na CLI | −75 ms/call | S |

### Onda 3 — Dashboard React em tempo real

| Opção | Descrição | Prós | Contras |
|---|---|---|---|
| **D1** ⭐ Servidor stdlib + React buildado | `lib/live_server.py` (stdlib `http.server`, **SSE**) expõe `/api/model` (`dashboard.build_model()`), `/api/events` (tail de `events.jsonl` + `hooks/firings.jsonl` + ledger). UI React+Vite em `dashboard-ui/` (exceção do Princípio IX, fora do import path do core); **bundle buildado commitado** → operador roda `cli.py dashboard serve` sem Node | tempo real de verdade, offline, sem Node em runtime, core segue stdlib | build JS a manter |
| D2 React via CDN, sem build | HTML com React UMD do CDN, consome o mesmo `/api` | mais simples | precisa de rede, contraria o "autocontido/offline" do item 5 do roadmap anterior |
| D3 Backend Node/Bun + WebSocket (estilo disler/Agents Observe) | servidor e UI em JS | ecossistema rico | segunda runtime obrigatória, duplica lógica do core |

Telas propostas (qualquer opção): **Kanban por feature/fase** (planned → in_progress →
review → approved → done), **timeline de rounds**, **tokens ao vivo** (por
fase/agente/modelo, burn rate, cache hit, custo estimado, orçamento do tier),
**lanes de workstreams/agentes** (quem está rodando, em qual worktree),
**gates e hooks disparados**, **mapa de dependências** (reaproveita `render_system_map`).
O HTML estático atual continua como fallback (Princípio VI).

### Onda 4 — Modo Speed ("XGH do bem", TDD first)

Princípio: **velocidade vem de cortar cerimônia, nunca de cortar teste**.

| Opção | Descrição | Prós | Contras |
|---|---|---|---|
| **S1** ⭐ Perfil `speed` dentro do Spec Kit | Novo perfil em `CEREMONY_PROFILES`: `specify` (com clarify inline só para bloqueantes) → `plan+tasks` em uma rodada → **analyze determinístico** (cobertura de traceability + EARS, sem LLM) → **`test-first`** (testes falhando derivados dos critérios de aceite, gate exige RED) → `implement` (gate exige GREEN + gates detectados) → `converge` (`/speckit.converge`). Bloqueado automaticamente quando o eixo de sensibilidade for alto (auth, pagamento, schema, secrets) | respeita Princípio VII (orquestra speckit), reaproveita risk/hooks | mexe no guard sequencial de `state.py` |
| S2 Quick Flow estilo BMAD | Uma única tech-spec autocontida → loop TDD → self-check + review adversarial do diff, pulando `plan/tasks` do Spec Kit | o mais rápido | **conflita com Princípio VII** e com a rastreabilidade; exigiria emenda na constitution |
| S3 Só enforcement TDD | Mantém o fluxo atual, adiciona apenas hooks TDD (bloqueia edição em `src/` sem teste falhando; `Stop` com exit 2 se suíte vermelha) + subagentes test-writer/implementer/refactorer separados | menor risco | ganho de velocidade pequeno |

Em S1/S3 o TDD é **imposto por hook, não por prompt** (padrão tdd-guard do mercado).

### Onda 5 — Modo multi-agente

| Opção | Descrição | Prós | Contras |
|---|---|---|---|
| **M1** ⭐ Subagentes do host guiados por manifest | Core gera `dispatch manifest` por onda (`worktree waves` + `workstreams.json`): pacote, papel, playbook, modelo, worktree, owner/reviewer. O adapter lança subagentes (`Agent` com `isolation: worktree` no Claude Code; equivalentes nos outros hosts) em paralelo por onda; `SubagentStop` grava resultado + tokens; Tech Lead integra | portável entre hosts, usa primitivas documentadas, atribuição de tokens exata | paralelismo depende do host |
| M2 Agent Teams do Claude Code | Papéis viram teammates; task list compartilhada com dependências; `TaskCompleted`/`TeammateIdle` como gates de QA | coordenação nativa rica (mailbox, locks) | **experimental**, só Claude Code, sem resume de teammates, ~7× tokens |
| M3 Runner headless no core | Estende `phase_runner.INTEGRATIONS` com `claude -p` / `codex exec --json` e um pool de processos no core (atrás de fronteira mockável) | paralelismo real e determinístico, tokens via JSON de saída | core passa a gerenciar processos; mais superfície |

Extras opcionais: **best-of-N** em tarefas de tier L/XL (N worktrees, reviewer
escolhe); reviewer obrigatoriamente ≠ owner (já existe); limite de 3–5 agentes
por onda.

### Onda 6 — Trilhas brownfield / greenfield

- **B1 Brownfield intake**: `map-codebase` com 4 leitores paralelos (stack,
  arquitetura, convenções, riscos) → steering docs em `.spec-master/context/` →
  constitution **por evidência** → primeira feature delimitada com fronteiras de
  compatibilidade → fase opcional de **testes de caracterização** → `converge`.
  Discovery passa a varrer sub-pacotes (monorepo) com poda de diretórios.
- **B2 Specs delta** (estilo OpenSpec) sobre specs vivas — opcional, maior.
- **G1 Greenfield bootstrap**: pergunta de stack no intake; proposta (nunca
  automática) de esqueleto + CI + gates mínimos, pois o Princípio VIII só detecta.
- **Adoção parcial** por subdiretório (`--scope path/`).

---

## 7. Dependências entre ondas

```
Onda 0 (higiene)
  └─► Onda 1 (ledger + statusline) ──► Onda 3 (dashboard React consome ledger/eventos)
        └─► Onda 2 (performance, medida em tokens reais)
              └─► Onda 4 (speed) ──► Onda 5 (multi-agente usa perfis/roteamento de modelo)
Onda 6 (brownfield/greenfield) depende só da Onda 0 + P4; pode correr em paralelo a 3–5
```

## 8. Decisões (EXPLICIT, 2026-10-19)

Escolhidas pelo usuário nesta sessão:

- **Multi-agente: M1** — subagentes do host guiados por dispatch manifest.
- **Speed: S1** — perfil `speed` dentro do Spec Kit, TDD imposto por gate.
- **Dashboard: D1** — servidor stdlib SSE + React/Vite com bundle buildado commitado.
- **Execução: via `/spec-master` (dogfood)** — este documento é o context-file.

Não perguntadas, adotadas como default recomendado (INFERRED, podem ser revistas
no `clarify`): **T3** (telemetria híbrida), **P1–P6**, **B1 + G1** (B2 fica no backlog).
Nenhuma delas exige emenda na constitution nem recurso experimental.

## 9. Fora de escopo

- Spec-as-source (Tessl) — mantido fora, como no roadmap anterior.
- Enviar telemetria para serviços externos: tudo local; export OTel continua
  "valida e gera, nunca envia" (Princípio X).
