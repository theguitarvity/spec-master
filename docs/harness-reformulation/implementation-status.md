# Status da implementação

O que da [proposta](proposal.md) está implementado neste branch, o que foi
medido e o que falta. O fluxo padrão do `/spec-master` continua o mesmo
(Princípio VI). Tudo da onda 1 é opt-in.

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
| Invocações inválidas nos documentos lidos por agentes | 2 | **0** de 275 | 0 | `doctor` / `test_protocol_conformance` |
| Skills de fase do Spec Kit detectadas | 0/10 | **10/10** | 10/10 | `discovery scan --path .` |
| Updates perdidos (16 escritas concorrentes) | 6–50% | **0** | 0 | `test_state_integrity` (16 processos de CLI) |
| Promoções aceitas sem artefato | aceitas | **recusadas** (`EvidenceMissing`) | 0 | `test_state_cli`, `test_evidence` |
| `gates detect` no próprio repo / erros no `unittest` | `[]` / 21 | `python3 -m unittest discover -s spec-master/tests` / **0** | ≠ `[]` / 0 | CLI e suíte |
| Rodadas com usage vindo do host | 0/9 | as 9 antigas são `manual-unverified`; o protocolo manda gravar as novas com `telemetry ingest` | 100% das novas | `metrics validate` |
| `PROTOCOL.md` | 49,8 KB | 37,9 KB | — | `wc -c`; referência sob demanda em `spec-master/docs/` |
| Testes | 631 com pytest; com `unittest`, 21 módulos com erro de import | **886** com `unittest`, todos passando | verde | `python3 -m unittest discover -s spec-master/tests` |

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
| Kernel: `lanes`, `step`, cards, `policy`, `hookd`, `verify:post`, proveniência v1 | feito | `lib/kernel/` (998 LOC; orçamento 2.500) |
| `step next\|begin\|end\|widen\|pause\|resume` | feito | `kernel/step.py` |
| Cards (roteador ≤5 KB, core, patch, bugfix, escalada) | feito | `spec-master/cards/` (roteador 1,7 KB) |
| Plugin do Claude Code (skill de lane, `hooks.json`) | feito, `claude plugin validate` passa | `spec-master/.claude-plugin/`, `.claude-plugin/marketplace.json` |
| Instalação dos hooks por projeto | feito (`harness install-hooks`, `harness mode`) | `kernel/install.py` |
| Hooks em audit por padrão, bloqueio por política | feito | `.spec-master/policy.json` `hooks_mode` |
| Lane Patch de ponta a ponta, com bugfix | feito | `test_kernel_step` (git real, gate real, regressão no commit base) |
| Evals adversariais de replay | feito | `test_kernel_hookd`: implementar antes do analyze, editar `state.json`, comando destrutivo, parar sem verificar, retomar após compactação |
| `doctor` no CI | feito | `doctor run --path .` |
| Proposta de emenda da constitution | feito, **não aplicada** | [`constitution-amendment.md`](constitution-amendment.md) |

### Números da onda 1

- Instruções para fazer um patch: entrypoint + `router.md` + `core.md` + card
  de implementação ≈ 7,3 KB, contra 55,1 KB do bootstrap do fluxo completo
  (meta ≤8 KB).
- `hookd` no PreToolUse: 6 módulos, 666 LOC importadas, **~40 ms p50**
  (máximo ~41–53 ms), medido pelo `doctor` com `-X importtime` (orçamento
  1.500 LOC e 100 ms p50; a proposta pede p95 ≤50 ms).
- Plugin: **~94 tokens** fixos por sessão; a skill de lane custa ~460 tokens
  quando é chamada.
- Patch: 3 chamadas estruturais (`lane triage`, `step begin`, `step end`), 0
  gates humanos, nota da mudança com meta de 1 KB (recusada acima de 4 KB).

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
2. **Decidir a emenda** da constitution
   ([`constitution-amendment.md`](constitution-amendment.md)). Sem ela, Patch
   e Standard continuam opt-in.
3. **Período de audit dos hooks.** Duas semanas em `audit`, medindo falsos
   bloqueios em `.spec-master/hooks/decisions.jsonl` (meta ≤2%), antes de
   passar para `block`.
4. **Pendências da onda 1**:
   - fatiar o `PROTOCOL.md` do fluxo padrão num roteador ≤5 KB + cards (hoje
     só o fluxo por lane tem roteador; o padrão foi podado para 37,9 KB);
   - compartilhar a função de próximo passo com o `controller`;
   - `init.sh link --hooks` (hoje o caminho é `harness install-hooks` ou o
     plugin);
   - agents no plugin.
5. **Ondas 2 a 4** (Standard, subagentes com `PhaseResult`, `claude plugin
   eval` com braço sem plugin, compat do Spec Kit 1.x, paralelismo):
   não começaram. Cada uma depende do go/no-go da anterior.
6. **Avisos atuais do `doctor`** (esperados):
   - `step_path_budget`: 4.803 LOC contra a meta de 4.500 para a onda 3;
   - `evidence`: 3 features do dogfood têm fases `PASSED` de antes da
     promoção por evidência, sem evidência verificada.
