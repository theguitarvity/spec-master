# Status da implementação

O que da [proposta](proposal.md) está implementado no `main`, o que foi
medido e o que falta. O fluxo padrão do `/spec-master` continua o mesmo
(Princípio VI). Tudo da onda 1 é opt-in. A emenda da constitution (2.0.0)
foi aprovada e aplicada, e os hooks estão em auditoria neste repositório.

## Onda 0: medir e parar o desperdício

| Entregável | Status | Onde |
|---|---|---|
| Telemetria do host (transcript do Claude Code e JSON do `claude -p`) | feito | `lib/telemetry.py`, `telemetry locate\|ingest` |
| Schema de métricas v2, retrocompatível | feito (1.1.0; campos novos opcionais) | `schemas/metrics-round.schema.json`, `metrics_export.validate_rounds` |
| Rodadas r1–r9 marcadas como `manual-unverified` | feito | `.spec-master/metrics/rounds.json` |
| `rounds.json` gravado pelo core, nunca à mão | feito (`--append`: valida, grava atômico, com lock; o hook nega edição direta) | `metrics record-round`, `telemetry ingest` |
| Runner do baseline (3 casos × 3 execuções × 2 braços) | construído, **não executado** | `lib/baseline.py`, `baseline plan\|run\|summarize` |
| Dieta de saída do CLI e `state show --summary` | feito | JSON compacto, ack no `transition`, `budget file` só com ids |
| Lock e `mkstemp` no `state.json` | feito | `state.locked`, `state.transaction` |
| Upsert só de metadados | feito (`--import-unverified --reason` para o histórico) | `state.upsert_feature_metadata` |
| Contratos de fase escopados por feature | feito | `phase_contracts.scoped_patterns`, `controller` |
| Promoção por evidência | feito | `lib/evidence.py`, `state transition`, `state evidence` |
| Tentativas por feature e fase | feito | `controller._attempt_key` |
| `gates.json` declarativo e detecção de `unittest` | feito | `quality_gates` |
| Suíte só com `unittest` (21 erros de import) | feito | testes convertidos |
| Bug de arestas do `graph enrich` | corrigido | `graph/store.py`, `graph/enrichment.py` |
| Fim da inflação de tier | feito | `risk_profile`, regra `irreversible` em `hooks.py` |
| Poda do protocolo e teste de conformidade | feito | `PROTOCOL.md`, `docs/protocol-reference.md`, `docs/team-mode.md`, `doctor` |
| Discovery via `.specify/integration.json`, pin do Spec Kit | feito (`v0.16.4`, faixa `>=0.16.4,<1.1`) | `discovery.py`, `init.sh` |

### KPIs medidos

| Indicador | Antes | Agora | Meta | Como foi medido |
|---|---|---|---|---|
| stdout do CLI por feature (58 chamadas mandatadas) | 100.833 B | **14.138 B** (−86%) | ≤15 KB | mesmo `sim_feature.sh` da avaliação, com artefatos reais da feature para a evidência passar |
| Escaladas espúrias S→M (003–005) | 3/3 | **0/3**; `optional-pr-open-step` sobe para M | 0/3 | replay do `risk classify` |
| Invocações inválidas nos documentos lidos por agentes | 2 | **0** de 282 | 0 | `doctor` / `test_protocol_conformance` |
| Skills de fase do Spec Kit detectadas | 0/10 | **10/10** | 10/10 | `discovery scan --path .` |
| Updates perdidos (16 escritas concorrentes) | 6–50% | **0** | 0 | `test_state_integrity` (16 processos de CLI) |
| Promoções aceitas sem artefato | aceitas | **recusadas** (`EvidenceMissing`) | 0 | `test_state_cli`, `test_evidence` |
| `gates detect` no próprio repo / erros no `unittest` | `[]` / 21 | `python3 -m unittest discover -s spec-master/tests` / **0** | ≠ `[]` / 0 | CLI e suíte |
| Rodadas com usage vindo do host | 0/9 | as 9 antigas são `manual-unverified`; o protocolo manda gravar as novas com `telemetry ingest` | 100% das novas | `metrics validate` |
| `PROTOCOL.md` | 49,8 KB | 37,9 KB | — | `wc -c`; referência sob demanda em `spec-master/docs/` |
| Testes | 631 com pytest; com `unittest`, 21 módulos com erro de import | **945** com `unittest`, todos passando, em Python 3.10 a 3.13 | verde | `python3 -m unittest discover -s spec-master/tests`, também no CI |

### Limites da telemetria (medidos, não resolvidos)

- As linhas de subagentes no transcript guardam o usage do começo do stream:
  input e cache são exatos, `output_tokens` é um limite inferior. A linha diz
  isso nas `notes`.
- Chamadas auxiliares do host (modelos menores) não aparecem no transcript.
  Totais exatos, com custo, vêm do modo headless (`modelUsage`,
  `total_cost_usd`).
- Contra o snapshot de custo do próprio host, os tokens de cache lidos do
  transcript ficaram a 0,27% (leitura) e 0,013% (criação). A meta de "2%" só
  vale para cache vindo do transcript.
- Linhas medidas pelo host fora de ordem geram aviso, não erro: rodadas
  paralelas são gravadas na ordem em que terminam.
- Calibração: linhas `manual-unverified`, e linhas com `source` mas 0 tokens,
  nunca entram. Linhas v1 sem `source` e com 0 tokens ficam de fora quando o
  arquivo tem qualquer linha com `source`, ou com `--require-measured`. Um
  arquivo só com linhas v1 mantém o comportamento antigo e sai marcado.

## Onda 1: impor o harness e abrir o Patch (opt-in)

| Entregável | Status | Onde |
|---|---|---|
| Kernel: `lanes`, `step`, cards, `policy`, `hookd`, `verify:post`, proveniência v1 | feito | `lib/kernel/` (1.212 LOC; orçamento 2.500) |
| `step next\|begin\|end\|widen\|pause\|resume` | feito | `kernel/step.py` |
| Cards (roteador ≤5 KB, core, patch, bugfix, escalada) | feito | `spec-master/cards/` (roteador 1,7 KB) |
| Plugins para oito hosts (duas skills, hooks no dialeto de cada host, MCP com `harness_entrypoint`) | feito, 0.3.0; validado nas CLIs de cada host (tabela abaixo) | `lib/packaging.py`, `kernel/hosts.py`, `spec-master/.*-plugin/`, raiz do repositório |
| Instalação dos hooks por projeto | feito (`harness install-hooks`, `harness mode`) | `kernel/install.py` |
| Hooks em audit por padrão, bloqueio por política | feito | `.spec-master/policy.json` `hooks_mode` |
| Lane Patch de ponta a ponta, com bugfix | feito | `test_kernel_step` (git real, gate real, regressão no commit base) |
| Evals adversariais de replay | feito | `test_kernel_hookd`: implementar antes do analyze, editar `state.json`, comando destrutivo, parar sem verificar, retomar após compactação |
| `doctor` no CI | feito: `.github/workflows/ci.yml` roda a suíte e o `doctor` em Python 3.10 a 3.13 | `doctor run --path .` |
| Emenda da constitution (Princípio VII e *Development Workflow*) | **aprovada e aplicada** em 2026-09-28 (versão 2.0.0) | [`constitution-amendment.md`](constitution-amendment.md) |
| Auditoria dos hooks | **em andamento neste repositório desde 2026-09-28** (modo audit, hooks em `.claude/settings.json`) | `harness audit`, `kernel/audit.py`, `.spec-master/hooks/audit.jsonl` |

### Números da onda 1

- Instruções para fazer um patch: entrypoint + `router.md` + `core.md` + card
  de implementação ≈ 7,3 KB, contra 55,1 KB do bootstrap do fluxo completo
  (meta ≤8 KB).
- `hookd` no PreToolUse: 7 módulos (com o adaptador de hosts), 827 LOC
  importadas, **~39–43 ms p50**, medido pelo `doctor` com `-X importtime`
  (orçamento 1.500 LOC e 100 ms p50; a proposta pede p95 ≤50 ms).
- Plugin: **~340 tokens** fixos por sessão (1,3 KB: o frontmatter das duas
  skills, o schema de `harness_entrypoint` e as instruções do servidor MCP).
  Com as 94 tools, a lista do MCP passaria de 49 KB (~12 mil tokens) em cada
  sessão de um host que carrega os schemas de uma vez; por isso os plugins
  sobem o servidor com `--tools entrypoint`. Chamar uma skill custa ~530
  tokens (o `SKILL.md` e a resposta de `harness_entrypoint`).
- Patch: 3 chamadas estruturais (`lane triage`, `step begin`, `step end`), 0
  gates humanos, nota da mudança com meta de 1 KB (recusada acima de 4 KB).

### Plugins por host (0.3.0)

Um gerador ([`lib/packaging.py`](../../spec-master/lib/packaging.py)) escreve
os manifestos, hooks e skills de todos os hosts; o `doctor` e
`test_packaging` falham se um arquivo divergir. O `hookd` fala o protocolo de
cada host ([`kernel/hosts.py`](../../spec-master/lib/kernel/hosts.py)).
Validação feita em 2026-09-30, com as CLIs reais instaladas numa `HOME`
descartável:

| Host | Versão | Como foi validado | Resultado |
|---|---|---|---|
| Claude Code | 2.1.285 | `claude plugin validate --strict` (plugin e marketplace), instalação pelo marketplace, `claude mcp list` | passou; MCP conectado |
| OpenAI Codex | 0.159.1 | `plugin marketplace add` + `plugin add`; `hooks/list`, `skills/list` e `mcpServerStatus/list` pelo app-server; hook com `apply_patch` simulado | 2 skills, 4 hooks (aguardando a revisão do usuário, como o Codex exige), MCP 0.3.0; `deny` correto |
| GitHub Copilot CLI | 1.0.89 | `plugin marketplace add` + `plugin install`; `copilot mcp get` | 2 skills e o MCP; os hooks conferem com a referência de hooks (disparar exige login) |
| Gemini CLI | 0.62.0 | `extensions validate`, `extensions install`, sessão headless com chave falsa | 2 skills, MCP conectado, o `SessionStart` rodou o `hookd` |
| Antigravity | 1.2.13 | `agy plugin validate` + `agy plugin install`; payloads simulados no plugin instalado | 2 skills, MCP e hooks; `deny`/`ask` corretos e `{}` sem objeção |
| Qwen Code | 0.24.7 | `extensions install`, `harness install-hooks --host qwen`, sessão headless | 2 skills; o MCP achou o projeto pelas *roots*; 4 hooks e o `SessionStart` rodou o `hookd` |
| Cursor | 2026.09.28 | validador oficial do repositório `cursor/plugins` | passou (rodar o agente exige login) |
| Kiro | — | sem CLI no ambiente: manifesto contra o schema Agent Plugins 1.0.0; hooks do instalador com payloads simulados | `deny` sai com código 2; engine ausente não bloqueia |
| VS Code | — | não testado (lê o mesmo marketplace do Claude Code) | — |

Depois do push, Claude Code, Codex, Copilot CLI, Gemini CLI e Antigravity
instalaram direto do GitHub (commit `2b98c80`), com o mesmo resultado, e o
CI passou em Python 3.10 a 3.13. O Qwen Code achou o marketplace no GitHub,
mas roda o `git clone` sem as variáveis de proxy, e este ambiente só sai pela
proxy: instalado de um clone do mesmo commit, deu o mesmo resultado. Numa
máquina com acesso direto, o clone do repositório público funciona.

Achados que mudaram o desenho:

- O Qwen Code carrega como Agent Plugins qualquer pacote com `plugin.json`
  de `$schema` 1.0.0 e aí ignora hooks; o Kiro exige esse manifesto. Os dois
  recebem os hooks por projeto (`install-hooks --host qwen|kiro`).
- Codex e Copilot preferem um manifesto Agent Plugins quando ele existe, e o
  Codex 0.159.1 não carrega hooks nesse formato: por isso ele fica na raiz e
  o plugin de `spec-master/` mantém os manifestos nativos.
- No Antigravity, `allow` num `PreToolUse` aprova a ferramenta sem perguntar
  ao usuário: o hook responde `{}` quando não tem objeção.
- Codex e Antigravity sobem o MCP na pasta do plugin sem informar o projeto;
  com `--tools entrypoint` isso não importa, porque a única tool não toca o
  projeto.

### Correções feitas na revisão final

- `step end --no-gates` podia marcar `PASSED` sem rodar gate nenhum. Agora
  essa opção nunca passa (fail-closed).
- O `hookd` só registra decisões em projetos que já têm `.spec-master/`. Um
  plugin habilitado em todo lugar não deixa rastro em outros repositórios.
- `is_test_path` passou a reconhecer nomes CamelCase (`CalcTest.java`,
  `CalcTests.cs`) sem voltar a confundir `latest.py` com teste.
- O `doctor` conta o próprio `hookd.py` no orçamento do PreToolUse.
- `harness mode` define o modo sem duplicar os hooks quando eles já vêm do
  plugin.
- Os arquivos de lock e o log de auditoria dos hooks ficam fora do
  `git status` do projeto: o core cria `.spec-master/.gitignore` na primeira
  vez e nunca reescreve um que já exista.

## O que falta

1. **Rodar o baseline.** Isso gasta dinheiro de verdade e depende da sua
   decisão. O go/no-go da onda 0 (o fluxo atual custa ≥2× o braço direto?)
   só sai com essa medição:
   `baseline plan --cases <arquivo> --max-budget-usd <teto>` mostra a matriz
   e o gasto no pior caso; `baseline run ... --yes` executa.
2. **Fechar a auditoria dos hooks** (começou em 2026-09-28). No dia 14
   (2026-10-12), `harness audit --path .` diz se os bloqueios ficaram em até
   2% das decisões. Se ficaram, ou se a revisão da lista `flagged` mostrar
   que os falsos bloqueios ficaram nesse limite,
   `harness mode --project . --mode block` liga o bloqueio. Até lá, cada
   sessão salva o próprio resumo (`--save`) antes do último commit.
3. **Pendências da onda 1**:
   - fatiar o `PROTOCOL.md` do fluxo padrão num roteador ≤5 KB + cards (hoje
     só o fluxo por lane tem roteador; o padrão foi podado para 37,9 KB);
   - compartilhar a função de próximo passo com o `controller`;
   - `init.sh link --hooks` (hoje o caminho é `harness install-hooks` ou o
     plugin);
   - agents no plugin.
4. **Plugins**: submeter aos catálogos oficiais (Claude, Codex, Cursor,
   galeria do Gemini, marketplace do Antigravity) é uma decisão sua; o
   Codex hoje recusa plugins com hooks no portal. Faltam rodadas reais no
   Cursor, Copilot, VS Code e Kiro, que exigem login ou o aplicativo. O
   Antigravity não tem `SessionStart`; o `PreInvocation` pode fazer esse
   papel quando a semântica de `invocationNum` estiver documentada.
5. **Ondas 2 a 4** (Standard, subagentes com `PhaseResult`, `claude plugin
   eval` com braço sem plugin, compat do Spec Kit 1.x, paralelismo):
   não começaram. Cada uma depende do go/no-go da anterior.
6. **Avisos atuais do `doctor`** (esperados):
   - `step_path_budget`: 4.830 LOC contra a meta de 4.500 para a onda 3;
   - `evidence`: 3 features do dogfood têm fases `PASSED` de antes da
     promoção por evidência, sem evidência verificada.
