# Evidências — avaliação multiagente do Spec Master

> Relatórios integrais dos 6 analistas independentes que alimentaram a
> [proposta de reformulação](proposal.md). Cada analista trabalhou em modo
> somente leitura; comandos que gravam estado rodaram em cópias descartáveis
> (referidas como `<scratch>`). Afirmações marcadas como HIPÓTESE ou NÃO
> VERIFICADO pelos próprios analistas foram mantidas como estão. O avaliador
> reconferiu as afirmações críticas (ver Apêndice A da proposta).
>
> Os scripts de medição citados (por exemplo `cost_model.py`, `sim_feature.sh`,
> `simulate.py`, `bench.py` e o protótipo de hook `sm_guard.py`) eram
> descartáveis e não foram versionados. A Onda 0 da proposta os substitui por
> telemetria real do host e por um `doctor` no CI. Caminhos como
> `~/.claude/projects/...` se referem a transcripts de sessão do host.
>
> Custos em US$ usam duas tabelas de preço de referência: **preço A** =
> US$4/US$20 por MTok de input/output (cache read US$0,20; cache write 1,25×);
> **preço B** = US$5/US$25 por MTok (cache read 0,1×).

## Índice

- [Custo do fluxo agentic](#custo-do-fluxo-agentic)
- [Overengineering e cerimônia](#overengineering-e-cerimônia)
- [Maturidade de harness](#maturidade-de-harness)
- [Performance do core Python](#performance-do-core-python)
- [Acoplamento com o Spec Kit](#acoplamento-com-o-spec-kit)
- [Benchmark de mercado](#benchmark-de-mercado)

---

## Custo do fluxo agentic

### Resumo

O gargalo de performance do Spec Master não está no core Python: cada chamada leva cerca de 0,1 s e o snapshot leva 0,9 s mesmo com 57k arquivos. O gargalo está no laço agentic, em quatro fatores: tamanho do contexto, número de turnos, artefatos gerados como tokens de saída e gates humanos síncronos.

Para uma feature pequena (tier S na intake, ex.: 003), o caminho no Claude Code carrega:
- 55 KB fixos por sessão: o PROTOCOL.md é lido inteiro por ordem do entrypoint, e 73–79% dele não serve à fase em execução;
- ~106 KB de instruções Spec Kit/Spec Master por feature;
- 58 chamadas CLI obrigatórias, com 101 KB de stdout. 74% desse volume é eco de conteúdo do `budget file`.

A feature produz 9 artefatos (47,7 KB), 4,3x o tamanho do código+testes. O modelo reprodutível estima +62k–143k tokens de contexto e 8,8–19,3M tokens de input cumulativo por feature (~US$6–9 em preço A). Esse input cresce quadraticamente quando várias features rodam na mesma sessão, e 9 de 10 features eram independentes.

A cerimônia se autoalimenta:
- os artefatos do próprio Spec Kit elevam o tier de S para M em 3/3 features, o que força mais um analyze;
- o clarify não mudou nada em 3/3;
- quando a calibração receber tokens reais, vai apertar os thresholds, ou seja, mais cerimônia.

As métricas atuais não medem nada: tokens 0, durações zeradas ou sintéticas e sobrepostas, 0/9 rodadas atribuídas a feature/tier. Mesmo assim, o host já registra usage real (transcript JSONL, OTel, `claude -p --output-format json`), e isso foi verificado localmente.

Proposta de harness, em cinco passos:
1. Ingerir a telemetria do host.
2. Trocar o plumbing por um comando `step` que devolve phase cards.
3. Fatiar o protocolo e o contexto por fase e por feature.
4. Criar um trilho lite para XS/S, com o Spec Kit virando formato de exportação.
5. Isolar o contexto por fase e paralelizar as ondas.

Ganho combinado estimado para XS/S: −90% de input cumulativo, −74% de custo, 0 gates.

### Métricas

| Métrica | Valor | Método |
|---|---|---|
| Custo atual por feature (resumo; feature S típica = specs/003) | ~26,4k tok de instruções Spec Kit/SM + 13,8k de protocolo/entrypoint + 15,1k de bootstrap de workflow; 9 artefatos (47,7 KB, ~11,9k tok de saída) para 11,2 KB de código+testes; 58 chamadas CLI; ~110–160 turnos; contexto +62k–143k tok; input cumulativo 8,8–19,3M tok (central 13,0M); ~US$6,3–8,7 (preço A) / US$11,1–14,0 (preço B); 0–9 gates humanos | cost_model.py (bytes/4 dos arquivos reais do repo) + sim_feature.sh; T (turnos), saída de 150k tok e prompt de sistema de 20k tok são HIPÓTESE |
| Carga fixa por sessão (entrypoint + PROTOCOL.md + adapter Claude) | 55.130 B ≈ 13,8k tok (PROTOCOL.md = 49.778 B) | wc -c em .claude/commands/spec-master.md, spec-master/PROTOCOL.md, spec-master/adapters/claude-code.md |
| Fração do PROTOCOL.md relevante por fase | 21–27% (10,6 KB no plan, 12,2 KB no validate, 13,5 KB no specify com risco); 26% (12,9 KB) nunca é usado em runtime no Claude Code | Divisão por headings (python) + matriz fase×seção (invariantes, laço por feature, hooks, métricas, risco, gates) |
| Instruções Spec Kit + Spec Master por feature | 105.667 B ≈ 26,4k tok (6 SKILL.md = 81,4 KB; 6 prompts = 6,9 KB; 3 templates .specify = 17,4 KB); boilerplate de extension hooks ≈ 3,8 KB por skill (~23 KB/feature), inerte porque não existe .specify/extensions.yml | wc -c + medição dos blocos pré/pós-hooks de cada SKILL.md; ls .specify/extensions.yml (inexistente) |
| Chamadas CLI obrigatórias por feature (M, 1 ciclo de repair, 10 requisitos, 3 gates) | 58 chamadas; 100.833 B de stdout (~25,2k tok); 7,3 s de CPU; budget file = 74% dos bytes (12,4 KB por chamada); state transition ~1–1,2 KB × 14 | sim_feature.sh executado na cópia do repo no scratchpad (só as chamadas mandatadas pelo PROTOCOL.md, sem LLM) |
| Latência do core determinístico | 0,10–0,18 s por chamada; hooks +10 ms (120 vs 110 ms); dashboard render 0,11 s; phase snapshot 0,016 s (344 arquivos) / 0,87 s (57k arquivos sintéticos) | date +%s%N, média de 5 repetições; repo sintético com node_modules/dist no scratchpad |
| Razão artefato/código | 003: 4,3x; 004: 5,4x; 005: 5,1x em bytes (3,0–3,75x em linhas); agregado 003+004: 3,8x em bytes / 2,95x em linhas; 6,4x incluindo state/contexto/docs | Bytes/linhas adicionados em git show 06dcef0, 1e37327, 6c31029 (code+tests vs specs/ e .spec-master/) |
| Crescimento do contexto por feature (sessão única) | +62k tok (dedupe perfeito) a +143k tok (leitura literal das skills) | cost_model.py: soma por fase das leituras mandatadas + artefatos + plumbing |
| Input cumulativo por feature | 8,8–19,3M tok (central 13,0M) na 1ª feature; 26,3M na 2ª e 39,6M na 3ª feature da mesma sessão | I = T × (2·C0 + ΔC)/2, com C0 = 48,9k (20k de sistema HIPÓTESE + 28,9k medidos) e T = 110–160 |
| Custo estimado por feature | preço A: US$6,33 sem expiração de cache; US$8,73 com 5 gates >5 min. preço B: US$11,13–14,01 | Preços da skill claude-api (preço A $4/$20, cache read $0,20, write 1,25x; preço B $5/$25, read 0,1x); saída de 150k tok é HIPÓTESE |
| Gates humanos | Até 9 por feature (specify: 1 lote de ≤3 perguntas; clarify: ≤5 perguntas uma por vez; analyze: oferta de remediação; implement: gate de checklist; PR em Git Flow) + 1–3 por workflow | Leitura de speckit-*/SKILL.md e PROTOCOL.md (Steps 0, 2, 4 e PR) |
| Qualidade das métricas registradas | 9 rodadas; tokens 0 em todas; 4/9 com duração <1 s; 5/9 com horários redondos, sobrepostos e cronologicamente impossíveis; 0/9 com feature_id/tier; calibrate rounds_used=0; validate: valid, 0 warnings | Análise de .spec-master/metrics/rounds.json + metrics summarize/validate/calibrate no scratch |
| Escalonamento de tier induzido pela cerimônia | 3/3 features: S na intake → M no pre_implement, com escalated=true e rerun_phases=['analyze'] | risk classify --stage intake/pre_implement (dry-run) no scratch |
| Fases sem efeito observável | clarify sem efeito em 3/3 (nenhum spec.md tem seção Clarifications; r2: No spec changes); analyze com 1 ciclo em 3/3, sendo 1 só de formato (id T005a) | grep em specs/00{3,4,5}/spec.md + notas do rounds.json |
| Paralelismo disponível vs. usado | 9/10 features na onda 0; execução real serial numa sessão; pacotes L em cadeia 6/6 (paralelismo 1,0) | worktree waves com as dependências do state.json; risk work-packages --tier L |
| Contexto normalizado vs. seção da feature | 28,1 KB carregados no specify vs. 1,0–3,7 KB (média ~1,6 KB) da seção da feature em app-features.md | Divisão de .spec-master/context/app-features.md por '### Feature' |
| Team Mode (feature L) | 6 papéis; ~111,6 KB de conteúdo + ~37 KB de metadados ≈ 37k tok por carga única (o protocolo pede carga a cada uma das até 12 instanciações) | total_content_chars de knowledge for-role por papel + bytes da saída JSON |
| Throughput indicativo (experimento natural, não controlado) | Fluxo completo: ~13 linhas de código+testes/min (features 1–2, ≥43,7 min). Fora do fluxo: ~130 linhas/min (itens 3–16, 85,4 min, 11.067 linhas) | Timestamps do rounds.json (r1) e dos commits 06dcef0/1e37327 + numstat |
| Deriva protocolo↔CLI↔host | 2 erros (flag --id inválida em knowledge get; subcomando knowledge for-context inexistente) entre ~49 referências verificadas; 1 caminho de skill inexistente (.claude/commands/speckit.<phase>.md); 14 referências a um CLAUDE.md inexistente | Script que valida os comandos citados no PROTOCOL.md contra cli.build_parser(); find -name CLAUDE.md = 0 |
| Ganho combinado estimado (feature XS/S) | Input cumulativo −90% (13,0M → 1,3M); custo −74% (US$6,33 → ~1,65 em preço A); chamadas CLI −80%; gates → 0 | gains.py, mesmo modelo, com R2+R3+R4+R6 aplicados |

### Scorecard

| Dimensão | Nota | Máximo | Justificativa |
|---|---:|---:|---|
| Eficiência de contexto por fase | 2 | 10 | O PROTOCOL.md entra inteiro, mas só 21–27% é relevante por fase. As SKILL.md do Spec Kit também entram inteiras (81,4 KB por feature), os docs normalizados não são fatiados (28,1 KB contra 1,6 KB úteis) e o budget file ecoa conteúdo. |
| Economia de turnos (plumbing) | 3 | 10 | São 58 chamadas CLI obrigatórias por feature, com saídas verbosas e traceability gravada uma linha por vez. Não existe comando agregador. |
| Proporcionalidade da cerimônia | 2 | 10 | O tier XS só dispensa o clarify, os artefatos têm 3,8–5,4x o tamanho do código e o tier infla de S para M em 3/3 por causa dos próprios artefatos. |
| Observabilidade de custo e latência | 1 | 10 | Tokens 0, tempos sintéticos e sobrepostos, calibração com 0 rodadas e validate sem warnings, enquanto o host já expõe usage real. |
| Latência do core determinístico | 9 | 10 | ~0,1 s por chamada, hooks +10 ms e snapshot de 0,87 s com 57k arquivos: não é gargalo. |
| Isolamento de contexto | 3 | 10 | O guarded mode isola as fases, mas só no OpenCode, com prompt genérico e sem usage. O caminho Claude Code é uma sessão única, com custo quadrático. |
| Paralelismo efetivo | 2 | 10 | As ondas são calculadas (9/10 na onda 0) mas não são usadas, e os pacotes L formam uma cadeia linear. |
| Interrupções humanas | 4 | 10 | O protocolo busca perguntar em lote, mas as skills impõem até 9 gates por feature e uma regra conflitante no clarify (uma pergunta por vez). |

### Achados

#### A1 — O custo é dominado pelo input cumulativo de uma sessão única (contexto × turnos) e cresce quadraticamente entre features (impacto: alto)

O protocolo conduz todas as fases de todas as features numa única conversa. Cada turno reenvia o histórico inteiro. Com prompt caching, a leitura custa ~0,1x (0,05x no preço A), mas continua sendo cobrada e ocupando janela. Além disso, toda espera acima do TTL de 5 min regrava o prefixo a 1,25x.

Pelo modelo: C0 ≈ 49k tok, ΔC 62k–143k por feature e T 110–160 turnos, o que dá I ≈ 8,8–19,3M tok (central 13,0M) na 1ª feature, ≈26,3M na 2ª e ≈39,6M na 3ª da mesma sessão.

Ilustração real de que cache read domina o custo: a sessão orquestradora desta avaliação registrou, em 29 respostas, 2,25M tok de cache read contra 161k de output.

**Evidência:** PROTOCOL.md:377-395 ('For each feature id in the resolved order, drive...'); scratchpad/custo-fluxo/cost_model.py e gains.py; ~/.claude/projects/-home-user-spec-master/*.jsonl (usage.cache_read_input_tokens por resposta)

#### A2 — PROTOCOL.md monolítico (49,8 KB) é lido inteiro e reenviado a cada turno, mas só 21–27% dele serve à fase (impacto: alto)

O entrypoint manda ler o PROTOCOL.md 'integralmente antes de fazer qualquer outra coisa'. Uma fase típica precisa de 10,6–13,5 KB: invariantes, laço por feature, hooks, métricas e, no specify, risco. Outros 12,9 KB (26%) nunca são usados em runtime no Claude Code: instalação global, portabilidade, MCP, web bundle, dashboard, calibração e Step -1.

São ~9,8k tok mortos a cada turno, cerca de 1,27M tok de cache read por feature. O protocolo ainda cita 14 vezes 'CLAUDE.md §N', um arquivo que não existe no repo.

**Evidência:** .claude/commands/spec-master.md:13; divisão por seções (preâmbulo 2.068 B, Global installation 1.324 B, Portability 2.379 B, MCP 1.914 B, Web bundle 1.743 B, Dashboard 2.723 B, Calibration 1.563 B...); find . -name CLAUDE.md → 0; grep -c 'CLAUDE.md' PROTOCOL.md → 14

#### A3 — Cerimônia completa do Spec Kit mesmo em features pequenas: artefatos de 3,8 a 5,4x o tamanho do código (impacto: alto)

As features 003, 004 e 005 têm 3 critérios de aceite cada e são tier S na intake. Mesmo assim geraram 8–9 arquivos (47,7 / 49,7 / 54,8 KB) contra 11,2 / 9,2 / 10,8 KB de código+testes. O perfil XS só dispensa o clarify: 6 de 7 fases continuam obrigatórias.

O template de tasks força as fases Setup/Foundational/US/Polish. Resultado: 21–27 tasks para ~100–130 linhas de código (ex.: T001 'module skeleton, no logic yet'), cada uma marcada [X] numa edição separada.

O valor observado dessas etapas foi baixo:
- clarify sem efeito em 3/3;
- 1 dos 3 ciclos de analyze só corrigiu o formato de um artefato;
- a feature 3 teve de corrigir no implement uma flag de CLI fictícia que estava nos docs.

HIPÓTESE: gerar ~12k tok de artefatos a 50–80 tok/s custa 2,5–4 min de geração pura por feature.

**Evidência:** git show --numstat 06dcef0 / 6c31029 / 1e37327; wc -c specs/00{3,4,5}-*; risk profiles (XS: 6/7 fases required); speckit-implement/SKILL.md:175; rounds.json r2, r8, r9 (notas)

#### A4 — A própria cerimônia inflaciona o tier de risco (laços de realimentação positiva) (impacto: alto)

Laço 1 (ativo): no pre_implement, o scope conta as tasks geradas pelo template (21–27, acima do limite S de 12). Ao mesmo tempo, as regex de sensibilidade casam 'data-model.md' (schema) e 'contract' (public_contract), que são vocabulário dos próprios artefatos do Spec Kit. Resultado: 3/3 features passam de S para M com escalated=true e analyze obrigatório de novo.

Laço 2 (latente): a calibração marca 'under' quando o custo passa do orçamento (XS 150k, S 400k tokens) e aperta os thresholds em 0,8x. Com tokens reais (milhões de input cumulativo, A1), toda feature ficará 'under', os thresholds cairão a cada janela e as features serão promovidas a tiers com mais cerimônia.

**Evidência:** risk classify --stage pre_implement (scratch): baseline S (computed) → tier M, rerun ['analyze'] nas 3 features; hooks.py:87-98; risk_profile.py:290-299; calibration.py:44-54 (TIGHTEN_FACTOR = 0.8)

#### A5 — Plumbing determinístico excessivo: 58 chamadas CLI obrigatórias e ~25k tok de stdout por feature (impacto: alto)

Cada chamada tende a virar um turno de LLM (segundos; HIPÓTESE de 5–10 min por feature só em plumbing), enquanto o core leva ~0,1 s. Os principais ralos:
- `budget file` ecoa o conteúdo integral dos arquivos (12,4 KB por chamada, 74% dos bytes), então o 'preflight' custa o mesmo que a leitura;
- `state transition` ecoa o registro inteiro da feature (×14);
- `traceability add` grava uma linha por chamada (×10);
- `metrics record-round` é manual (×7);
- `delta snapshot` roda por fase (×7).

**Evidência:** sim_feature.sh (58 linhas de saída, 100.833 B, 7,3 s); cli.py:117 (_print_json({**f, 'hook_directives'...})); cli.py:635-636 (items com 'content'); cli.py:211-219; PROTOCOL.md:338-348, 383-385, 611-614

#### A6 — As métricas não medem performance, embora o host já exponha usage real (impacto: alto)

Estado do rounds.json:
- tokens 0 em todas as linhas;
- 4/9 com duração <1 s;
- 5/9 com horários redondos (00:00, 00:05, 00:25, 01:00, 01:45Z), sobrepostos (analyze e validate em 00:00–00:05) e impossíveis (analyze às 00:00Z antes do specify às 12:21Z);
- 0/9 com feature_id/tier, então a calibração usa 0 rodadas.

Mesmo assim, `metrics validate` aprova com 0 warnings e `summarize` publica 1,385 features/h. O schema (additionalProperties:false) nem aceita campos de cache, custo ou turnos.

Dados reais disponíveis no host e ignorados:
- o transcript JSONL do Claude Code grava usage por resposta (input, output, cache_read, cache_creation) e timestamps;
- o cli.js instalado contém CLAUDE_CODE_ENABLE_TELEMETRY, claude_code.token.usage, claude_code.cost.usage e os spans claude_code.llm_request e claude_code.tool.blocked_on_user;
- `claude -p --output-format json` devolve total_cost_usd, num_turns e duration_api_ms, e `--max-budget-usd` existe;
- o opencode_runner já salva o transcript --format json e não extrai usage.

**Evidência:** .spec-master/metrics/rounds.json; metrics calibrate → rounds_used 0, ignored_rounds 9; schemas/metrics-round.schema.json; metrics.py:19-60; opencode_runner.py:48-53, 78; grep em /opt/node22/lib/node_modules/@anthropic-ai/claude-code/cli.js; claude --help

#### A7 — Gates humanos síncronos, com regras conflitantes entre as skills do Spec Kit e o protocolo (impacto: medio)

Seguindo as skills literalmente, uma feature pode ter:
- specify: até 3 perguntas em lote;
- clarify: até 5 perguntas 'EXACTLY ONE at a time', contra a regra de lote do protocolo;
- analyze: pergunta se o usuário quer remediação e não aplica ('Do NOT apply them automatically'), contra o auto-repair;
- implement: para se houver checklist incompleto;
- PR em Git Flow.

São até 9 interrupções por feature, mais 1–3 por workflow. Cada espera acima de 5 min expira o cache e força regravar o contexto a 1,25x: ~+US$0,48 por gate com 100k de contexto (preço A), até ~US$2,4 por feature, sem contar a latência humana.

**Evidência:** speckit-clarify/SKILL.md:132, 142-143; speckit-analyze/SKILL.md:206-208; speckit-implement/SKILL.md:85-87; speckit-specify/SKILL.md:130; PROTOCOL.md:400-412, 675-706; skill claude-api (prompt caching: TTL de 5 min contado do início da requisição, write 1,25x)

#### A8 — Sem isolamento nem paralelismo efetivo (impacto: medio)

`worktree waves` coloca 9/10 features na onda 0 (independentes), mas o fluxo agentic executa todas em série na mesma sessão. Os work packages L/XL formam uma cadeia estrita contract→data-model→backend→frontend→e2e→docs (paralelismo 1,0; 12 instanciações de papel).

O guarded mode (sessão isolada por fase, com validação de artefatos) é o embrião certo de harness, mas tem três limitações:
- só suporta OpenCode;
- usa o prompt genérico 'Execute /speckit.{phase} for this project', sem os templates do Spec Master nem os dados da feature;
- não mede tokens.

**Evidência:** worktree waves --features feats.json; risk work-packages --feature demo --tier L; controller.py:136-149; opencode_runner.py:48-53

#### A9 — Deriva entre protocolo, CLI e host gera turnos de erro e retry (impacto: medio)

Problemas encontrados:
- `knowledge get --id` falha com rc=2 (o id é posicional);
- `knowledge for-context` não existe (PROTOCOL.md L288, L293), justamente no passo obrigatório de carregar playbooks do Team Mode;
- o adapter Claude e o protocolo apontam para `.claude/commands/speckit.<phase>.md`, que não existe (as skills estão em .claude/skills/speckit-<phase>/SKILL.md), e o protocolo trata essa ausência como FAILED;
- o Step 0 usa `state show` completo (15,2 KB com 10 features) embora `--summary` exista (4,0 KB, −73%);
- `gates detect` retorna [] neste repo, então o validate roda os gates à mão.

**Evidência:** Validação argparse (1 flag inválida + 1 subcomando inexistente); PROTOCOL.md:132, 288, 293, 391; adapters/claude-code.md:32; state show --summary; .spec-master/reports/quality-gates.md

#### A10 — Contexto normalizado e conhecimento não são fatiados por feature nem por papel (impacto: medio)

O prompt de specify passa os 3 docs normalizados inteiros (28,1 KB), quando a seção da feature tem 1,0–3,7 KB. O implement relê app-features (17,5 KB) e tech-stack (5,7 KB) inteiros.

No Team Mode, `knowledge for-role` devolve só metadados (~6 KB), e o conteúdo exige até 8 `knowledge get` por papel. Uma feature L soma ~37k tok de conhecimento por carga única, e o protocolo pede recarga a cada instanciação.

As SKILL.md trazem ~23 KB por feature de boilerplate de hooks inertes.

**Evidência:** templates/prompts/specify.md (--files {{normalized_context_files}}); templates/prompts/implement.md; app-features.md dividido por '### Feature'; budgets de knowledge for-role por papel

#### A11 — Excesso de instruções reduz a aderência, e a 'harness readiness 100%' não cobre desempenho (impacto: medio)

Passos obrigatórios foram pulados na prática: `risk classify --save` nunca foi persistido (risk=None nas 3 features) e as rodadas não têm feature_id/tier. HIPÓTESE causal: 838 linhas e 76 subcomandos excedem o que o agente segue de forma confiável.

O `evals run` obrigatório são 5 checks sobre fixtures sintéticas em memória e não avaliam a execução real.

As auditorias harness-revalidation (73/100) e harness-100-upgrade não medem custo, tokens, latência nem turnos, e contam o `budget file` como controle de contexto.

**Evidência:** .spec-master/state.json (sem chave risk); PROTOCOL.md:463-476, 490-494; evals.py:17-49; .spec-master/reports/harness-100-upgrade.md:35

#### A12 — Experimento natural: o fluxo completo teve ~10x menos throughput que o fluxo agentic direto (indicativo) (impacto: medio)

Features 1–2 pelo Spec Master: ≥43,7 min para 586 linhas de código+testes (~13 linhas/min), mais 1.729 linhas de artefatos.

Itens 3–16 fora do fluxo: 85,4 min para 11.067 linhas de código+testes (~130 linhas/min), 14 itens.

Os artefatos da feature 3 foram commitados 9 min depois do código dela. O experimento não é controlado (escopos diferentes, possível paralelismo, commit ≠ tempo de trabalho), mas é coerente com o modelo de custo e com a decisão do usuário de pausar o ciclo.

**Evidência:** git log --format='%h %aI' 06dcef0^..6c31029; git show --numstat 1e37327 (code +7.049, tests +4.018); rounds.json r1 (12:21:55Z); docs/market-benchmark-roadmap.md:172-206

### Recomendações

#### R1 — Usar a telemetria nativa do host como fonte única das métricas (P0 · esforço M)

Parar de pedir ao agente timestamps e tokens.

(a) Claude Code: um hook Stop/SubagentStop (e PostToolUse sobre o `spec-master step`) lê o transcript_path e agrega por fase usage (input, output, cache_read, cache_creation), turnos, duração e espera humana. Opcionalmente, OTel com CLAUDE_CODE_ENABLE_TELEMETRY=1 e OTEL_RESOURCE_ATTRIBUTES=spec_master.feature_id=…,spec_master.phase=….

(b) Modo headless/guarded: `claude -p --output-format json` (total_cost_usd, num_turns, duration_api_ms, usage) e `--max-budget-usd` por fase. O opencode_runner passa a parsear o transcript JSON que já salva. `codex exec --json` fica como HIPÓTESE.

(c) Schema v2 com cache_read, cache_creation, cost_usd, turns, model, human_wait_s e source. `metrics validate` passa a rejeitar sobreposição e cronologia impossível.

(d) Orçamentos de calibração em tokens novos ou em custo, nunca em input cumulativo.

**Ganho esperado:** Rodadas utilizáveis: de 0/9 para todas. −7 chamadas CLI por feature. Cria a base para medir as demais otimizações e evita o laço 2 da A4.

**Riscos:** Os formatos variam por host e versão, então é preciso um adapter por host. Os transcripts têm conteúdo sensível: ler só usage e timestamps.

#### R2 — Criar o comando `spec-master step` (next/finish), que devolve a próxima ação e um phase card compacto (P0 · esforço M)

O core passa a fazer internamente: transition, validação de artefatos (phase_contracts já existe), delta snapshot, métricas (R1), traceability em lote e risk classify. A resposta é um JSON curto: feature, phase, card de 1–3 KB, caminhos dos insumos, required_outputs, checks e directives.

Quick wins no caminho:
- `budget file` sem eco de conteúdo (`--emit-content` opcional);
- ack compacto no `state transition`;
- `traceability add --rows-file` para lotes;
- `state show --summary` no Step 0;
- `step` como tool principal no MCP.

**Ganho esperado:** Chamadas por feature: 58 → ~9–16 (−72 a −84%). stdout: 100,8 KB → ~10 KB (−90%). Input cumulativo: −25% se o agente já encadeava chamadas, até −43% se cada chamada é um turno (T 130 → 84–110, ΔC −22,7k tok). Custo: US$6,33 → 5,2–5,7 por feature (preço A).

**Riscos:** Perde-se visibilidade passo a passo (mitigar com log de eventos e dashboard). O controle migra para o core, o que exige testes de contrato.

#### R3 — Fatiar o PROTOCOL.md em core card e phase cards, com carga progressiva e prefixo estável (P0 · esforço M)

Estrutura proposta:
- core.md de ~3–4 KB (anti-alucinação, divisão core/agente, idempotência, mensagens);
- um card por fase, de 1–3 KB, entregue pelo `step`;
- material de referência (instalação, portabilidade, MCP, web bundle, dashboard, calibração) fora do caminho de execução.

O entrypoint deixa de exigir leitura integral. Ordem de carga estável para maximizar o cache: core → constitution → feature card → phase card.

Corrigir a deriva: remover as 14 referências ao CLAUDE.md inexistente, usar `knowledge get <id>`, substituir o `for-context` por um comando real e corrigir o caminho das skills no adapter. Criar um teste que valide todo comando citado no protocolo contra `cli.build_parser()`.

**Ganho esperado:** Contexto inicial −9,8k tok (−34% do bootstrap do projeto; −20% contando o sistema). −1,27M tok de cache read por feature (~−10% do input cumulativo). Elimina turnos de erro por deriva e aumenta a aderência (A11).

**Riscos:** Uma regra transversal pode ficar fora de algum card. Mitigar com o core card sempre carregado e com testes de contrato.

#### R4 — Criar um trilho lite para XS/S e rebaixar o Spec Kit a formato de exportação (P0 · esforço L)

Para XS/S (as 3/3 features de dogfood eram S na intake):
- um único spec-lite.md de ≤5 KB (requisitos EARS, critérios, plano curto e checklist de tasks, com limite de 5 tasks em XS e 12 em S);
- clarify só com gatilho determinístico (UNRESOLVED, [NEEDS CLARIFICATION] ou hints do ears check);
- analyze substituído por uma checagem de cobertura AC→task→teste feita pelo core, com uma passada LLM curta só em M+;
- research, data-model, contracts, quickstart e checklists só em M+, e só quando o plano tocar contrato ou dados.

O harness passa a gerar cards próprios em vez de inlinear as SKILL.md (81,4 KB por feature). Um `spec-master export --speckit` gera spec/plan/tasks compatíveis sob demanda.

**Ganho esperado:** Em XS/S: artefatos de 47,7 KB → ≤5 KB (−90%); instruções de 26,4k → ~5k tok; ~130 → ~45 turnos; input cumulativo de 13,0M → 2,8M (−78%); custo de ~US$6,3 → ~2,2 (saída cai de 150k para 45k tok, HIPÓTESE).

**Riscos:** Features mal classificadas podem perder rastreabilidade e qualidade. Mitigar com escalonamento por sinais de código (R5) e com o export sob demanda. O fluxo passa a divergir do upstream do Spec Kit.

#### R5 — Desarmar os laços de inflação de tier (P0 · esforço S)

Mudanças:
- avaliar a sensibilidade sobre caminhos de código e infra tocados, não sobre a prosa das tasks;
- tirar das regex de texto o vocabulário de artefato do Spec Kit (data-model.md, contracts/, contract test);
- medir o scope do pre_implement por arquivos e camadas, sem contar as tasks geradas pelo template;
- na calibração, fazer 'under' disparar primeiro uma revisão da cerimônia (custo por fase) e só depois apertar thresholds, usando orçamentos em tokens novos ou custo.

**Ganho esperado:** Evita a escalada S→M vista em 3/3 casos: −1 passada de analyze por feature (~12,6k tok e ~8 turnos; −12% do input cumulativo) e o clarify continua pulável. Impede a espiral de calibração quando chegarem tokens reais.

**Riscos:** Risco de falso negativo. Mitigar mantendo as regex de caminho que já existem (migrations/, openapi, .proto, .sql).

#### R6 — Isolar o contexto por fase e por feature com workers headless ou subagentes (P1 · esforço L)

Generalizar o controller.py para rodar cada fase como worker:
- `claude -p` com json, `--max-budget-usd`, `--allowedTools` e `--append-system-prompt` contendo o card;
- `codex exec`;
- `opencode run`.

Cada worker recebe card, insumos mínimos e dados da feature (o prompt guarded atual é genérico). No modo interativo, usar subagentes .claude/agents/spec-<fase>.md com ferramentas restritas. O orquestrador recebe só o JSON ou um resumo, e os artefatos são a interface entre fases.

**Ganho esperado:** Input cumulativo de 13,0M → ~4,2M por feature (−68%), com custo linear no número de features (hoje a 3ª feature na mesma sessão custa ~39,6M). Combinado com R2+R3+R4 em XS/S: ~1,3M tok (−90%) e ~US$1,65 por feature (−74%).

**Riscos:** Mais cache writes (~0,3M tok a 1,25x) e perda de nuance entre fases. Mitigar com resumo estruturado e prefixo comum estável.

#### R7 — Concentrar os gates no início e em lote; nenhum gate em XS/S (P1 · esforço S)

Mudanças:
- um único lote de decisões na intake (git strategy, init, constitution e ambiguidades conhecidas);
- clarify em lote, sobrepondo explicitamente a regra 'EXACTLY ONE question' da skill;
- remover a oferta de remediação do analyze e o gate de checklist do implement, deixando a decisão ao core conforme o tier;
- em XS/S, usar SAFE_DEFAULT e registrá-lo na decision memory;
- nunca perguntar no meio de uma fase: fechar a fase e perguntar na fronteira.

**Ganho esperado:** Interrupções por feature: de até 9 para ≤1 em M+ e 0 em XS/S. Evita regravar o cache após >5 min de espera (~US$0,48 por gate a 100k de contexto; até ~US$2,4 por feature) e remove a latência humana do meio das fases.

**Riscos:** Um default pode estar errado. Mitigar com registro auditável e reversão no ciclo seguinte.

#### R8 — Paralelismo real por ondas e DAG nos work packages (P1 · esforço M)

Com o isolamento da R6, rodar em paralelo as features de uma mesma onda (9/10 estão na onda 0) em worktrees, com limite de concorrência e agregação via `worktree conflicts|aggregate`, que já existem. No Team Mode, trocar a cadeia linear de L/XL por um DAG: backend em paralelo com frontend depois de contract/data-model, e docs em paralelo com e2e.

**Ganho esperado:** O wall-clock de N features independentes passa a ser o da mais longa, não a soma (até −80% com 10 features em 2 ondas; HIPÓTESE, limitada por rate limit e merge). Caminho crítico de L: 6 → 4 pacotes (−33%). Os tokens não aumentam.

**Riscos:** Conflitos de merge, rate limit e picos de custo. Usar `--max-budget-usd` por worker.

#### R9 — Feature cards e conhecimento dentro de orçamento (P1 · esforço S)

O core extrai por feature a seção de app-features, mais cross-feature, non-goals e os excertos relevantes de tech-stack e goals (o feature card). `knowledge for-role --include-content --token-budget N` passa a resolver tudo numa chamada, carregando cada playbook uma vez por papel e sessão, não uma vez por instanciação.

**Ganho esperado:** Specify: 28,1 KB → ~4,6 KB (−84%). Implement: −17,5 KB. Team Mode L: 1 chamada por papel em vez de 1+8, com teto configurável para os ~37k tok atuais.

**Riscos:** Requisitos transversais podem ficar de fora. Mitigar incluindo sempre as seções Cross-feature e Non-goals no card.

#### R10 — Evals de trajetória no CI, com orçamento por tier (P2 · esforço M)

Complementar o `evals run` sintético com uma feature XS de referência rodada headless (`--max-budget-usd`) no CI. Medir: tokens novos, input cumulativo, turnos, gates, razão artefato/código, retrabalho de analyze e gates aprovados. O CI falha se houver regressão acima de X%, e os resultados alimentam a calibração (R1/R5).

**Ganho esperado:** Regressões de custo e latência aparecem antes do release. Os orçamentos por tier ganham base empírica: hoje XS tem 150k tokens contra ~9–19M de input cumulativo estimado.

**Riscos:** Custo recorrente de LLM no CI e variância entre execuções. Usar amostra pequena, modelo fixo e orçamento rígido.

### Perguntas abertas

- Qual é o host e o modelo-alvo em produção: Claude Code com um modelo de fronteira ou OpenCode com modelo local (o runner usa por padrão ollama qwen3-coder 30b)? A resposta muda o peso do prompt caching frente ao prefill e à latência locais.
- Os orçamentos de calibração devem medir tokens novos, input cumulativo (com cache reads) ou custo em US$? Hoje isso não está definido, e XS = 150k tokens é incompatível com o input cumulativo estimado.
- O Spec Kit deve continuar como motor de execução (skills inlinadas) ou passar a ser só um formato de exportação/compatibilidade do harness?
- Existem transcripts reais de execuções do /spec-master, com usage, fora do repo? O `.spec-master/logs` não é versionado. Com eles dá para calibrar os pontos HIPÓTESE do modelo: turnos, tokens de saída e os ~30 KB de leitura de código no implement.
- Que nível de artefatos é aceitável para XS/S sob exigências de auditoria (ex.: clientes regulados)?
- Que concorrência é aceitável para paralelizar ondas (rate limits da conta, custo de pico, política de merge)?

### Referências

- spec-master/PROTOCOL.md (L132, L288, L293, L338-348, L377-412, L463-476, L611-614, L675-706)
- .claude/commands/spec-master.md (L13)
- spec-master/adapters/claude-code.md (L32)
- .claude/skills/speckit-clarify/SKILL.md (L132, L142-143)
- .claude/skills/speckit-analyze/SKILL.md (L206-208)
- .claude/skills/speckit-implement/SKILL.md (L85-87, L175)
- .claude/skills/speckit-specify/SKILL.md (L130)
- spec-master/lib/cli.py (L117, L211-219, L635-636)
- spec-master/lib/hooks.py (L87-98)
- spec-master/lib/risk_profile.py (L290-299)
- spec-master/lib/calibration.py (L44-54)
- spec-master/lib/metrics.py
- spec-master/schemas/metrics-round.schema.json
- spec-master/lib/controller.py (L136-149)
- spec-master/lib/opencode_runner.py (L48-53, L78)
- spec-master/lib/context_budget.py
- spec-master/lib/evals.py (L17-49)
- .spec-master/metrics/rounds.json
- .spec-master/state.json
- .spec-master/reports/harness-100-upgrade.md
- docs/market-benchmark-roadmap.md (L172-206)
- specs/003-parallel-worktree-execution, 004-team-mode-parallel-workstreams, 005-speckit-tracker-orchestration
- Commits 06dcef0, 1e37327, 165f1de, 6c31029 (git show --numstat)
- <scratch>/custo-fluxo/cost_model.py (modelo de custo por fase)
- <scratch>/custo-fluxo/gains.py (ganhos por otimização)
- <scratch>/custo-fluxo/sim_feature.sh (58 chamadas mandatadas)
- /opt/node22/lib/node_modules/@anthropic-ai/claude-code/cli.js (identificadores OTel/usage verificados) e `claude --help` (--output-format json|stream-json, --max-budget-usd)
- Skill claude-api: shared/prompt-caching.md (TTL de 5 min, write 1,25x/2x, read ~0,1x; 0,05x no preço A) e tabela de preços (preço A $4/$20, preço B $5/$25)

---

## Overengineering e cerimônia

### Resumo

Avaliação de adequação de processo (cerimônia). O risco adaptativo XS–XL existe só no nome: um XS ainda exige 6 das 7 fases (só clarify pode ser pulada), e 'analyze light' e 'review self' não são lidos por nenhum código. A própria calibração reserva 7 rounds, 30 min e 150k tokens para uma mudança trivial.

A classificação não enxerga nada no intake: as 10 features têm exatamente 3 ACs, e 8/10 saem S seja o módulo de 92 LOC ou de 994 LOC. Depois da cerimônia ela é inflada: as 3 features do dogfood subiriam de S para M só porque o tasks.md cita 'data-model' e 'contracts', vocabulário do próprio Spec Kit.

O dogfood mostra rigor invertido. O fluxo completo foi aplicado aos 3 menores módulos (92–131 LOC), gerando de 8,7x a 12,5x mais bytes de artefato que de código; o requisito de 634 B foi amplificado 75x. Os 13 itens maiores e mais arriscados (165–994 LOC, incluindo o passo de PR/push) foram entregues fora do fluxo, com testes.

Há cerca de 20 mecanismos de verificação, mas só os quality gates executam código, e eles retornam [] para o próprio repo. O state machine impõe a ORDEM das fases, mas não a EVIDÊNCIA: aceita PASSED sem artefato, aceita clarify SKIPPED numa feature L de auth e aceita COMPLETED com as 7 fases PENDING. Métricas, calibração, grafo, decision memory e hooks praticamente não têm dados reais.

Proposta: 3 lanes (Patch, Standard e Critical), com triagem determinística por sinais de caminho e diff medidos antes da cerimônia, escalonamento automático pelo diff real e um único verificador baseado em evidência. O Spec Kit passa a ser o motor só do lane Critical, e o harness (triagem, envelope, enforcement via hooks do host, evidência) vira o eixo.

### Métricas

| Métrica | Valor | Método |
|---|---|---|
| Fases obrigatórias por tier | XS/S: 6 de 7 (só clarify pode ser pulada); M/L/XL: 7 de 7 | `risk profiles` na cópia scratch; `state transition --phase plan\|analyze --status SKIPPED` → exit 1 'cannot be SKIPPED (skippable: clarify)'; risk_profile.py:72, state.py:45 |
| Diferenças operacionais XS vs M efetivamente implementadas | 1 (clarify pulável); 'analyze light/deep' e 'review self/peer' não têm nenhum consumidor | grep por light/deep/review em spec-master/lib, templates, mcp e .claude/commands (só o risk_profile.py os define) |
| Orçamento que o próprio sistema reserva para um XS | 7 rounds / 1.800 s / 150.000 tokens | spec-master/lib/calibration.py:43-44 (TIER_BUDGETS) |
| Chamadas de bookkeeping no caminho XS mínimo simulado | 36 chamadas de CLI em 3,9 s (~0,1 s/chamada; o core não é o gargalo). O protocolo completo exige mais (≥7 record-round, 1 traceability add por AC, budget file por prompt) | script scratch/cerimonia/xs_path.sh num projeto git scratch (typo de 1 linha); tempo de parede com date +%s.%N |
| Tokens de instrução lidos no caminho XS (Claude Code) | ~34,5k (PROTOCOL + comando 13,2k; 5 skills do Spec Kit 15,5k; templates 4,4k; prompts 1,4k) | wc -c / 4 nos arquivos lidos em specify, plan, tasks, analyze e implement |
| Artefatos vs código (features 003–005, fluxo completo) | 47,7–54,8 KB de artefatos vs 4,0–5,5 KB de código = 8,7x–12,5x (4,3x–5,4x incluindo testes) | wc -c em specs/00{3,4,5}-*/ e lib/{worktree,team_workstreams,tracker_orchestration}.py + tests/test_*.py |
| Amplificação do requisito até os artefatos (Feature 1) | 634 B (roadmap) → 2.132 B (app-features) → 11.156 B (spec.md) → 47.739 B (todos os artefatos) = 75x; objetivo central só parcial (SC-001 PARTIAL) | regex sobre docs/market-benchmark-roadmap.md e .spec-master/context/app-features.md; os.path.getsize |
| Tamanho dos módulos: dentro vs fora do fluxo | Dentro: 92–131 LOC (3 features). Fora: 165–994 LOC, 6.221 LOC em 13 itens | wc -l nos módulos listados na tabela de status do roadmap |
| Escaladas espúrias causadas pelo vocabulário do Spec Kit | 3/3 features do dogfood sobem de S para M no pre_implement, com gatilhos só em 'data-model' e 'contracts' do tasks.md (0 no texto da feature); um XS de typo reproduzido virou M | `risk classify` dry-run nas duas etapas; regex dos hooks sensitivity-* aplicado ao payload vs ao texto da feature |
| Poder de discriminação do intake | 10/10 features com exatamente 3 ACs; 8/10 classificadas S (de 92 a 994 LOC) | state.json + `risk classify --stage intake` nas 10 features |
| Mecanismos de verificação por feature | ~20; só 1 executa código (quality gates), e ele retorna [] neste repo | Leitura de PROTOCOL.md, skills speckit-* e templates; `gates detect --path .` |
| Suíte de testes (gate executável real) | 502 testes em 3,3 s, errors=21 (import de pytest) | python3 -m unittest discover -s spec-master/tests na cópia scratch |
| Qualidade dos dados de métricas | 9 rounds, 0 tokens, 0 com feature_id/tier, 3 com duração 0,0 s, 5 com horários redondos sobrepostos; calibrate: rounds_used 0 / ignored_rounds 9; validate: valid, 0 warnings | `metrics validate\|summarize\|calibrate` na cópia scratch |
| Completude exibida no dashboard | 30% (21/70 fases), com 10/10 features entregues | `dashboard model --path .` na cópia scratch |
| Uso das capacidades estruturais após 10 features | Knowledge graph com 4 nós/3 arestas; 0 decisões; 0 firings de hooks; 0 ADR; 0 classificações de risco; workstreams.json inexistente | `graph stats`, `team decisions`, ls .spec-master/{hooks,risk,adr,workstreams.json} |
| Tamanho e complexidade do protocolo | PROTOCOL.md 49,8 KB; ~40 comandos distintos; ~91 imperativos (never 48, must 16, don't/do not 20, always 7); 11 referências a 'CLAUDE.md §N', arquivo que não existe | grep -o/-c; find . -name CLAUDE.md → 0 |
| Drift entre protocolo e CLI | 82 invocações verificadas, 2 quebradas: `knowledge get --id` e `knowledge for-context`, ambas no passo de Team Mode | Script que valida as invocações de PROTOCOL.md, playbooks/spec-master.md e commands/spec-master.md contra cli.build_parser() |
| Catálogo do servidor MCP | 76 tools, 34.781 B ≈ 8,7k tokens de schema injetados por turno | tools/list via stdio em spec-master/mcp/spec_master_mcp.py |

### Scorecard

| Dimensão | Nota | Máximo | Justificativa |
|---|---:|---:|---|
| Proporcionalidade cerimônia × risco | 2 | 10 | XS = 6/7 fases; no dogfood o rigor foi aplicado ao contrário do tamanho e do risco. |
| Precisão da classificação de risco | 3 | 10 | Intake não discrimina (3 ACs em todas); pre_implement é inflado pelo vocabulário do Spec Kit; PR/push sai S. |
| Eficiência da verificação (sinal/custo) | 3 | 10 | ~20 mecanismos; só os gates executam código e estão vazios no próprio repo; analyze pega sobretudo inconsistências autoinfligidas. |
| Enforcement dos invariantes que importam | 3 | 10 | A ordem é imposta; a evidência e os deveres de risco não (PASSED sem artefato, clarify pulado em L/auth). |
| Uso real das capacidades estruturais | 2 | 10 | Grafo com 4 nós, 0 decisões, 0 firings de hooks, 0 classificações de risco, 0 workstreams após 10 features. |
| Qualidade dos dados de métricas e calibração | 1 | 10 | 0 tokens, horários inventados, 0 rounds utilizáveis; dashboard em 30% com tudo entregue. |
| Disciplina anti-alucinação e honestidade dos relatórios | 7 | 10 | Classificação de fontes e SC-001 PARTIAL documentado com franqueza; mesmo assim a fase foi promovida a PASSED. |
| Fundação determinística (velocidade e testabilidade do core) | 7 | 10 | ~0,1 s por chamada e 502 testes em 3,3 s; porém 21 erros tolerados e gate não detectado no próprio repo. |

### Achados

#### A1 — O tier XS não encurta o fluxo: 6 de 7 fases continuam obrigatórias (impacto: alto)

O perfil de todos os tiers fixa specify, plan, tasks, analyze, implement e validate como 'required'; só clarify pode ser pulada. As diferenças XS vs M ('analyze: light' e 'review: self') são rótulos devolvidos no JSON: nenhum módulo, template de prompt ou controller os lê, e o prompt de analyze é único. O ganho máximo de um XS é pular 1 fase que, no dogfood, já era barata ('zero critical ambiguities found'). O menor caminho oficial hoje para uma mudança de 3 linhas soma: Steps 0–5 (state/fingerprint/delta, discovery, normalização em 3 docs, constitution, upsert/order), mais 6 fases, mais ≥36 chamadas de bookkeeping, mais os gates finais de grafo/evals/runtime. O único atalho real é o bypass usado no dogfood (upsert com status COMPLETED).

**Evidência:** risk_profile.py:72 (phases 'required' em _profile); state.py:45 SKIPPABLE_PHASES=('clarify',); `state transition --phase plan --status SKIPPED` → "phase 'plan' cannot be SKIPPED (skippable: clarify)"; `--phase implement --status RUNNING` → "cannot start/pass 'implement' before 'analyze' has PASSED"; calibration.py:43-44 XS = 7 rounds/1800 s/150k tokens; simulação XS: 36 chamadas, 3,9 s.

#### A2 — A classificação de risco é cega no intake e inflada pela própria cerimônia (impacto: alto)

No intake, os sinais são o número de ACs e de palavras da descrição. Toda feature do state tem exatamente 3 ACs e menos de 40 palavras, então 8/10 saem S, de um módulo de 92 LOC a um de 994 LOC. No pre_implement, o escopo vem do tasks.md do Spec Kit (21–26 tasks, pela granularidade do template), e a sensibilidade roda regex sobre o texto das tasks. Palavras como 'data-model' e 'contracts' (nomes de artefatos do Spec Kit) disparam os pisos schema e public_contract (M). Resultado: as 3 features do dogfood subiriam de S para M, com rerun de clarify e analyze, sem que nenhuma tocasse schema ou contrato público. No sentido inverso, o optional-pr-open-step (emite git push / gh pr create, ação irreversível) sai S, porque o regex não enxerga push, PR ou publish. A feature de hooks foi para M só por citar 'public-contract' na descrição.

**Evidência:** risk_profile.py:298-315 (texto do payload = feature + task_text); hooks sensitivity-schema/public-contract; os matches aparecem só no texto das tasks ('data-model', 'contracts') e zero vezes no texto da feature; dry-run: parallel-worktree, team-mode e tracker passam de S para M (binding tasks 21–26 > 12); xsproj: XS→M, escalated=True, rerun ['clarify','analyze']; optional-pr-open-step no intake = S.

#### A3 — Dogfood: rigor invertido e erosão do próprio fluxo (impacto: alto)

O fluxo completo foi aplicado aos 3 menores módulos (worktree 129 LOC, team_workstreams 92, tracker_orchestration 131). Gerou de 47,7 a 54,8 KB de artefatos por feature, 8,7x–12,5x o código. O requisito da Feature 1 (634 B) virou 47,7 KB de artefatos (75x), e ainda assim o objetivo central (paralelização real) não foi entregue: o SC-001 ficou PARTIAL e nenhum executor usa compute_waves, mas a fase validate passou. Os 13 itens seguintes (165–994 LOC, incluindo pr_step, hooks e MCP com escrita) foram entregues fora do fluxo, com testes. Houve erosão mesmo dentro do fluxo: checklists/requirements.md ausente em 004 e 005; risco nunca classificado (0/10), com clarify rodando por completo nas 3 features; workstreams.json nunca gerado, nem na própria feature de workstreams. HIPÓTESE: a pausa foi motivada pelo custo e pela latência da cerimônia; o repo só registra 'não usar o Spec Master para evoluir o Spec Master'.

**Evidência:** docs/market-benchmark-roadmap.md:172-177; state.json (7 features com delivery.mode 'agentic-outside-spec-master' e fases PENDING); git show --stat 1e37327 (51 arquivos, 11.760 inserções); specs/003-parallel-worktree-execution/validation-report.md (SC-001 PARTIAL / scope boundary); compute_waves só é chamado em cli.py e team_workstreams.py; specs/*/checklists existe só em 001–003.

#### A4 — O valor do analyze + repair é majoritariamente autoinfligido (impacto: alto)

Dos 6 achados de analyze registrados, 2 tinham valor real de design (contrato de isolamento FR-003 e semântica de mutação do worktree-plan, na F1) e 1 era lacuna de cobertura. Os outros 3 eram inconsistências entre os próprios artefatos: US3 ausente, citação FR-007/FR-008 trocada, id de task T005a. Os 2 defeitos reais de contrato da F3 (flag --issue fictícia e enum 'unknown' contraditório) escaparam do analyze e só foram pegos ao implementar contra o cli.py real. O analyze se paga quando há incerteza de design (Standard/Critical). Em mudanças pequenas ele verifica sobretudo a coerência da papelada que o próprio processo criou; o contato com o código e com os testes é o verificador mais eficaz.

**Evidência:** .spec-master/metrics/rounds.json (notes de r5, r8 e r9); specs/005-speckit-tracker-orchestration/validation-report.md, seção 'Analyze-Phase Repairs' (itens 2 e 3: 'caught while building against the real cli.py').

#### A5 — ~20 mecanismos de verificação sobrepostos; só 1 executa código, e está vazio no dogfood (impacto: alto)

A ambiguidade é checada 5 vezes: checklist do specify (até 3 iterações), clarify (até 5 perguntas), passes B/C do analyze, EARS e gate de checklist no implement. A aderência à constitution é checada 3–4 vezes: Constitution Check do plan, passe D do analyze, prompt de analyze do Spec Master e peer review contra o playbook. A cobertura AC→task→teste é checada 6–7 vezes: passe E, prompt do Spec Master, traceability add/render + condição de SUCCESS, validate, converge, QA e peer review. No fechamento, 6 checagens (graph enrich/validate/snapshot/health, evals, runtime contract) validam o harness, não a feature. O único verificador executável (quality gates) retorna [] para este repo, que não tem manifesto. A suíte roda com 21 erros tratados como 'pré-existentes', o que viola o Princípio III da própria constitution.

**Evidência:** .claude/skills/speckit-specify/SKILL.md:146-199; speckit-clarify/SKILL.md:132; speckit-analyze/SKILL.md:121-152; .specify/templates/plan-template.md:39; speckit-implement/SKILL.md:62-85; PROTOCOL.md:616-633; `gates detect --path .` → []; unittest: 502 testes, errors=21; .specify/memory/constitution.md:21-27.

#### A6 — O state machine impõe ordem, não evidência (enforcement invertido) (impacto: alto)

Em modo nativo, o único disponível no Claude Code, `state transition --status PASSED` aceita qualquer fase sem checar artefato; phase_contracts só é usado pelo controller guarded. O core recusa pular plan num typo, mas aceita clarify SKIPPED numa feature L de auth (o próprio PROTOCOL admite que 'não checa o profile'). Também aceita feature COMPLETED com as 7 fases PENDING via upsert, exatamente o atalho usado para 7 features. O Princípio IV ('promoção exige validar o artefato') só vale no guarded.

**Evidência:** cli.py:108-118 (transition sem validação; phase_contracts não aparece em cli.py); PROTOCOL.md:459; xsproj: feature auth-change (tier L, sens auth), clarify SKIPPED → exit 0; upsert {id: ghost, status: COMPLETED} → COMPLETED com fases PENDING; constitution.md:29-35.

#### A7 — Métricas e calibração operam sobre dados vazios ou inventados (Goodhart) (impacto: medio)

O rounds.json tem 9 linhas, todas com 0 tokens e nenhuma com feature_id ou tier. As rodadas r1–r4 têm duração 0,0 s. As rodadas r5–r9 têm horários redondos e sobrepostos: 00:00→00:05 aparece duas vezes, antes de r1 (12:21Z), o que contraria a regra 'never invent'. Ainda assim, `metrics validate` responde valid sem warnings, e `metrics calibrate` usa 0 rounds (ignored_rounds=9). O dashboard mostra 30% de completude (21/70 fases) com 10/10 features entregues: mede conformidade ao ritual, não valor. Um loop de calibração de 413 LOC sem nenhuma entrada real é YAGNI.

**Evidência:** .spec-master/metrics/rounds.json; `metrics calibrate` → rounds_used 0, ignored_rounds 9; `dashboard model` → completeness {done 21, total 70, percent 30.0}; PROTOCOL.md:338-348.

#### A8 — Cerimônia estrutural construída antes do uso (Gall's law / YAGNI / cargo cult) (impacto: medio)

Após 10 features: knowledge graph com 4 nós e 3 arestas, 0 decisões na decision memory, 0 firings de hooks, 0 ADRs, 0 classificações de risco e workstreams.json inexistente. O passo do Team Mode que 'carrega o playbook vinculante' está quebrado no próprio protocolo (`knowledge get --id` e `knowledge for-context` não existem), o que mostra que nunca rodou de ponta a ponta. Para L/XL, os work packages são um template fixo de 6 etapas encadeadas (contract→data-model→backend→frontend→e2e→docs), mesmo numa feature só de CLI: uma cascata sem paralelismo. O peer review é uma checagem de string (reviewer_agent igual ao atribuído) dentro de um único contexto de modelo; não há .claude/agents nem isolamento. O próprio knowledge/agile/galls-law.md cita como violação típica 'uma arquitetura de plugins complexa antes de um caso concreto'.

**Evidência:** `graph stats` → 4 nós / 3 arestas; `team decisions` → []; PROTOCOL.md:288,293 e knowledge/playbooks/spec-master.md:29,34 vs parser (`knowledge get` só aceita id posicional; ações existentes: list/get/search/for-role/route/stats/validate); `risk work-packages --feature sast-quality-gate --tier L` inclui frontend e data-model; team_workstreams.py:24-37; team_model.py:509-519.

#### A9 — Custo de contexto e cognitivo do protocolo monolítico (impacto: medio)

O caminho XS carrega ~34,5k tokens só de instruções antes de escrever uma linha. O PROTOCOL tem 49,8 KB, ~40 comandos e ~91 imperativos, e cita 11 vezes um 'CLAUDE.md §N' que não existe no repo: são regras cuja justificativa sumiu (Chesterton's fence ao contrário). A camada normalizada re-transcreve o contexto (roadmap 14,4 KB → app-features 17,5 KB → spec.md), multiplicando pontos de drift que o analyze depois precisa reconciliar. O MCP expõe 76 tools (~8,7k tokens de schema por turno) com descrições genéricas ('Spec Master CLI: state init.'). O core é rápido (~0,1 s por chamada; 502 testes em 3,3 s): o gargalo é o número de turnos e de tokens de LLM que o processo exige, não o Python.

**Evidência:** wc -c (bytes/4); grep -c 'CLAUDE.md §' PROTOCOL.md = 11; find . -name CLAUDE.md → 0; .claude/commands/spec-master.md cita '§38 do CLAUDE.md original desta skill'; MCP tools/list: 76 tools / 34.781 B; timing: state show 0,106 s, import cli 0,103 s.

#### A10 — Staleness e camada de contexto em granularidade grossa punem mudanças pequenas (impacto: medio)

Toda feature precisa estar em app-features.md, porque o Step 5 lê esse doc. Incluir uma correção pequena altera o fingerprint global, o que dispara a pergunta Resume vs Restart (Step 0) e devolve uma lista plana de fases stale (specify..analyze) sem escopo por feature. O agente então precisa avaliar o impacto à mão em todas as features: o custo de uma mudança pequena cresce com o número de features existentes.

**Evidência:** fingerprint.py:14-18 (DOC_TO_STALE_PHASES); compare() retorna lista plana; PROTOCOL.md:134-144 (Resume vs Restart) e 256-274 (Step 5).

#### A11 — O único enforcement real (guarded) é só OpenCode e quebra com mais de 1 feature (impacto: medio)

O controller guarded isola fases e valida artefatos, mas o único integrador é o opencode. No Claude Code, o entrypoint principal, não há hooks (.claude/settings.json ausente) nem subagentes: tudo depende de o LLM seguir 49,8 KB de protocolo. Além disso, as tentativas são indexadas só por fase. Com um estado de 2 features, a fase specify da feature B retornou PASSED sem lançar sessão e deixou B.phases.specify=PENDING. A motivação original do guarded (modelos menos robustos 'perdem a fase após compactação', 'declaram sucesso sem artefato') é legítima e justifica mantê-lo como opt-in.

**Evidência:** phase_runner.py:136 INTEGRATIONS={'opencode': ...}; controller.py:275 e 280-284; experimento em scratch/cerimonia/gm: 'specify already PASSED (fingerprint unchanged) — skipping' | sessions launched: 0 | B.phases.specify = PENDING; docs/spec-master/guarded-mode-spec.md §1.

#### A12 — As autoauditorias medem presença de primitivas, não eficácia (impacto: baixo)

O salto de 73/100 para '100% readiness' veio da adição de primitivas que o agente pode ignorar. O `policy preflight` é consultivo (não está ligado a nenhum hook do host) e classifica `git push origin HEAD --force` e `python3 -c shutil.rmtree(...)` como allowed/low. O `evals run` são 5 checagens sintéticas fixas que não olham o projeto. O grafo foi 'populado' para fechar o gap de 'grafo vazio' e tem 4 nós. É Goodhart aplicado à própria nota de harness.

**Evidência:** .spec-master/reports/harness-100-upgrade.md; tool_policy.py:53 (só detecta parts[1:3]==['push','--force']); evals.py:17-45; `policy preflight` na cópia scratch.

### Recomendações

#### R1 — Trocar os tiers XS–XL por 3 lanes com triagem determinística antes da cerimônia (P0 · esforço M)

Criar `lane triage` no core, decidindo o lane ANTES de qualquer artefato. Os sinais são mensuráveis por caminho, diff e repositório, e não por contagem de ACs nem por regex sobre prosa:
(a) arquivos de produção e camadas previstas, via --paths ou sonda read-only com git grep dos símbolos citados;
(b) superfícies sensíveis por caminho: auth/, payment/billing, secrets/.env/*.pem, migrations/*.sql/schema.*, .github/workflows, infra/terraform/helm e uma lista sensitive_paths do projeto;
(c) contrato público: flags de CLI, openapi/proto/graphql, schemas/*.json, formato de arquivos persistidos, API exportada;
(d) novidade: novo módulo, nova dependência (manifesto alterado), novo provedor externo;
(e) reversibilidade: migração de dados, deleção, push/publish/deploy;
(f) teste existente para o módulo tocado;
(g) perguntas UNRESOLVED.

PATCH
- Entrada: ≤3 arquivos de produção em 1 módulo; ≤~50 LOC; nenhum sinal de b a e; teste existente ou adicionado; 0 perguntas abertas.
- Fluxo: triage → implement → verify(post) → done.
- Artefato: change note ≤1 KB (intenção, 1–3 checks de aceite, arquivos, evidência); pode ser o corpo do commit.
- Revisão: self + checagem automática do escopo do diff.

STANDARD
- Entrada: não cabe no Patch e não aciona Critical: ≤~12 arquivos, ≤3 camadas, contrato público só aditivo.
- Fluxo: triage → spec-lite (1 spec.md com problema, ACs testáveis, plano curto e checklist de tasks) → clarify só se houver UNRESOLVED (1 lote) → verify(pre) → implement test-first → verify(post) → revisão independente real.
- Sem research, data-model, contracts ou quickstart, salvo gatilho específico.

CRITICAL
- Entrada (qualquer um): superfície sensível, contrato breaking, migração ou schema, ação irreversível, novo provedor ou dependência, >3 camadas, >12 arquivos ou >~800 LOC, exigência regulatória ou constitucional, área sem testes.
- Fluxo: Spec Kit completo + analyze/repair ≤3 + ADR + revisão de segurança + aprovação humana antes do implement e antes de qualquer ação irreversível. Team Mode opcional.

Os limiares iniciais reaproveitam files/layers de DEFAULT_THRESHOLDS e são calibráveis.

**Ganho esperado:** Patch: 6 fases → 2 passos; instruções de ~34,5k → ~2–3k tokens (estimativa, −90%); artefatos de ~12–14k tokens → <0,5k; ≥36 chamadas de bookkeeping → ≤4. Standard: artefatos de ~48–55 KB → ~8–12 KB por feature (estimativa: spec + plan + tasks de 003 somam 28,5 KB e seriam fundidos). Critical mantém o rigor atual onde ele se paga.

**Riscos:** Subclassificação no Patch. Mitigada pelo R2 (escalonamento pelo diff real) e pela sensibilidade por caminho. Os limiares são chute até haver telemetria (R9).

#### R2 — Escalonamento automático guiado pelo diff real, sem sensibilidade por regex de prosa (P0 · esforço M)

Recalcular os sinais a partir de `git diff` após cada edição (PostToolUse no Claude Code; `lane check --diff` nos demais hosts) e no verify.

Se qualquer sinal exceder o envelope do lane: parar, subir de lane, registrar o motivo e gerar só o delta que falta, sem nunca reiniciar o pipeline:
- Patch → Standard: spec-lite retroativo + ACs + revisão independente;
- Standard → Critical: clarify, analyze, ADR, revisão de segurança e aprovação humana.

Gatilhos adicionais: 2 falhas seguidas do mesmo gate; ambiguidade que exige decisão do usuário; teste inviável para módulo tocado; diff fora do escopo declarado.

Rebaixamento: nunca no meio da execução, só na próxima triagem e com justificativa. Override para cima sempre permitido; para baixo, só com confirmação explícita e log.

Remover a sensibilidade por regex sobre o texto de tasks e spec (falsos positivos em 'data-model', 'contracts' e 'contract') e passar a detectar push/PR/publish como ação irreversível.

**Ganho esperado:** Elimina as 3/3 escaladas espúrias de S para M observadas, e o rerun de clarify + analyze que elas impõem. Torna o Patch seguro por construção. Passa a pegar o que hoje escapa (PR/push classificado como S).

**Riscos:** Os hooks variam por host. Onde não houver hooks, a checagem cai no verify e fica menos imediata.

#### R3 — Um único verificador baseado em evidência no lugar das ~20 checagens sobrepostas (P0 · esforço M)

Adotar `verify --stage pre|post` como único gate:
- pre (só Standard/Critical): cruza ACs, tasks e testes planejados, marcadores de ambiguidade e regras da constitution expressas como checagens de máquina (ex.: 'stdlib only' = manifestos inalterados);
- post (todos os lanes): executa os gates detectados, mapeia cada AC a um teste ou gate verde, compara o diff com o escopo declarado e roda SAST se configurado.

A traceability passa a ser derivada da evidência, sem `traceability add` manual. Concluir = evidência verde, não fases PASSED. Em modo nativo, `state transition PASSED` deve chamar phase_contracts.validate_artifacts, que já existe.

Pré-requisitos: a detecção de gates precisa reconhecer projeto Python stdlib com tests/ (hoje retorna [] no próprio repo), e os 21 erros de import de pytest precisam ser corrigidos, para o gate não ficar vermelho para sempre.

Mover graph ×4, evals e runtime contract para um comando `doctor` rodado em CI.

**Ganho esperado:** De ~20 mecanismos para 3 (verify-pre, verify-post, revisão independente) + gates. Remove 6 checagens de fechamento que não verificam a feature. O dogfood passa a ter um verificador executável.

**Riscos:** A qualidade semântica da spec continua pedindo LLM no Critical. Manter o analyze do Spec Kit ali.

#### R4 — State machine por lane: relaxar a ordem, endurecer a evidência e os deveres de risco (P0 · esforço S)

Trocar o FEATURE_PHASES global por uma lista de passos por lane:
- Patch: implement, verify;
- Standard: spec, [clarify], verify-pre, implement, verify-post, review;
- Critical: as 7 fases.

O core deve recusar clarify SKIPPED quando o lane exige, e recusar COMPLETED sem registro de lane e evidência. O hack delivery.mode='agentic-outside-spec-master' dá lugar a um registro oficial de Patch ou Standard. As tentativas passam a ser indexadas por feature+fase, o que corrige o bug do guarded (A11).

**Ganho esperado:** Fecha os 3 buracos verificados (PASSED sem artefato, clarify pulado em L/auth, COMPLETED com fases PENDING) e dá caminho oficial para o que hoje é feito por fora.

**Riscos:** Migração do state.json existente (10 features). Resolver com migração idempotente, como a da traceability.

#### R5 — Matriz explícita: cortar, tornar opt-in, manter obrigatório (P1 · esforço M)

CORTAR
- tiers XS–XL e os rótulos sem efeito (analyze light/deep, review self/peer);
- sensibilidade por regex de prosa;
- 6 fases obrigatórias para qualquer mudança;
- camada normalizada de 3 docs regenerada a cada execução (→ um 'project brief' único sob demanda + change notes);
- bookkeeping manual do LLM (record-round por rodada, traceability add, budget file por prompt, delta snapshot) → automático ou derivado;
- gates de autoauditoria em cada relatório de feature (→ `doctor` em CI);
- loop de calibração até existir telemetria;
- template fixo de 6 work packages;
- refresh do dashboard a cada transição;
- referências fantasmas a 'CLAUDE.md §N'.

OPT-IN
- Team Mode (só Critical ou pedido explícito);
- guided intake (greenfield);
- knowledge graph + decision memory (ligados por gatilho de ADR);
- EARS, web bundle, dashboard, export OTLP, PR step, tracker;
- worktree waves (até existir executor paralelo);
- adapters além dos first-class e catálogo MCP completo;
- guarded mode para modelos menos robustos.

OBRIGATÓRIO em todos os lanes
- triagem registrada;
- regra anti-alucinação (classificar ao menos o que for INFERRED);
- escopo de escrita imposto pelo host;
- gates executáveis com evidência;
- conclusão por evidência de aceite;
- confirmação humana para ação irreversível (Princípio X);
- escalonamento automático;
- teto de reparo → BLOCKED;
- constitution existente usada como regras verificáveis, sem reescrita a cada execução.

**Ganho esperado:** A superfície obrigatória cai de ~40 comandos e ~91 imperativos para um núcleo de ~8–10 invariantes. O resto só é pago quando usado.

**Riscos:** Chesterton's fence: cada corte precisa registrar o porquê original (o guarded existe para modelos fracos; a anti-alucinação existe contra requisitos inventados). Por isso esses itens vão para opt-in, não para o lixo.

#### R6 — Spec Kit como motor do lane Critical; spec-lite nativo para Standard (P1 · esforço M)

O eixo passa a ser triage → execute → verify do harness. O Spec Kit vira um provider plugável do Critical, mantendo a regra 'nunca reimplementar speckit.*' onde ele é usado. O Standard usa um template spec-lite próprio (~1 página, derivado do spec-template, com seções de plano e tasks) e não exige .specify/ instalado. Na escalada, o spec-lite pode ser 'promovido' a spec do Spec Kit. A constitution segue única por repo e é lida pelo verificador.

**Ganho esperado:** Tira as 5 skills do Spec Kit (~15,5k tokens) e a exigência de .specify/ dos caminhos Patch e Standard. HIPÓTESE: isso cobre a maior parte das mudanças do dia a dia.

**Riscos:** Dois formatos de spec para manter. Mitigar derivando ambos do mesmo template.

#### R7 — Protocolo com progressive disclosure e teste de contrato entre protocolo e CLI (P1 · esforço S)

Quebrar o PROTOCOL.md (49,8 KB) em um roteador (≤5 KB) e um playbook por lane, carregado sob demanda: Patch ≤2 KB, Standard ≤8 KB, Critical = o atual. Remover ou restaurar as 11 referências a 'CLAUDE.md §N'. Adicionar à suíte o teste usado nesta avaliação: validar as 82 invocações documentadas contra build_parser (hoje 2 quebradas: `knowledge get --id` e `knowledge for-context`). No MCP, expor por padrão 6–8 tools de intenção (triage, next, verify, record_evidence, escalate, status) e deixar o catálogo de 76 atrás de uma flag.

**Ganho esperado:** Instrução de uma execução Patch cai de 13,2k para ~1,5–2k tokens; −~8,7k tokens de schema MCP por turno; drift entre protocolo e CLI passa a quebrar o CI.

**Riscos:** O conteúdo de cada lane precisa de testes próprios para não divergir do roteador.

#### R8 — Team Mode com isolamento real e pacotes derivados do diff (P1 · esforço M)

Reduzir os 12 papéis a 3–4 agentes efetivos: implementador; revisor independente; revisor de segurança quando houver superfície sensível; arquiteto quando houver mudança de fronteira. Implementá-los como subagentes do host com contexto limpo (.claude/agents/*.md e equivalentes), recebendo só diff + ACs + evidência. Os work packages passam a ser derivados das camadas realmente tocadas, sem o template fixo de 6 etapas, e os independentes rodam em paralelo. Corrigir o passo de carga de playbook.

**Ganho esperado:** Revisão com independência real (hoje é uma checagem de string no mesmo contexto). Elimina pacotes vazios (frontend/data-model em feature só de CLI). Permite paralelismo.

**Riscos:** Custo de tokens por subagente. Por isso ficam restritos a Standard (1 revisor) e Critical.

#### R9 — Telemetria automática do host; congelar calibração e métricas manuais (P2 · esforço S)

Parar de pedir ao LLM que registre rounds (hoje: 0 tokens e horários inventados). Coletar duração e tokens do host (hooks de sessão ou OTel do agente), com feature_id e lane preenchidos automaticamente. O dashboard passa a medir completude por evidência e lane, não por fases. Reativar a calibração dos limiares de lane só depois de ≥10 features com dados reais.

**Ganho esperado:** Remove ≥7 chamadas manuais por feature e os dados inválidos. O dashboard deixa de mostrar 30% para um produto 100% entregue.

**Riscos:** Nem todo host expõe tokens. Usar duração + número de turnos como fallback explícito.

#### R10 — Envelope do lane imposto pelo host (hooks) e guarded mode por feature (P1 · esforço M)

No Claude Code:
- PreToolUse bloqueia escrita fora do allowlist do passo (reusando PHASE_ALLOWED_WRITES por lane) e aplica a policy de verdade, não só como consulta;
- PostToolUse alimenta o escalonamento do R2;
- Stop/SubagentStop exige verify-post verde antes de declarar concluído;
- tudo empacotado como plugin (comandos + agents + hooks + MCP enxuto).

No guarded: indexar as tentativas por feature e oferecer o modo como opt-in para modelos menos robustos, não como caminho padrão.

Adapters: 3–4 hosts first-class com enforcement; os 33 gerados ficam como best-effort, sem promessa de paridade.

**Ganho esperado:** Regras de prosa viram invariantes do harness. O Patch fica seguro sem cerimônia documental. O guarded passa a funcionar com mais de 1 feature.

**Riscos:** Acoplamento às APIs de hooks de cada host. Manter o core agnóstico e os hooks finos.

### Perguntas abertas

- Qual foi o motivo concreto da pausa ('não usar o Spec Master para evoluir o Spec Master')? Custo e latência, recursão (a ferramenta mudando a si mesma durante a execução) ou qualidade dos artefatos? Isso muda o peso relativo de R1–R3.
- Qual a distribuição esperada de mudanças nos projetos-alvo (patch, feature, crítica)? Existem contextos regulados que exigem rastreabilidade formal para toda mudança, inclusive Patch?
- Quais hosts serão first-class para enforcement via hooks (Claude Code, Codex, Copilot, OpenCode)? Isso define onde implementar o envelope de lane (R10).
- Os hosts-alvo expõem telemetria real de tokens e tempo (ex.: OTel do agente) para calibrar os limiares dos lanes?
- O Spec Kit continua dependência obrigatória de instalação ou passa a ser provider opcional do lane Critical (R6)?
- Que nível de independência a revisão do Critical exige: outro contexto do mesmo modelo, outro modelo ou humano?
- A classificação EXPLICIT/INFERRED/UNRESOLVED deve valer também para as change notes do Patch, ou só para specs?

### Referências

- spec-master/PROTOCOL.md (Step 6, linhas 276-513; gates finais 616-633; referências 'CLAUDE.md §N')
- spec-master/lib/state.py (linhas 45-46 e 157-176)
- spec-master/lib/risk_profile.py (linhas 72, 83-104, 280-316)
- spec-master/lib/calibration.py (linhas 43-49)
- spec-master/lib/hooks.py (hooks sensitivity-*)
- spec-master/lib/cli.py (linhas 108-118)
- spec-master/lib/controller.py (linhas 192-218 e 272-284)
- spec-master/lib/phase_contracts.py
- spec-master/lib/phase_runner.py (linha 136)
- spec-master/lib/execution_mode.py
- spec-master/lib/fingerprint.py (linhas 14-18)
- spec-master/lib/team_model.py (linha 509)
- spec-master/lib/team_workstreams.py (linhas 24-37)
- spec-master/lib/tool_policy.py (linha 53)
- spec-master/lib/evals.py (linhas 17-45)
- spec-master/lib/quality_gates.py
- spec-master/knowledge/agile/galls-law.md, goodharts-law.md, chestertons-fence.md; foundations/yagni.md, kiss.md; anti-patterns/cargo-cult.md
- spec-master/knowledge/playbooks/spec-master.md (linhas 29 e 34)
- .claude/commands/spec-master.md
- .claude/skills/speckit-{specify,clarify,plan,tasks,analyze,implement,converge,checklist}/SKILL.md
- .specify/templates/{spec,plan,tasks}-template.md
- .specify/memory/constitution.md (Princípios III e IV)
- .spec-master/state.json
- .spec-master/metrics/rounds.json
- .spec-master/reports/harness-revalidation.md e harness-100-upgrade.md
- docs/market-benchmark-roadmap.md (linhas 123-207)
- docs/spec-master/guarded-mode-spec.md (§1)
- specs/003-parallel-worktree-execution/validation-report.md
- specs/005-speckit-tracker-orchestration/validation-report.md
- Commits 06dcef0, 1e37327, 165f1de, 6c31029 (git show --stat)
- Reprodução: <scratch>/cerimonia/xs_path.sh e xsproj/ (caminho XS, escalada XS→M, clarify SKIPPED em L, feature 'ghost' COMPLETED); scratchpad/cerimonia/gm/ (bug do guarded com 2 features)

---

## Maturidade de harness

### Resumo

Como biblioteca determinística, o Spec Master é sólido: 13,7k linhas de Python stdlib e 631 testes que passam em 3,7 s. Como harness, porém, quase tudo é só DECLARADO. No modo padrão (hosted/nativo), o loop, os gates de fase, a política de ferramentas, o budget de contexto, os hooks e as métricas dependem de o modelo ler integralmente 49,7KB de protocolo (~12,4k tokens) e chamar ~70 comandos de CLI por feature. Nenhuma primitiva do host impõe regra alguma: não há settings.json, hooks, subagentes, plugin nem .mcp.json.

O único loop que o Spec Master de fato controla é o guarded mode (controller + OpenCode). Ele não está ligado ao /spec-master e não tem smoke test com modelo real versionado. Além disso, falha em repos com várias features: dá falso PASSED quando a fase edita o plan.md de uma feature antiga e falso BLOCKED por placeholders de features antigas.

Evidências medidas:
- o bypass do state via `upsert-feature`;
- 11 de 16 comandos destrutivos aprovados pelo `tool_policy`;
- 9 de 9 rodadas com tokens 0 e timestamps fabricados;
- 5 'evals' triviais que sempre passam;
- 7 de 10 features COMPLETED com todas as fases PENDING.

As auditorias anteriores (73/100 e '100% readiness') contam a existência de um comando como se fosse capacidade. Minha nota honesta como harness é ~31/100.

Proposta: inverter o controle. Um kernel determinístico enxuto (state com invariantes, contratos de fase por feature, política, risco, gates) é exposto por uma API transacional (`phase begin/end`) e imposto pelo host por bindings finos:
- hooks PreToolUse, Stop, SubagentStop e SessionStart(compact);
- subagentes ou skills `context: fork` por fase;
- workflow script;
- plugin com marketplace;
- OTel real e `claude plugin eval`.

No modo self-hosted, o mesmo kernel roda via `claude -p --bare`, Agent SDK, `codex exec` e `opencode run`, em worktrees descartáveis.

Um protótipo no scratchpad (~100 linhas reaproveitando phase_contracts, tool_policy e state) já impõe os gates em 28–33 ms por decisão. Ganhos esperados:
- instrução por fase de ~12,4k para ~1,5k tokens;
- turnos estruturais por feature de ~71 para ~14 (ou ~0 com workflow);
- métricas medidas em vez de declaradas;
- eval comportamental com baseline sem plugin.

### Métricas

| Métrica | Valor | Método |
|---|---|---|
| Tamanho do protocolo lido integralmente a cada execução | 49.778 bytes / 837 linhas / ~12,4k tokens; 14 referências a 'CLAUDE.md §N', arquivo que o .gitignore exclui | wc -c / wc -l spec-master/PROTOCOL.md; tokens = bytes/4; grep -c CLAUDE.md; .gitignore linha 1 |
| Instruções Spec Kit acumuladas nas 7 fases (modo nativo, mesmo contexto) | 91.432 bytes ≈ 22,9k tokens (specify 18,4KB e clarify 19,3KB são as maiores) | wc -c em .claude/skills/speckit-{constitution,specify,clarify,plan,tasks,analyze,implement}/SKILL.md |
| Base de conhecimento e playbooks | 242KB em 91 arquivos .md; os playbooks somam 45.094 bytes ≈ 11,3k tokens | du -sb spec-master/knowledge; find -name '*.md' \| wc -l; wc -c knowledge/playbooks/*.md |
| Chamadas estruturais à CLI exigidas pelo protocolo (estimativa) | ~50 por feature + ~21 fixas por execução ≈ 71 turnos de LLM para 1 feature e ~171 para 3, só de contabilidade | Contagem derivada dos Steps 0–8 do PROTOCOL.md (14 state transition, 7 record-round + 7 edições do rounds.json, 2 risk classify, traceability add etc.). HIPÓTESE: não há transcripts reais para confirmar |
| Latência da CLI versus Python puro | 105–163 ms por chamada contra 11–12 ms de 'python3 -c pass'; o custo vem de importar ~35 módulos no topo do cli.py | date +%s%N em torno de 6 comandos; python3 -X importtime |
| Overhead dos hooks internos numa transição de estado | 125–139 ms sem hooks contra 133–148 ms com hooks (~+10 ms, incluindo re-render do dashboard) | state transition --no-hooks vs. com hooks, 2 repetições, em cópia do repo no scratchpad |
| Superfície MCP | 76 tools (47 readOnly, 29 com escrita); tools/list = 32.564 bytes ≈ 8,1k tokens; um subprocess por chamada; o servidor não está registrado (.mcp.json ausente) | JSON-RPC initialize + tools/list via stdin no spec_master_mcp.py (cópia no scratchpad) |
| Parsers da CLI | 102 add_parser | grep -c 'add_parser(' spec-master/lib/cli.py |
| Eficácia do tool_policy contra comandos destrutivos | 11 de 16 classificados ALLOWED/low (git push -f, git -C . push --force, git push origin +main, git clean -xfd, python -c shutil.rmtree, node -e rmSync, git branch -D main, git restore --source=HEAD~5 ., uvx, pip install, npm run) | tool_policy.classify_command em 16 probes |
| Evals do harness | 5 checagens com entradas hardcoded, 100% pass em 217 ms; nenhuma lê o projeto ou avalia o agente | python3 cli.py evals run; leitura de evals.py:20-41 |
| Testes unitários do core | 631 passed + 37 subtests em 3,67 s | pytest (venv no scratchpad) em spec-master/tests da cópia |
| Coerência do estado persistido | 7 de 10 features COMPLETED com as 7 fases PENDING; dashboard em 30% (21 de 70 fases); state sem 'execution'/'attempts' (guarded nunca rodou no repo) | leitura de .spec-master/state.json; cli dashboard model |
| Qualidade das métricas registradas | 9 de 9 rodadas com tokens=0; r1–r4 com duração ~0 s; r5–r9 com horários redondos inventados (00:00→00:05, 300/1200/3300/2700 s); o dashboard deriva 31,4 pacotes/h | leitura de .spec-master/metrics/rounds.json; dashboard model |
| Razão spec:código nas features de dogfood | 8,7x / 12,5x / 12,2x em bytes (4,3x–5,4x incluindo testes) para módulos de 92–131 linhas | du -sb specs/003..005 vs. wc -c do módulo lib e do teste correspondente |
| Distribuição do código por camada de harness | loop/controle 1.707 de 13.691 linhas (12,5%); contexto/conhecimento 3.645 (26,6%); distribuição/superfície 3.097 (22,6%); política/gates 1.864 (13,6%); observabilidade 1.791 (13,1%); team/git 1.587 (11,6%) | script de contagem de linhas por grupo de módulos |
| Grafo do projeto e gates no próprio repo | 4 nós / 3 arestas com 'health 100/100 (A)'; 'gates detect' retorna [] (os 631 testes não viram gate) | cli graph stats; graph-health.md; cli gates detect --path . |
| Uso do fluxo pelo próprio mantenedor | 3 de 16 itens do roadmap entregues pelo fluxo; 13 de 16 feitos fora dele | docs/market-benchmark-roadmap.md:172-204; state.json delivery.mode |
| Latência de um hook imposto pelo host (protótipo) | 28–33 ms por decisão PreToolUse/Stop reaproveitando phase_contracts, tool_policy e state sem alterações | sm_guard.py no scratchpad com JSON simulado no formato de hook do Claude Code |
| Custo do snapshot do guarded mode | 12 ms para 344 arquivos / 2MB, executado 2x por tentativa; ignora .gitignore e cresce linearmente com o repo | time.perf_counter em phase_contracts.snapshot na cópia |

### Scorecard

| Dimensão | Nota | Máximo | Justificativa |
|---|---:|---:|---|
| Loop de execução e controle de fluxo | 3 | 10 | No modo hosted o loop é prosa (.claude/commands/spec-master.md:10-13). O controller é real (tentativas, timeout, lock, retry sem transcript, fingerprint), mas só para OpenCode, desligado do entrypoint e sem smoke test real versionado; o modo 'auto' é só um rótulo (controller.py:314/362). |
| Máquina de estados e gates de fase | 4 | 10 | 'transition' rejeita implement antes de analyze (testado), mas o upsert-feature é um bypass. Nada acopla o estado às ferramentas do host, e o repo tolera 7 features COMPLETED com todas as fases PENDING. |
| Engenharia de contexto (seleção, compactação, carregamento progressivo) | 3 | 10 | Pontos fortes: camada WHAT/WHY/HOW, fingerprint/delta e router de conhecimento. Mas o protocolo de ~12,4k tokens é lido integralmente, o budget só é aplicado no web bundle, o limite é por contagem de módulos, o prompt do guarded tem uma frase, e nada sobrevive bem à compactação (teto de 5k tokens por skill). |
| Política de ferramentas, permissões e sandbox | 1 | 10 | O preflight não é chamado por nada no caminho de execução; o próprio controller roda gates com shell=True sem preflight e sem timeout. A denylist aprovou 11 de 16 comandos destrutivos. Não há settings permissions nem sandbox. |
| Hooks de ciclo de vida | 2 | 10 | O barramento de eventos interno é bem desenhado e testado, mas nenhum hook do host é usado. As diretivas são consultivas e o controller as descarta; só raise_tier e as ações internas têm efeito. |
| Subagentes e isolamento de contexto | 3 | 10 | O guarded dá uma sessão OpenCode nova por fase (real). No hosted não há subagentes: os 12 papéis do Team Mode e o 'peer review' são personas no mesmo contexto, e o worktree.py só cria worktrees, sem disparar agentes. |
| Verificação (gates, testes, loops de correção) | 5 | 10 | Pontos fortes: gates e SAST detectados por evidência, contratos de fase, limite de 3 ciclos de analyze no state. Mas os gates não têm timeout, o controller não executa o analyze→repair, os globs globais geram falso PASS/FAIL, e o 'gates detect' não acha nenhum gate no próprio repo. |
| Recuperação (retry, checkpoint, resume) | 4 | 10 | O controller oferece tentativas limitadas, lock com expiração, pulo por fingerprint e revalidação de contrato. Não há rollback nem quarentena de escritas proibidas (só o transcript é copiado) e não há checkpoint por worktree. No hosted, o resume depende do prompt. |
| HITL (humano no loop) | 5 | 10 | Os gates estão bem definidos (git strategy, clarify em lote, constitution, PR com confirmação explícita), e o guarded pausa quando há user_decision_required. No hosted, porém, tudo depende do prompt, e o final-report registra a constitution como 'GENERATED — not approved'. |
| Estado e memória persistentes | 5 | 10 | Escrita atômica, rastreabilidade por feature e memória de decisão no grafo. Faltam validação de esquema e invariantes; o estado do próprio repo é contraditório (state vs. dashboard). |
| Observabilidade (traces, tokens, custo) | 2 | 10 | Existem firings.jsonl, dashboard e export OTLP, mas os dados são autodeclarados: 9 de 9 rodadas com tokens 0 e timestamps fabricados. Não há traces, e o OTel nativo do host é ignorado. |
| Evals comportamentais | 1 | 10 | Os 5 'evals' são checagens estáticas com entradas hardcoded; nenhuma avalia o agente. Os 631 testes são testes de software, não evals de agente. fixtures/fake_agent.py é uma semente reaproveitável. |
| Empacotamento e distribuição | 4 | 10 | Pontos fortes: init.sh com engine global, 30+ entrypoints gerados e um MCP stdlib que funciona. Mas não há plugin nem marketplace, o MCP não está registrado, os adapters estão defasados (commands vs. skills) e não há config de host versionada. |
| Segurança | 2 | 10 | O gate de SAST/secrets baseado em evidência é bom, e há PROTECTED_PATHS, mas só no guarded e só depois do fato. Não há sandbox, PreToolUse nem proteção de .env ou segredos; a denylist é contornável. |
| TOTAL (normalizado) | 31 | 100 | 44 de 140 nas 14 dimensões ≈ 31/100. Compare com 73/100 na harness-revalidation e '100% readiness' na harness-100-upgrade, que pontuam a existência de comandos e código como capacidade imposta. Como biblioteca determinística a qualidade é alta; como harness, a maior parte é DECLARADA. |

### Achados

#### H1 — O loop só é do Spec Master no guarded mode (OpenCode), que está desligado do entrypoint; o modo 'auto' é só um rótulo (impacto: alto)

No modo padrão (/spec-master no Claude Code, Copilot, Codex, Qwen, e no OpenCode via init.sh), o fluxo é 100% conduzido pelo modelo seguindo prosa ('leia e siga esse arquivo integralmente'). O controller é o único ponto IMPOSTO: 2 tentativas, timeout de 600 s, lock com expiração, retry sem transcript, pulo por fingerprint e revalidação de contrato. Mas há quatro limitações. Primeiro, só existe a integração 'opencode'. Segundo, ligar --mode ao /spec-master ficou fora de escopo. Terceiro, o smoke test com modelo real foi pulado. Quarto, o state do repo não tem 'execution' nem 'attempts', ou seja, o dogfood rodou nativo. O modo 'auto', padrão pela GM-002, é cosmético: active_mode só altera print e relatório, e o mesmo runner OpenCode roda em auto e em guarded. Numa sessão hosted não existe detector de comportamento inseguro. Nuance: final-report.md cita um bug achado rodando o controller contra 'qwen-greeting-api', então houve uso real fora do repo, mas sem transcript versionado.

**Evidência:** .claude/commands/spec-master.md:10-13 e :34; phase_runner.py:136 'INTEGRATIONS = {"opencode": _run_opencode}'; specs/001-guarded-mode-controller/tasks.md:21-23 ('wiring --mode into the /spec-master ... out of scope') e :288-290 ('real model smoke test ... skipped'); grep active_mode → só controller.py:314, 362, 444; 'execution' in state.json → False

#### H2 — Zero integração com as primitivas de enforcement do host (impacto: alto)

Não existem .claude/settings.json (permissions/hooks), .claude/agents/, .claude-plugin/plugin.json, marketplace, .mcp.json, workflows/ nem evals/. Nos outros hosts também não há .github/hooks, hooks.json do Codex, o agente OpenCode 'spec-phase' (que a guarded-mode-spec §11 exige, com skill loading negado e web desabilitada) nem plugin tool.execute.before. Todos os entrypoints são ponteiros em prosa. Os 4 hosts principais oferecem hoje PreToolUse bloqueante, Stop/SubagentStop, SessionStart e agentes com allowlist, e nenhum desses recursos é usado.

**Evidência:** ls: 'cannot access .mcp.json / .claude/settings.json / .claude/agents / .claude-plugin / .opencode / AGENTS.md'; init.sh:268-300 (o OpenCode recebe só um comando .md com 'Regras obrigatorias' em prosa); grep 'spec-phase' só encontra o código Python e a spec; adapters/claude-code.md:25-37

#### H3 — Os 'hooks declarativos' são um barramento de eventos consultivo, não hooks de ciclo de vida (impacto: alto)

hooks.emit só roda quando algo chama a CLI (state transition, risk classify, team escalate/resolve, hooks emit) ou quando o controller o chama. Das 14 regras default, só as ações internas (render_dashboard, record_decision) são executadas pelo core. As demais devolvem 'directives' (repair, escalate, revalidate, block, notify) em JSON para o agente 'seguir'. O controller descarta o retorno de safe_emit, então nunca repara nem escala sozinho, e nenhuma regra default usa 'block'. O único consumo real de diretiva pelo core é raise_tier dentro de risk classify. O próprio protocolo reconhece: 'Hooks are advisory plumbing'.

**Evidência:** hooks.py:11-15, 52-53, 451-456; controller.py:62-64 (hooks.safe_emit sem uso do retorno); risk_profile.py:507; PROTOCOL.md:545-560; .spec-master/hooks/firings.jsonl inexistente no repo; overhead medido de ~10 ms

#### H4 — 'policy preflight' não intercepta nenhuma ferramenta e a denylist por string é fraca (impacto: alto)

tool_policy.preflight só é chamado pelo comando 'cli policy preflight' e por evals.py. O próprio controller roda os gates com subprocess shell=True, sem preflight e sem timeout: um teste em watch mode trava a execução. A classificação por string aprovou 11 de 16 comandos destrutivos como allowed/low. A auditoria harness-100 dá como FECHADO o gap 'No internal tool proxy/firewall' só por existir esse comando, o que é inflado: um classificador opcional que o próprio modelo precisa chamar não é firewall nem sandbox.

**Evidência:** grep tool_policy → cli.py:622 e evals.py:26; phase_runner.py:62-71 ('subprocess.run(gate["command"], shell=True, ...)' sem timeout); comandos aprovados: 'git push -f origin main', 'git -C . push --force', 'git clean -xfd', 'python3 -c "import shutil; shutil.rmtree(...)"', 'git branch -D main', 'git restore --source=HEAD~5 .', 'uvx some-unvetted-package'; harness-100-upgrade.md, tabela 'Closed Gaps'

#### H5 — A máquina de estados tem guard real, mas bypass trivial, e aceita estado incoerente (impacto: alto)

'state transition' rejeita implement antes de analyze, ou seja, a regra é IMPOSTA na CLI. Já 'state upsert-feature' aceita qualquer mapa de fases e status: aceitou implement e validate PASSED com status COMPLETED e todas as fases anteriores PENDING. No modo hosted nada impede Edit ou Write direto em .spec-master/state.json; PROTECTED_PATHS só vale no guarded, e só depois do fato. O próprio repo tem 7 de 10 features COMPLETED com as 7 fases PENDING, enquanto o dashboard mostra 30% de completude: duas 'verdades' simultâneas.

**Evidência:** state.py:141-154 (upsert sem validação) vs. 157-177 (transition com pré-requisito). Saídas: transition → 'cannot start/pass implement before analyze has PASSED'; upsert → 'aceito: COMPLETED {... implement: PASSED, validate: PASSED}'. dashboard model → completeness 30.0, phase_totals {PENDING: 49, PASSED: 21}

#### H6 — Observabilidade autodeclarada: métricas com tokens zero e timestamps fabricados (impacto: alto)

'metrics record-round' apenas ecoa os valores de início, fim e tokens informados pelo agente, que depois anexa a linha ao rounds.json editando o arquivo à mão. Resultado nas 9 rodadas:
- tokens=0 em todas;
- r1–r4 com duração ~0 s;
- r5–r9 com horários redondos inventados (00:00:00Z→00:05:00Z, 300/1200/3300/2700 s), sobrepostos entre features.

O dashboard calcula '31,4 pacotes/h' em cima disso, e a calibração de tiers e o export OTLP operam sobre os mesmos números. Enquanto isso, o host já emite OTel real (claude_code.token.usage, cost.usage, tool_result.duration_ms, spans llm_request/tool), e o 'claude -p --output-format json' devolve total_cost_usd e usage.

**Evidência:** cli.py:455-472; .spec-master/metrics/rounds.json (r5 '2026-09-26T00:00:00Z'→'00:05:00Z'; r8 '00:05:00Z'→'01:00:00Z'); dashboard model metrics {total_tokens: 0, packages_per_hour: 31.385}; teste: record-round aceitou 5 h, 99 pacotes e 0 tokens sem questionar

#### H7 — Performance: o custo de contexto e de turnos de LLM domina; o Python não é o gargalo (impacto: alto)

No modo nativo o contexto acumula instrução e saídas de ferramenta ao longo da execução:
- PROTOCOL.md completo (~12,4k tokens);
- as 7 skills Spec Kit (~22,9k);
- playbooks do Team Mode (~11,3k);
- artefatos (~12k por feature);
- saídas JSON da CLI (só 'state show' tem 3,8k tokens; 'hooks list' tem 2,2k).

Como cada decisão estrutural é uma chamada de CLI, e cada chamada é um turno de LLM, estimo ~71 turnos só de contabilidade para 1 feature. A CLI custa 100–160 ms por chamada e os hooks ~10 ms, o que é irrelevante perto disso. Além disso, após compactação o Claude Code re-anexa no máximo 5k tokens por skill, então o protocolo monolítico não sobrevive íntegro. A própria guarded-mode-spec §1 lista 'perder a fase atual depois de uma compactação' como modo de falha.

**Evidência:** wc: PROTOCOL.md 49.778 B / 837 linhas; skills das fases 91,4KB; medições: runtime contract 119 ms, state show 105 ms, python -c pass 11 ms; -X importtime; contagem derivada dos Steps 0–8 (HIPÓTESE para os turnos); docs de Skills: 're-attaches ... up to 5,000 tokens per skill'

#### H8 — Engenharia de contexto: o orçamento é só estimado e não chega às sessões isoladas (impacto: medio)

context_budget.budget_items só é aplicado no web bundle. No fluxo do agente, o protocolo apenas pede que o modelo rode 'budget file' e liste o que foi omitido, ou seja, é DECLARADO. Knowledge router e graph context limitam por contagem (8 módulos, N nós), não por tokens. No guarded mode, a única execução isolada, o prompt é uma frase ('Execute /speckit.{phase}... you may only write to: ...'). Ele não inclui o contexto normalizado, templates/prompts/<fase>.md, playbooks nem decisões. Toda a engenharia de contexto construída fica fora da sessão que mais precisa dela.

**Evidência:** grep context_budget → só web_bundle.py:577-596, cli.py:629-636 e evals.py; controller.py:137-152 (_render_prompt); grep 'templates/prompts|knowledge|budget' em controller, phase_runner e opencode_runner → nenhum uso; knowledge/router.py (orçamento por número de módulos)

#### H9 — O guard existente tem falhas de correção em repos multi-feature e não reverte escritas proibidas (impacto: medio)

validate_artifacts e placeholder_artifacts usam globs globais (specs/*/...). Neste repo:
- a fase plan nunca acusa artefato ausente, e editar o plan.md de uma feature ANTIGA conta como required_changed sem forbidden write → falso PASSED;
- tasks e implement acusariam placeholder por causa do texto 'NEEDS CLARIFICATION' em specs/002/tasks.md → falso FAILED/BLOCKED permanente;
- a correção por feature ativa (resolve_active_feature_dir) só foi aplicada aos no-ops de clarify e analyze.

Escritas proibidas são detectadas depois, por snapshot SHA-256 do repo inteiro feito 2x por tentativa (ignorando .gitignore), mas nunca revertidas: _preserve_failed_attempt copia só o transcript, contrariando a spec §12. Por fim, 'gates detect' retorna [] no próprio repo (Python stdlib), então a fase validate passaria sem rodar os 631 testes.

**Evidência:** phase_contracts.py:34-43, 113-119, 161-170; saída na cópia: plan missing=[] e required_changed=True/forbidden=[] editando specs/001/plan.md; specs/002-guarded-noop-phase-validation/tasks.md:73, 84, 142; controller.py:128-133; guarded-mode-spec.md §12; gates detect → []; quality-gates.md ('No quality gates detected ... run directly')

#### H10 — A cerimônia 'adaptativa' corta pouco; o próprio dogfood evidencia overengineering (impacto: alto)

O tier só permite pular clarify; 'analyze: light' não é lido por nenhum template nem pelo controller. Uma mudança XS ainda passa por 6 fases de LLM e gera o conjunto completo de artefatos do Spec Kit (research, data-model, contracts, quickstart, checklists). Nas features de dogfood, a razão spec:código foi de 8,7x a 12,5x em bytes (4,3x–5,4x incluindo testes) para módulos de 92 a 131 linhas. O mantenedor pausou o fluxo ('não usar o Spec Master para evoluir o Spec Master') e entregou 13 dos 16 itens do roadmap fora dele. Do ponto de vista de harness, cerimônia sem enforcement e sem medição é custo sem garantia.

**Evidência:** risk_profile.py:83-92, e grep 'light' não encontra consumidores; state.py SKIPPABLE_PHASES=('clarify',); du -sb specs/003..005 = 47,7–54,8KB vs. worktree.py 5,5KB, team_workstreams.py 4,0KB, tracker_orchestration.py 4,5KB; docs/market-benchmark-roadmap.md:172-179

#### H11 — Superfície de ferramentas excessiva e adapters defasados em relação ao host e ao Spec Kit (impacto: medio)

Os 102 parsers da CLI viram 76 tools MCP (29 com escrita). O tools/list ocupa 32,5KB (~8,1k tokens), cada chamada abre um subprocess Python, e o servidor nem está registrado. Uma superfície tão granular obriga o modelo a orquestrar passo a passo. O adapter do Claude Code afirma que o host 'não tem como invocar outro slash command' e aponta para .claude/commands/speckit.<phase>.md. Porém o Spec Kit 0.16.4 instalou skills (.claude/skills/speckit-*/SKILL.md), que o Skill tool invoca e que podem rodar isoladas com 'context: fork'. O Spec Kit 0.16.4 também traz um motor de workflow próprio com gates, que se sobrepõe à orquestração do Spec Master.

**Evidência:** grep -c add_parser → 102; tools/list → 76 tools, 47 readOnly, 32.564 B; spec_master_mcp.py:615 (subprocess.run por chamada); adapters/claude-code.md:31-37; .specify/integrations/claude.manifest.json; .specify/workflows/speckit/workflow.yml

#### H12 — Auditorias anteriores infladas, evals triviais e fonte das regras fora do versionamento (impacto: medio)

A harness-revalidation (73/100) dá 10/10 em 'Orchestration and deterministic control' e 8/8 em 'Persistent state'. Ignora o bypass por upsert e o fato de que, no modo hosted, o controle é prosa. A harness-100-upgrade declara '100% readiness' redefinindo o escopo e contando a existência de um comando como capacidade:
- policy preflight tratado como firewall;
- budget estimate tratado como budget aplicado;
- 'evals run' tratado como eval.

Os 5 evals usam entradas hardcoded e sempre passam. O grafo 'populado' tem 4 nós e 3 arestas e recebe health 100/100 (A). O PROTOCOL.md cita 'CLAUDE.md §N' 14 vezes, mas o CLAUDE.md está no .gitignore e não existe no repo: as regras normativas não são rastreáveis por outros usuários ou hosts. Mérito real: os 631 testes e o fixture fake_agent.py, boa semente para evals.

**Evidência:** harness-revalidation.md, tabela 'Score v2'; harness-100-upgrade.md ('Readiness: 100% for Hosted/Hybrid'); evals.py:20-41; cli graph stats → 4 nós/3 arestas; graph-health.md; grep -c CLAUDE.md PROTOCOL.md → 14; .gitignore:1 = 'CLAUDE.md'; pytest → 631 passed

### Recomendações

#### R1 — Arquitetura-alvo: inverter o controle com um kernel determinístico e bindings finos por host (P0 · esforço L)

(1) O HOST fornece:
- inferência e o loop de ferramentas;
- permissões e sandbox (settings permissions, sandbox de Bash);
- hooks de ciclo de vida;
- subagentes com contexto isolado (.claude/agents, context: fork, isolation: worktree);
- runtime de workflows (agent/pipeline/parallel com schema);
- OTel;
- plugin, marketplace e 'claude plugin eval'.

(2) O SPEC MASTER possui o KERNEL, que é o core atual enxugado em stdlib:
- state machine com invariantes;
- contratos de fase por feature ativa;
- política (allowlist de caminhos por fase; classificação de comandos só como defesa em profundidade);
- risco → perfil de cerimônia;
- gates com timeout;
- rastreabilidade e memória de decisão.

O kernel é exposto por uma API transacional (R3) e por um entrypoint único de hooks, o 'hookd' (R2).

(3) BINDINGS gerados a partir de um único arquivo de política:
- Claude Code: plugin com hooks/hooks.json, agents/, skills/, workflows/, .mcp.json e evals/;
- Codex: hooks.json + AGENTS.md;
- Copilot CLI: .github/hooks/*.json + .github/agents/*.agent.md;
- OpenCode: .opencode/agents/spec-phase.md com permission + .opencode/plugins/spec-master.js com tool.execute.before chamando o hookd;
- os demais ~26 agentes ficam num tier explícito 'prompt-only', sem garantias.

(4) MODOS de execução:
- HOSTED: plugin dentro do host, com workflow script ou skill-roteador + subagentes por fase, e HITL nas fronteiras de estágio;
- SELF-HOSTED: o controller.py generalizado com integrações para 'claude -p --bare --plugin-dir ... --agents ... --json-schema PhaseResult --output-format json --max-turns N --permission-mode dontAsk --allowedTools ...', para o Agent SDK (canUseTool = motor de política, hooks como callbacks), para 'codex exec --sandbox workspace-write --output-schema' e para 'opencode run --agent spec-phase'. Cada tentativa roda numa worktree descartável.

**Ganho esperado:** O mesmo kernel já testado (631 testes) passa a ser IMPOSTO em todos os modos. Acaba a dicotomia 'hosted = prosa / guarded = só OpenCode e nunca ligado'. A orquestração passa a ser código, e o modelo fica só com o trabalho semântico.

**Riscos:** A semântica de hooks difere entre hosts (ex.: issue #3874 do Copilot CLI sobre deny em preToolUse). Manter N bindings tem custo. Há migração para quem já usa o init.sh e a CLI atual.

#### R2 — hookd: impor os gates via hooks do host, começando pelo Claude Code (P0 · esforço M)

Um script Python de ~100–200 linhas recebe o JSON do hook e consulta o kernel:
- PreToolUse(Edit|Write|MultiEdit|NotebookEdit): nega escrita fora de PHASE_ALLOWED_WRITES da fase RUNNING e em PROTECTED_PATHS (state.json, logs, failed-attempts);
- PreToolUse(Bash): aplica a política de comandos (deny/ask);
- Stop/SubagentStop: sai com código 2 se a fase RUNNING não tem artefatos válidos, bloqueando 'declarar sucesso sem artefato';
- SessionStart(startup|resume|compact) e UserPromptSubmit: injetam o phase card (R4);
- PostToolUse(Skill speckit-*): dispara 'phase end'.

Distribuir via hooks/hooks.json do plugin, ou no frontmatter 'hooks:' da skill spec-master, que só registra os hooks quando o Spec Master é invocado e não afeta o trabalho normal. Oferecer escape hatch auditado ('sm override --reason', registrado em overrides.jsonl). Um protótipo funcional já está no scratchpad.

**Ganho esperado:** Converte ~10 regras hoje DECLARADAS em IMPOSTAS no modo padrão: nada de implementar antes de tasks/analyze, allowlist por fase, state protegido, comandos perigosos barrados, fase só termina com artefato. As classes early_implementation e false_phase_completion, que hoje só o guarded detecta e só depois do fato, passam a ser bloqueadas antes. Latência medida: 28–33 ms por decisão.

**Riscos:** Falsos bloqueios em trabalho legítimo; mitigar atuando só com fase RUNNING e oferecendo override auditado. O usuário pode desligar com disableAllHooks; registrar isso na trilha. A latência sobe se o hookd importar o cli.py inteiro; usar imports mínimos, como no protótipo.

#### R3 — API transacional de fase: a contabilidade passa a ser feita pelo código, não pelo modelo (P0 · esforço M)

Substituir ~40 comandos finos por 3–4 transações:
- 'sm phase begin --feature F --phase P': valida pré-requisitos e tier, marca RUNNING, grava o timestamp real e devolve phase card + allowlist + bundle de contexto já orçado em tokens + schema do PhaseResult;
- 'sm phase end --feature F --phase P --result r.json': valida o contrato escopado pela feature ativa, roda os gates quando a fase é validate, transita PASSED/FAILED, emite eventos, sincroniza rastreabilidade, grava métricas medidas e atualiza o dashboard;
- 'sm run next': devolve a próxima ação.

Remover a entrada manual de started_at, ended_at e tokens em 'metrics record-round' (passam a vir do kernel e da telemetria do host, R8). Validar invariantes de status × fases no upsert-feature. Resumos da CLI com no máximo 1k tokens.

**Ganho esperado:** Estimativa: de ~71 para ~14 turnos estruturais por feature (2 por fase), ou ~0 quando a orquestração é feita por workflow ou hook. Fim das métricas fabricadas e do bypass por upsert. Menos tokens de saída de ferramenta no contexto.

**Riscos:** Quebra de compatibilidade com o protocolo atual; manter aliases por uma versão. Transações maiores exigem testes de atomicidade e rollback.

#### R4 — Phase cards e carregamento progressivo no lugar do protocolo monolítico (P0 · esforço S)

Quebrar o PROTOCOL.md (837 linhas, ~12,4k tokens) em três partes:
- (a) uma SKILL roteadora de até 500 linhas, só com regras permanentes: anti-alucinação, divisão core/agente, uso de begin/end;
- (b) phase cards por fase, de ~1–1,5k tokens, renderizados pelo kernel com o estado atual (feature, tier, allowlist, ACs, pendências) e injetados via !`python3 …/cli.py phase card`, SessionStart(compact) ou UserPromptSubmit;
- (c) material de referência carregado só sob demanda: MCP, web bundle, PR step, calibração, EARS, portabilidade, instalação.

Eliminar as 14 referências 'CLAUDE.md §N' (arquivo que o .gitignore exclui) ou versionar essa fonte normativa. Atualizar o adapter: as fases Spec Kit são skills invocáveis pelo Skill tool.

**Ganho esperado:** De ~12,4k para ~1–1,5k tokens de instrução por fase (−88% a −92%). O card cabe no teto de 5k tokens re-anexado após compactação. Regras críticas deixam de ficar enterradas no meio de 50KB.

**Riscos:** Cards e kernel podem divergir; gerar os cards a partir dos mesmos dados (phase_contracts, perfis de risco) e cobri-los com testes.

#### R5 — Execução isolada por fase no modo hosted: subagentes, forked skills ou workflow (P0 · esforço M)

Criar um subagente por fase (speckit-specifier, -planner, -tasker, -analyzer, -implementer, -validator, -reviewer), cada um com:
- tools/disallowedTools (fases de documento sem Bash livre);
- maxTurns;
- model por fase (um modelo menor para tasks e para o lint de analyze);
- skills: [speckit-<fase>] pré-carregada;
- hooks no frontmatter com a allowlist da fase.

Alternativa: 'context: fork' nas skills. Em qualquer caso, o orquestrador recebe só um PhaseResult JSON validado por schema.

Opcionalmente, um workflow '/spec-master:run' com agent()/pipeline() e schema. Como workflows não aceitam input no meio da execução, dividir em estágios nos pontos de HITL: [intake + specify + perguntas de clarify] → usuário responde → [plan → tasks → analyze] → aprovação → [implement → validate].

O peer review do Team Mode vira um subagente revisor real, de contexto limpo, em vez de uma persona no mesmo contexto. Pacotes e features paralelos usam isolation: worktree.

**Ganho esperado:** O contexto principal cresce ~0,5k tokens de resultado por fase, em vez de acumular ~23k de skills Spec Kit + artefatos + ~50 saídas de CLI. A revisão passa a ser independente de verdade. Paralelismo real (hoje worktree.py só cria as worktrees). Permite modelo diferente por fase.

**Riscos:** Custo por subagente se o prefixo de cache não for compartilhado. Workflows sem input no meio exigem estágios. As descrições de subagentes somam num limite de 15k tokens.

#### R6 — Corrigir o guard existente antes de expandi-lo (P0 · esforço S)

Seis correções:
1. Escopar validate_artifacts, placeholder_artifacts e required_changed à pasta da feature ativa (.specify/feature.json) em todas as fases, não só nos no-ops.
2. Pôr timeout e política nos gates, que hoje rodam com shell=True sem timeout.
3. Fazer o controller agir sobre as diretivas dos hooks (repair, escalate, block) ou removê-las.
4. Rodar cada tentativa numa worktree ou branch descartável (ou git stash) para reverter escritas proibidas, como pede a spec §12.
5. Trocar o snapshot SHA-256 do repo inteiro por git status --porcelain / diff, que respeita o .gitignore.
6. Fazer o gates detect reconhecer projetos Python stdlib (tests/ com unittest/pytest) e ligar o ciclo analyze→repair (máx. 3) ao controller.

**Ganho esperado:** Elimina o falso PASSED (plan editando feature antiga) e o falso BLOCKED (placeholder em specs/002) em repos com várias features. O guard passa a funcionar no próprio repositório, e a fase validate passa a exigir os testes reais.

**Riscos:** Mudar o contrato de fase exige incrementar PHASE_CONTRACT_VERSION; o mecanismo de revalidação de tentativas antigas já existe.

#### R7 — Cerimônia adaptativa de verdade: caminho lite para XS/S (P1 · esforço M)

O tier passa a decidir QUAIS fases e QUAIS artefatos existem:
- XS/S → 'spec-lite': um único spec.md com ACs EARS e tasks inline → implement → gates. O analyze vira um lint determinístico: contratos de fase + cobertura de rastreabilidade + ears check.
- M → Spec Kit sem research, quickstart e checklists por padrão.
- L/XL e mudanças sensíveis → ciclo completo + revisor independente.

'analyze: light' precisa corresponder a um prompt ou checagem concreta. Os pisos de sensibilidade (auth, pagamento, segredos) continuam forçando o ciclo completo. Avaliar convergência com o motor de workflow do próprio Spec Kit (.specify/workflows).

**Ganho esperado:** XS/S passam de 6 fases de LLM para ~3. Meta de razão spec:código de ~9–12x para ~1–2x. O fluxo volta a ser viável para evoluir o próprio Spec Master; hoje 13 dos 16 itens foram feitos fora dele.

**Riscos:** Mudanças arriscadas classificadas como XS por engano ficariam sub-especificadas; mitigado pelos pisos de sensibilidade, pela reclassificação em pre_implement e pelos evals (R9).

#### R8 — Observabilidade real a partir do host; aposentar métricas autodeclaradas (P1 · esforço S)

No modo HOSTED:
- ligar CLAUDE_CODE_ENABLE_TELEMETRY com OTEL_RESOURCE_ATTRIBUTES por feature e fase (spec_master.feature, spec_master.phase), e spans (CLAUDE_CODE_ENHANCED_TELEMETRY_BETA);
- consumir claude_code.token.usage, cost.usage e tool_result (duration_ms);
- o hookd grava .spec-master/trace.jsonl com timestamps medidos em begin/end, mais session_id e transcript_path do evento.

No modo SELF-HOSTED: usar o JSON final do claude -p / SDK (total_cost_usd, usage, num_turns, duration_ms).

'metrics record-round' passa a ser derivado. A calibração só roda com dados medidos. O export OTLP próprio fica opcional.

**Ganho esperado:** Tokens, custo e latência reais por fase e por feature. Calibração de tiers e dashboard deixam de operar sobre zeros e horários inventados. Dá a base para medir os ganhos de R3–R7.

**Riscos:** Privacidade: prompts vêm redigidos por padrão; não ligar OTEL_LOG_USER_PROMPTS sem consentimento. Spans ainda estão em beta.

#### R9 — Evals comportamentais como gate de release, no lugar do 'evals run' (P1 · esforço M)

Criar evals/ para 'claude plugin eval' com 6–10 casos canônicos:
- bugfix XS;
- feature M;
- feature L sensível a auth;
- contexto ambíguo que exige clarify;
- prompt adversarial 'implemente já';
- retomada após compactação.

Priorizar graders sem custo: tool_order (Skill speckit-tasks antes de qualquer Edit em src/), file_exists (spec/plan/tasks), regex (nenhum 'NEEDS CLARIFICATION' restante) e tool_used com input_match nos comandos de gate. Usar poucos graders 'llm', com rubrica. Rodar com baseline sem plugin (Δ), --runs 3, --threshold e --max-cost-usd.

Complementar com uma suíte de replay determinística do hookd/guard sobre fixtures/fake_agent.py. Usar ablação para medir o valor da base de conhecimento, do Team Mode e de cada fase, e decidir cortes com dados.

**Ganho esperado:** Primeira medição objetiva de se o Spec Master melhora o resultado em relação a não usá-lo. Detecta regressões a cada troca de modelo. Transforma o debate sobre overengineering em números.

**Riscos:** Cada execução é uma chamada real de modelo com custo; usar --ablation none ao iterar e um teto de custo. Graders 'llm' variam; preferir graders determinísticos.

#### R10 — Empacotar como plugin com núcleo mínimo e mover a periferia para extras (P1 · esforço M)

Publicar um plugin: .claude-plugin/plugin.json + marketplace, com skills/, agents/, hooks/hooks.json, workflows/, evals/ e userConfig (host, tiers, gates). Trocar as 76 tools MCP por ~8 tools de alto nível: state_summary, phase_begin, phase_end, run_next, risk_classify, gates_run, trace_report, decisions_for_role. Oferecer equivalentes para Codex, Copilot e OpenCode; o init.sh vira bootstrap para hosts sem plugin.

Tirar do caminho de runtime, como extras opcionais congelados até um eval provar valor:
- web bundle;
- auto-render do dashboard;
- export OTLP próprio;
- calibração;
- subsistema de grafo (4 nós hoje);
- base de conhecimento genérica (manter os playbooks);
- gerador de 30+ adapters (manter os 4 hosts com binding real + o tier 'prompt-only' rotulado).

**Ganho esperado:** Schemas MCP de ~8,1k para ~1k tokens. Instalação versionada e atualizável. O caminho crítico fica concentrado em loop/controle + política + contratos (~3,6k das 13,7k linhas), reduzindo a superfície de erro e a manutenção.

**Riscos:** Afeta quem usa a CLI completa; mantê-la como 'expert mode'. Governança do marketplace. Diferenças de empacotamento entre hosts.

### Perguntas abertas

- Qual host é o alvo primário: Claude Code (hosted/plugin) ou OpenCode com modelos locais (guarded/self-hosted, ex.: qwen3-coder 30b)? A resposta define se R2/R5 ou o modo self-hosted de R1 vem primeiro.
- Existem transcripts reais (~/.claude/projects/...) das 3 features que passaram pelo fluxo? As contagens de ~71 turnos por feature e ~36k tokens de instrução são estimativas derivadas do protocolo (HIPÓTESE) e poderiam ser medidas.
- O Team Mode com 12 papéis é requisito de produto (multi-agente real, revisão independente) ou metáfora de governança? No primeiro caso exige subagentes (R5); no segundo pode virar checklists por tier.
- O que contém o CLAUDE.md que o .gitignore exclui? As seções §1–§43 citadas no PROTOCOL.md são normativas e só existem na máquina do autor?
- O Spec Master deve continuar dependente do Spec Kit em todos os tiers, ou pode ter um caminho 'spec-lite' próprio para XS/S? Deve convergir com o motor de workflow do próprio Spec Kit (.specify/workflows) ou com os workflows do Claude Code?
- Qual orçamento de custo e latência por feature é aceitável? Ele é necessário para calibrar tiers, --max-cost-usd dos evals e a escolha de modelo por fase.
- O final-report cita um bug achado rodando o controller contra 'qwen-greeting-api'. Há transcripts desse uso real que possam virar casos de replay e eval do guard?

### Referências

- spec-master/lib/hooks.py (linhas 11-15, 52-53, 425-456)
- spec-master/lib/tool_policy.py
- spec-master/lib/context_budget.py
- spec-master/lib/runtime_contract.py
- spec-master/lib/evals.py (linhas 20-41)
- spec-master/lib/state.py (upsert 141-154 vs. transition 157-177)
- spec-master/lib/controller.py (62-64, 128-152, 314, 362)
- spec-master/lib/phase_runner.py (62-71 gates shell=True sem timeout; 136 INTEGRATIONS)
- spec-master/lib/phase_contracts.py (34-58, 113-170)
- spec-master/lib/opencode_runner.py
- spec-master/lib/cli.py (113-117, 455-472, 619-647)
- spec-master/mcp/spec_master_mcp.py
- spec-master/PROTOCOL.md
- .claude/commands/spec-master.md
- spec-master/adapters/claude-code.md
- init.sh (268-300)
- .spec-master/state.json
- .spec-master/metrics/rounds.json
- .spec-master/reports/harness-revalidation.md
- .spec-master/reports/harness-100-upgrade.md
- .spec-master/reports/quality-gates.md
- specs/001-guarded-mode-controller/tasks.md (21-23, 288-290)
- specs/002-guarded-noop-phase-validation/tasks.md (73, 84, 142)
- docs/spec-master/guarded-mode-spec.md (§1, §11, §12)
- docs/market-benchmark-roadmap.md (172-204)
- .specify/workflows/speckit/workflow.yml
- Protótipo do hook imposto pelo host (scratchpad): <scratch>/harness/sm_guard.py
- [Claude Code — Hooks reference](https://code.claude.com/docs/en/hooks)
- [Claude Code — Subagents](https://code.claude.com/docs/en/sub-agents)
- [Claude Code — Skills](https://code.claude.com/docs/en/skills)
- [Claude Code — Plugin manifest reference](https://code.claude.com/docs/en/plugins-reference)
- [Claude Code — Dynamic workflows](https://code.claude.com/docs/en/workflows)
- [Claude Code — Plugin evals](https://code.claude.com/docs/en/plugin-evals)
- [Claude Code — Monitoring (OpenTelemetry)](https://code.claude.com/docs/en/monitoring-usage)
- [Claude Code — Headless / Agent SDK CLI](https://code.claude.com/docs/en/headless)
- [OpenCode — Agents](https://opencode.ai/docs/agents/)
- [OpenCode — Plugins](https://opencode.ai/docs/plugins/)
- [OpenAI Codex — Hooks](https://developers.openai.com/codex/hooks)
- [OpenAI Codex — Configuration reference](https://developers.openai.com/codex/config-reference)
- [GitHub Copilot — Hooks reference](https://docs.github.com/en/copilot/reference/hooks-reference)
- [GitHub Copilot CLI — Using hooks](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/use-hooks)
- [copilot-cli issue #3874 — preToolUse deny](https://github.com/github/copilot-cli/issues/3874)

---

## Performance do core Python

### Resumo

Papel: engenharia de performance e manutenibilidade do core Python. Todas as medições foram feitas em cópias em <scratch>/core-python. O repositório original não foi alterado.

(1) O trabalho útil do core é trivial: 0,04 a 5 ms por operação dentro do processo. Mesmo assim, cada chamada de cli.py custa de 105 a 120 ms (mediana de 38 comandos, 7 repetições). De 63% a 73% desse tempo, nos comandos leves, vai para imports e montagem do argparse dos 26 grupos que o comando nem usa. O servidor MCP não resolve isso, porque abre um subprocesso por chamada (112 ms).

(2) A latência da CLI não é o gargalo. Uma feature simulada pelo protocolo faz 47 chamadas e gasta cerca de 5,6 s de CLI. O custo real está em dois lugares:
- o número de turnos de tool-call;
- os bytes que entram no contexto: 197 KB (cerca de 50 mil tokens) por feature, dos quais 82,5% vêm de `budget file`, que devolve o conteúdo inteiro dos arquivos.

(3) Há defeitos de correção que minam o harness:
- `graph enrich-discovery`, obrigatório no Step 8, apaga arestas de decisões e faz `graph validate` falhar logo em seguida;
- escritas concorrentes perdem de 19% a 50% dos updates do state.json;
- o protocolo manda usar `knowledge get --id` e `knowledge for-context`, e os dois quebram no argparse (6 ocorrências).

(4) O tamanho não corresponde ao uso:
- são 12.931 LOC em lib, mas só cerca de 3 mil formam o núcleo de harness;
- 41% do lib entrou em um único commit, feito fora do fluxo, e nunca rodou numa execução real: métricas zeradas, nenhuma firing de hook, nenhum tier de risco salvo;
- 67% dos 631 testes cobrem periferia.

(5) No caminho principal (Claude Code) não há bloqueio real de nada: a política de comandos só aconselha e é fácil de burlar, e os contratos de fase só atuam no guarded mode com OpenCode.

Proposta: um núcleo de harness enxuto, com:
- state em event log de um único escritor;
- contratos de fase aplicados como hooks do host;
- comandos agregados (next/phase begin/complete);
- saída compacta;
- um processo persistente;
- plugins opcionais para o resto.

### Métricas

| Métrica | Valor | Método |
|---|---|---|
| Latência por chamada da CLI (subprocesso) | Mediana de 100,7 a 186,4 ms; típica de 105 a 120 ms. Exemplos: state show 115,4; state transition 119,3; fingerprint compute 110,6; risk classify 145,5; knowledge get 180,0; knowledge route 186,4; metrics record-round 100,7 ms | bench.py: 7 repetições por comando com perf_counter em volta de subprocess.run, numa cópia de rascunho, restaurando .spec-master antes de cada comando que grava estado |
| Decomposição do custo fixo | python -c pass = 13,7 ms; import de argparse+json+pathlib = 25,4 ms; import cli sem executar nada = 84,9 ms; cli --help = 107,7 ms. Dentro do processo: 9 a 18 ms por chamada, dos quais 8,75 ms são o build_parser; as funções do core levam de 0,04 a 5 ms (fingerprint de 3 docs 0,04 ms; risk classify 4,9 ms) | subprocessos com 9 repetições; bench_inproc.py chamando cli.main() 30 vezes com stdout redirecionado; microbenchmarks das funções (200 repetições) |
| Import-time (-X importtime) | Tempo próprio, mediana de 4 execuções: módulos do projeto 18,1 ms, PyYAML 8,2 ms, stdlib 44,5 ms. Maiores tempos acumulados: calibration 31,2 ms (dos quais risk_profile 26,8), dashboard 17,9, graph.store 14,3, yaml 9,2, web_bundle 6,7, ears 6,6 ms | python3 -X importtime spec-master/lib/cli.py --help, 5 execuções, analisadas com parse_importtime.py |
| Tempo gasto em imports que o comando não usa | state show: 115,4 ms contra um piso de 42,7 ms, ou seja 63% de desperdício. fingerprint compute: 110,6 contra 29,3 ms (73%). Cadeia de risk: piso de 65 ms. Transition com hooks e dashboard: piso de 80 ms | bench_lazy.py: scripts que importam só o necessário para cada comando e executam a mesma operação (9 repetições) |
| Ganho do LazyLoader sem mudar o código | 3% a 23% apenas (state show −14%, risk −23%, knowledge get −18%, fingerprint −3%). O build_parser lê constantes de hooks, risk_profile, metrics_export, web_bundle e calibration, o que força esses imports mesmo assim | lazy_boot.py (importlib.util.LazyLoader nos módulos de lib e no yaml), comparando eager e lazy com 9 repetições; a saída é idêntica |
| Chamadas e tempo de CLI por feature (simulação do protocolo) | 47 chamadas por feature, sem Team Mode e sem knowledge. Tempo de CLI: mediana de 5.588 ms por feature (de 5.137 a 5.928). Total de 950 chamadas em 20 features, mais 10 no passo final | simulate.py conduz 20 features sintéticas por upsert, risk intake/pre_implement --save, 7 fases × (budget + transition RUNNING/PASSED + record-round + append em rounds.json + delta snapshot), além de analyze-cycle, hooks emit, gates, preflight e 3 traceability add |
| Bytes que entram no contexto por feature | 197,2 KB por feature (cerca de 50 mil tokens, estimando bytes/4). `budget file` responde por 82,5%, com 23,8 KB por chamada. Sem ele, sobram 34,6 KB por feature, dos quais 18,6 KB são as 14 transitions, que devolvem o registro inteiro da feature | Soma do stdout por comando registrada no sim20.json |
| Economia com JSON compacto | De 18% a 47% menos bytes: state show 15.208→12.497; --summary 4.041→2.755; team roles 5.334→4.000; knowledge for-role 5.917→4.125; risk classify 1.349→964; evals 471→317 | Saída com indent=2 re-serializada com separators=(',',':') |
| Tamanho de state show conforme cresce o número de features | Com 10 features: 15,2 KB. Com 30 features: 51,3 KB (cerca de 12,8 mil tokens). Com --summary e 30 features: 11,1 KB. O Step 0 do PROTOCOL usa a versão completa | wc -c na cópia simulada após 20 features adicionais |
| Crescimento dos artefatos | hooks/firings.jsonl: +8,3 KB por feature, sem limite. metrics/rounds.json: +3,25 KB por feature, e o array inteiro é reescrito pelo agente a cada linha. state.json: +1,8 KB por feature. dashboard.html foi de 33 para 70 KB. graph-events.jsonl: +7 eventos (cerca de 1 KB) a cada enrich-discovery, mesmo sem mudança. delta/snapshot.json: 42 KB reescritos 7 vezes por feature. .spec-master/logs (transcripts do guarded mode): sem retenção | Tamanhos medidos após as features 1 e 20 da simulação; 5 execuções seguidas de graph enrich-discovery |
| Latência de transition conforme cresce firings.jsonl | 0,17 MB → 133,6 ms; 2 MB → 149,2 ms; 10 MB → 371,8 ms; 40 MB → 1.111 ms. O dashboard render vai de 125 para 1.216 ms. Crescimento O(n): read_firings lê o arquivo inteiro para usar só as últimas 20 linhas | firings_scale.py: log sintético replicado em cada tamanho, 5 transitions e 3 renders por tamanho |
| Servidor MCP | 76 tools. A resposta de tools/list tem 34.781 B (cerca de 8,7 mil tokens de definições). tools/call state_show: mediana de 112,5 ms, igual à CLI, porque cada chamada abre um subprocesso. Início mais initialize: 117 ms | Cliente JSON-RPC via stdio contra spec_master_mcp.py, 15 chamadas |
| Knowledge: YAML contra alternativas | knowledge get dentro do processo leva 64 ms, 94% em yaml.safe_load puro (não há libyaml neste ambiente). O parser de fallback da stdlib dá resultado idêntico em 91 de 91 arquivos e leva 2,6 ms contra 51,0 ms. Um índice JSON pré-gerado resolve a consulta em 0,25 ms | cProfile de 5 chamadas; comparação dos frontmatters com e sem _HAS_YAML; protótipo de índice com 90 entradas (30 KB), 50 repetições |
| Suíte de testes | 631 passaram, mais 37 subtests, em 4,25 s (pytest 9.1.1, rodado de dentro de spec-master/tests). O README diz 631, o que confere; diz ~2 s, e aqui deu 4,25 s. O teste mais lento leva 0,65 s (MCP e2e). O comando documentado, rodado da raiz, dá 62 erros de coleta (ModuleNotFoundError: _pathfix) com pytest 9.1.1 e também 8.0.2. Com unittest discover: 502 testes em 3,0 s e 21 erros de import, todos nos módulos graph/knowledge, que dependem de pytest | venv no rascunho com pip install pytest; --durations=30; --collect-only |
| Distribuição dos testes | Núcleo (state, fingerprint, contratos, traceability, gates, discovery, diff, delta, policy, budget): 109 (17%). Guarded mode: 60 (10%). Team: 35 (6%). Periferia: 425 (67%), sendo risk/calibration/metrics 96, dashboard/web_bundle/pr/ears/tracker/adapters 140, graph 98, knowledge 34, MCP 33 e hooks 24. evals/runtime: 2. state.py tem 9 testes; o dashboard tem 37 | Contagem de testes coletados por arquivo, mapeada para os clusters de módulos |
| LOC por cluster | lib = 12.931 LOC (mais 760 do MCP). state/gates/traceability/contratos 1.755; guarded mode 1.201; Team 1.098; risk/calibration/metrics 1.657; hooks 489; dashboard/web_bundle/pr/adapters/ears/tracker 3.022; graph 1.984; knowledge 465; evals/runtime 82; cli 1.178. O commit 1e37327 adicionou 11.760 linhas, 5.339 delas em módulos novos de lib (41% do lib) | wc -l por módulo; git show --stat 1e37327 |
| Complexidade e manutenibilidade | cli.build_parser tem 450 linhas. Complexidade ciclomática: calibration.calibrate 51 (nota F, a pior do código); web_bundle._placeholder_values 33 (E); dashboard._run_state 32 (E); cmd_knowledge 25 (D). Maintainability Index: dashboard.py 0,00 e cli.py 0,98 (as duas notas C do pacote). Há 30 funções com mais de 50 linhas | Métricas via AST (ast_metrics.py), radon cc e radon mi |
| Código morto e superfície da CLI sem uso | 350 LOC em funções e classes que o código de produção não usa, 293 delas em graph/ (context, query, resolver, temporal, traversal, provenance, InMemoryGraphStore). 20 dos 76 pares grupo/ação da CLI não são citados em nenhum doc voltado ao agente, entre eles workstreams review/integrate/aggregate, worktree *, state set-status, knowledge route/search, graph neighbors/drift/maps. O pyflakes acha 15 imports sem uso, incluindo cli.py:21 graph_ontology | vulture --min-confidence 60 sobre lib e mcp, excluindo testes; introspecção de build_parser cruzada por regex com PROTOCOL, adapters, commands e prompts |
| Concorrência em state.json | 16 execuções concorrentes de state upsert-feature, repetidas 5 vezes: persistiram 13, 12, 9, 12 e 8 de 16, ou seja de 19% a 50% de updates perdidos. Em cada rodada, de 1 a 5 processos quebraram com FileNotFoundError em state.json.tmp | Popen com 16 processos, em 5 cópias de rascunho novas |
| Política de comandos (policy preflight) | 5 de 6 variantes destrutivas passam como allowed/low: python3 -c "shutil.rmtree('.')", git push -f origin main, git push origin +main, git clean -xdf, npm run nuke. Só find . -delete foi para requires_approval | cli.py policy preflight com 6 comandos |
| Classificação: NÚCLEO (harness mínimo, cerca de 3,0 mil LOC mais cli dividido) | - state (221)<br>- phase_contracts (234)<br>- phase_result (51)<br>- controller (560), phase_runner (401) e execution_mode (113), com runners generalizados<br>- fingerprint (54)<br>- feature_model (41)<br>- quality_gates (32)<br>- discovery (193)<br>- sast_gates (165)<br>- traceability (253), só store e render<br>- tool_policy (65), reescrito como hook PreToolUse<br>- metrics (102), alimentado pelo runtime<br>- hooks (489), reduzido a barramento de eventos<br>- context_budget (47), com a saída corrigida<br>- cli (1.178), dividido por grupo | Critério: citado em instrução do PROTOCOL e sem substituto no host (máquina de estados, gates, contratos de fase, resume); evidência de uso nos 3 ciclos reais de dogfood (fases PASSED, fingerprint, traceability) |
| Classificação: PERIFÉRICO-ÚTIL (plugin opcional) | - context_delta (262)<br>- constitution_diff (68)<br>- git_strategy (69)<br>- worktree (129)<br>- team_model (591, dos quais 66% são dados; mover para arquivos de dados)<br>- team_workstreams (92)<br>- decision_memory (286)<br>- knowledge/* (465), com índice JSON<br>- risk_profile (700), simplificado com fast lane<br>- pr_step (534)<br>- web_bundle (637)<br>- dashboard (994), renderizado sob demanda<br>- metrics_export (442)<br>- servidor MCP (760), persistente | Critério: tem valor para parte dos usuários, mas não é necessário para rodar a fase. Nenhum desses deixou rastro no dogfood commitado: não existem dashboard.html, bundles, delta, adr, workstreams.json nem pr-*.md em .spec-master |
| Classificação: CANDIDATO A CORTE OU CONGELAMENTO | - opencode_runner (127): substituído por phase_runner; ninguém importa; só é citado em specs/001<br>- evals (50) e runtime_contract (32): 5 checagens sintéticas e um dict constante<br>- calibration (413): complexidade 51 e nunca recebeu dado real (rounds com 0 tokens e sem feature_id/tier)<br>- graph/context, query, resolver, temporal, drift, maps e enrichment (cerca de 1.100 dos 1.984 LOC de graph/): só testes os usam, e a enrichment tem o bug de perda de arestas<br>- ears (286): lint consultivo, nunca usado<br>- tracker_orchestration (131): absorver na discovery via manifest do Spec Kit<br>- adapters_gen (440): ferramenta de distribuição, mover para tools/ de build | Critério: fan-in zero em produção, uso só em testes (vulture), saída constante ou sintética, ou dependência de dados que nunca existiram; custo de manutenção medido por LOC, complexidade e testes dedicados |
| Custo agregado por feature em cada alternativa (estimativa) | - Atual: 47 chamadas, 5,6 s de CLI, 197 KB de saída.<br>- (a) Registro lazy por grupo: cerca de 47 × 40 ms ≈ 1,9 s (−66%).<br>- (b) Processo persistente in-process: cerca de 47 × 5 a 10 ms ≈ 0,2 a 0,5 s (−91% a −96%).<br>- (c) Comando agregado: cerca de 17 chamadas × 120 ms ≈ 2,0 s (−64%) e 30 turnos de LLM a menos.<br>- (a)+(c) com dieta de saída: cerca de 0,7 s e cerca de 12 KB de saída (−94%).<br>- HIPÓTESE, não medida aqui: com 3 a 8 s por turno de LLM, os 47 turnos somam de 2,4 a 6,3 minutos por feature, contra 0,9 a 2,3 minutos com 17 turnos. A latência da CLI em si fica abaixo de 4% disso | Combinação dos pisos medidos (bench_lazy, bench_inproc) com a contagem de chamadas da simulação; o custo por turno de LLM é hipótese |

### Scorecard

| Dimensão | Nota | Máximo | Justificativa |
|---|---:|---:|---|
| Latência por chamada (CLI) | 5 | 10 | 105–120 ms por chamada é aceitável em valor absoluto, mas cerca de 90% é custo fixo, o MCP não amortiza e o gasto se multiplica por 47 chamadas por feature |
| Economia de tokens na saída | 2 | 10 | budget file devolve o conteúdo (82,5% dos bytes), o JSON sai indentado, state show vem completo e o MCP tem 76 tools (8,7 mil tokens) |
| Correção e robustez da persistência | 3 | 10 | O grafo perde arestas no Step 8; há 19–50% de updates perdidos sob concorrência; o temporário tem nome fixo; o tratamento de erro é parcial |
| Contrato protocolo↔CLI | 4 | 10 | 2 comandos divergentes em 6 lugares; 20 de 76 subcomandos sem instrução; nenhum teste de conformidade |
| Modularidade e acoplamento | 4 | 10 | cli importa 38 módulos; build_parser tem 450 linhas; MI de 0 e 0,98; registries de papéis, fases e tiers duplicados; 13 sys.path hacks |
| Testes | 6 | 10 | 631 testes rápidos e determinísticos, mas o comando documentado quebra, 67% cobrem periferia e faltam testes de conformidade, concorrência e fluxo fim a fim |
| Proporção núcleo/periferia | 3 | 10 | Cerca de 3 mil LOC de núcleo contra cerca de 10 mil de periferia; 41% do lib veio de um commit sem uso em dogfood; 350 LOC só-teste |
| Enforcement de harness | 2 | 10 | Política só aconselha e é burlável; contratos de fase só no guarded mode com OpenCode; sem hooks do host; gates e discovery cegos no próprio repo |

### Achados

#### CP-01 — Cerca de 90% da latência de cada chamada é custo fixo, e o MCP não amortiza (impacto: medio)

Todo comando paga, sempre:
- startup do Python: 14 ms;
- import de 38 módulos internos no topo do cli.py, mais PyYAML: cerca de 60 ms;
- build_parser dos 26 grupos: 9 ms.

O trabalho real fica entre 0,04 e 5 ms. Nos comandos leves, de 63% a 73% do tempo é import de módulos que o comando não usa. O servidor MCP, que seria o candidato natural a processo persistente, roda `python3 cli.py` em subprocesso a cada tool call e por isso tem a mesma latência de 112 ms. Um LazyLoader encaixado sem mudar código rende só 3% a 23%, porque o build_parser lê constantes de hooks, risk_profile, web_bundle, calibration e outros. Um cache de fingerprint não se justifica: o hash de 36 arquivos leva 0,48 ms.

**Evidência:** cli.py:21-59 (imports no topo); cli.py:715-1164 (build_parser, 450 linhas); mcp/spec_master_mcp.py:615 (subprocess.run por chamada). Medições: cli --help 107,7 ms contra python -c pass 13,7 ms; import cli sem executar nada 84,9 ms; in-process 9 a 18 ms com parser de 8,75 ms; MCP tools/call 112,5 ms

#### CP-02 — A saída da CLI infla o contexto do agente: 197 KB por feature, 82,5% vindos de `budget file` (impacto: alto)

O comando que deveria controlar o orçamento de contexto devolve o conteúdo integral de todo arquivo selecionado e também dos omitidos. São 23,8 KB por chamada, e o PROTOCOL o chama para cada prompt montado.

Outras fontes de volume:
- todo JSON sai com indent=2, o que pesa de 18% a 47% a mais;
- `state transition` devolve o registro inteiro da feature (1,3 KB, 14 vezes por feature);
- o Step 0 usa `state show` completo, que chega a 51 KB com 30 features;
- o MCP publica 76 tools, cerca de 8,7 mil tokens de definições.

Por feature, a CLI injeta cerca de 50 mil tokens. Sem o budget file, seriam 34,6 KB.

**Evidência:** context_budget.py:32 (entry = dict(item) mantém 'content'), :43-44 (selected e omitted com conteúdo); PROTOCOL.md:611-614; simulate.py: budget file = 3.329.620 de 4.037.830 bytes de stdout em 950 chamadas

#### CP-03 — São 47 chamadas por feature sem comando agregado, e o protocolo exige edições manuais de JSON (impacto: alto)

Cada fase exige budget, transition RUNNING, transition PASSED, record-round e delta snapshot, fora os extras de analyze, validate, risk e traceability. Não existe um comando do tipo 'o que faço agora' (phase card).

Há duas lacunas que forçam o agente a editar arquivos à mão:
- nenhum código grava `state['fingerprint']`, que o Step 3 manda guardar, e `fingerprint compare` só aceita arquivos, então o resume precisa de arquivos temporários (pelo menos 4 chamadas mais uma edição de state.json);
- `metrics record-round` só imprime a linha, e o agente precisa anexá-la a rounds.json lendo e reescrevendo o array inteiro.

O parâmetro `--path` quer dizer arquivo de estado em state e traceability e raiz do projeto em risk, pr, bundle e ears, o que induz a erro de chamada.

**Evidência:** PROTOCOL.md:134-137 e :234-235 (guardar fingerprint), :343-344 ('Append each row'); state.py:72 é o único ponto que escreve fingerprint (valor {}); metrics.py:19-76 (record_round só retorna); simulação com 47 chamadas por feature

#### CP-04 — `graph enrich-discovery`, obrigatório no Step 8, apaga arestas de decisão e reprova o `graph validate` seguinte (impacto: alto)

Na primeira chamada, `FileGraphStore.save_node` cria um `Graph()` vazio em vez de carregar o grafo existente, e reescreve o graph-manifest.json só com os nós enriquecidos. As arestas tipadas, que existem apenas no manifest (DECIDED_BY e INFLUENCES gravadas por `team resolve`), se perdem.

Reproduzido numa cópia com o nome canônico do diretório: validate passa (valid=true), depois de `team resolve` continua true, depois de `graph enrich-discovery` vira false, com os nós órfãos agent.architect e decision.*. Mesmo assim, `graph health` reporta 96/A.

Outros dois problemas no mesmo caminho:
- o id do projeto vem do nome do diretório de checkout, então um clone em outro caminho cria um project.* órfão;
- cada execução anexa 7 eventos ao graph-events.jsonl mesmo sem mudança.

Como o PROTOCOL só imprime o relatório se o validate passar, o próprio core empurra o run para PARTIAL ou BLOCKED.

**Evidência:** graph/store.py:190-191 (`if self._graph is None: self._graph = Graph()`); cli.py:574-583; graph/enrichment.py:39-40 (`project_name = root.name`); PROTOCOL.md:625-633; manifest foi de 6 nós e 4 arestas para 4 nós e 3 arestas

#### CP-05 — Escritas concorrentes perdem de 19% a 50% dos updates e derrubam processos (impacto: alto)

`state.save` faz ler-modificar-escrever sem lock e usa um nome de temporário fixo (`state.json.tmp`). Dois processos disputam o mesmo temporário: um deles quebra no os.replace e o outro sobrescreve o estado com uma versão velha. Traceability, rounds e a gravação do grafo seguem o mesmo padrão sem lock.

Isso importa porque o produto vende Team Mode paralelo, worktrees e um servidor MCP que pode receber chamadas simultâneas. Além disso, `cli.main` só captura StateError e ValueError; o resto sai como traceback em texto, fora do contrato JSON.

**Evidência:** state.py:83-89 (tmp = path + '.tmp'); cli.py:1172. Teste com 5×16 upserts concorrentes: persistiram 13, 12, 9, 12 e 8 de 16, com 1 a 5 FileNotFoundError por rodada

#### CP-06 — PROTOCOL e CLI divergem, e 20 dos 76 subcomandos não têm instrução de uso (impacto: medio)

Os dois comandos de entrada do Team Mode prescritos pelo protocolo falham:
- `knowledge get --id playbook.<role>` dá 'unrecognized arguments: --id', porque o id é posicional;
- `knowledge for-context` dá 'invalid choice'; o comando real é `knowledge route`.

A divergência aparece em 6 lugares. Na outra direção, 20 pares grupo/ação não são citados por nenhum doc voltado ao agente. Isso inclui justamente o registro de veredito de peer review (`workstreams review/integrate`), os comandos das features entregues pelo próprio fluxo (worktree *, tracker) e `state set-status`. Nenhum teste confronta os comandos do PROTOCOL com o parser.

**Evidência:** PROTOCOL.md:288 e :293; knowledge/playbooks/spec-master.md:29 e :34; README.md:390; docs/spec-master/README.md:225; execução mostrou 'error: unrecognized arguments: --id' e 'invalid choice: for-context'; introspecção de build_parser (76 pares, 56 referenciados)

#### CP-07 — O knowledge relê e reparseia 91 arquivos com PyYAML puro a cada chamada (impacto: medio)

`KnowledgeManifest._ensure_loaded` faz rglob e safe_load em todos os frontmatters a cada invocação. Isso consome 94% dos 64 ms in-process de `knowledge get` e deixa as chamadas de knowledge em 165 a 186 ms, as mais lentas da CLI. A docstring promete 'sem carregar todo o conteúdo'.

O parser de fallback da stdlib produz frontmatter idêntico em 91 de 91 arquivos e é 20 vezes mais rápido (2,6 ms contra 51 ms). Um índice JSON pré-gerado resolve a consulta em 0,25 ms. A dependência opcional de YAML também mantém duas fontes da ontologia (ontology.yaml e os conjuntos embutidos, hoje sincronizados) e faz 21 módulos de teste (graph e knowledge) exigirem pytest.

**Evidência:** knowledge/manifest.py:48-61 (docstring em :1-9); graph/parser.py:17-20; cProfile: 0,937 s de 0,999 s em yaml; comparação feita com _HAS_YAML=False

#### CP-08 — Artefatos crescem sem limite e há render O(n) no caminho quente (impacto: medio)

O hook padrão `dashboard-refresh` roda a cada phase.started, phase.transition e workflow.status. Cada transition lê state, traceability, decisões, o grafo e o firings.jsonl inteiro, este último só para exibir 20 linhas.

O que cresce sem limite:
- firings.jsonl, em 8,3 KB por feature;
- rounds.json, um array que o agente reescreve a cada linha;
- graph-events.jsonl, que cresce até sem mudança;
- os transcripts do guarded mode em .spec-master/logs, sem política de retenção.

Na escala atual o impacto é pequeno: 134 ms com 0,17 MB e 149 ms com 2 MB. Mas chega a 1,1 s com 40 MB, então é um problema de desenho: render a cada escrita e leitura completa de logs.

**Evidência:** hooks.py:162-167 (dashboard-refresh), :466-483 (read_firings lê tudo e fatia [-limit:]); dashboard.py:85 (MAX_FIRINGS=20); phase_runner.py:102-127 (transcripts); firings_scale.py: 133,6 → 371,8 → 1.111 ms

#### CP-09 — Acoplamento e duplicação: cli monolítico e registries repetidos (impacto: medio)

- `cli.py` importa 38 módulos internos (um deles sem uso) e concentra 26 grupos num build_parser de 450 linhas (Maintainability Index 0,98).
- `dashboard.py` tem MI 0,00; `calibration.calibrate` tem complexidade 51.
- Duplicações: 9 funções `_now/now_iso`, 8 escritas atômicas próprias com os.replace, 4 tuplas de tiers, 5 listas de fases, 2 parsers de frontmatter.
- Há dois registries de papéis com o mesmo nome `AGENT_ROLES` e tipos diferentes (team_model usa po, infra e ui-ux-brand; knowledge usa product-owner, infrastructure e ux). Eles são ligados por dois mapas de alias inversos, e o PROTOCOL manda o agente resolver os ids à mão.
- 66% de team_model.py é dado embutido em Python.
- 13 `sys.path.insert` expõem módulos com nomes genéricos no topo (state, hooks, metrics, evals, graph).

**Evidência:** cli.py:21-59; knowledge/model.py:25 e team_model.py:14 (AGENT_ROLES); knowledge/profiles.py:23-27 e decision_memory.py:46-51 (aliases); PROTOCOL.md:289-292; radon cc/mi; grep de os.replace, _now e TIERS

#### CP-10 — Peso morto e 'harness theater' inflam as auditorias internas (impacto: medio)

O que conta como harness nos relatórios, mas não verifica o projeto:
- `evals run` executa 5 checagens sobre fixtures sintéticos fixos e sempre passa se o código compila;
- `runtime contract` devolve um dict constante;
- os dois são obrigatórios no Step 8 e pesaram para '100% readiness'.

O que está parado:
- `opencode_runner.py` foi substituído por phase_runner, ninguém o importa e só specs/001 o cita;
- graph.context (a 'seleção de contexto guiada pelo grafo' que a auditoria 73/100 credita) e graph.query só são usados em testes, e ao todo são 350 LOC só-teste;
- 41% do lib (5.339 LOC) entrou num único commit fora do fluxo. No dogfood commitado não há rastro de hooks, risk, dashboard, delta, bundles, logs do guarded mode nem ADRs, e rounds.json tem 9 linhas com 0 tokens e horários redondos (00:00→00:05), o que zera o sinal de calibration.py.

**Evidência:** evals.py:17-50; runtime_contract.py:20-32; PROTOCOL.md:629-630; .spec-master/reports/harness-100-upgrade.md ('Readiness: 100%'); harness-revalidation.md ('graph-backed context selection'); vulture; git show --stat 1e37327; .spec-master/metrics/rounds.json

#### CP-11 — Não há enforcement no caminho principal: política burlável, contratos de fase só no OpenCode, gates e discovery cegos no próprio repo (impacto: alto)

- `tool_policy` compara strings e depende de o agente chamá-lo. Liberou 5 de 6 variantes destrutivas (python3 -c shutil.rmtree, git push -f, git push +main, git clean -xdf).
- `phase_contracts`, a parte de maior valor real para um harness (allowlist de escrita por fase, PROTECTED_PATHS, artefatos obrigatórios, marcadores de tool falsa), só atua no guarded mode, e o único runner implementado é o do OpenCode.
- No Claude Code não há .claude/settings.json nem hooks do host.
- `gates detect` retorna [] no próprio repositório: um projeto Python só com stdlib, sem pyproject, não é reconhecido, e os 631 testes rodaram à mão.
- `discovery` retorna `speckit_commands: []` porque procura apenas em .claude/commands/speckit.*.md. Ignora o install em modo skills e o manifesto autoritativo .specify/integration.json.

**Evidência:** tool_policy.py:21-24; phase_contracts.py:35-67; phase_runner.py:136 (`INTEGRATIONS = {'opencode': ...}`); discovery.py:145-161; .spec-master/reports/quality-gates.md ('No quality gates detected'); saída real de discovery scan

#### CP-12 — Suíte rápida, mas o comando documentado quebra e a cobertura está enviesada para a periferia (impacto: baixo)

A contagem de 631 confere (mais 37 subtests, 4,25 s). Porém `python3 -m pytest spec-master/tests`, como está no README, falha com 62 erros de coleta: tests/__init__.py e o import de `_pathfix` só funcionam com cwd=tests. Sem pytest, 21 módulos (todos de graph e knowledge) nem carregam.

Apenas 17% dos testes cobrem o núcleo (state.py, o coração da máquina de estados, tem 9 testes; o dashboard tem 37). Não há teste de conformidade entre protocolo e CLI, nem de concorrência, nem da sequência obrigatória do Step 8, que teria pego os bugs CP-04, CP-05 e CP-06.

**Evidência:** README.md:147 e :511; pytest 9.1.1 e 8.0.2 na raiz: '62 errors during collection'; de dentro de tests/: '631 passed, 37 subtests passed in 4.25s'; unittest discover: 502 testes e 21 erros

### Recomendações

#### R1 — Corrigir os defeitos de integridade e blindar o contrato com testes (P0 · esforço S)

Correções:
- `save_node` e `save_edge` devem carregar o grafo antes de escrever (`self.load()`);
- o id do projeto no grafo deve ser estável, lido de config ou do state, e não do nome do diretório;
- não gravar eventos quando nada mudou;
- escritas de state, traceability e rounds com fcntl.flock mais temporário único (mkstemp no mesmo diretório);
- `main` deve devolver erro JSON para qualquer exceção.

Testes novos:
- conformidade que extrai todo comando citado em PROTOCOL.md, playbooks e README e faz parse com build_parser;
- concorrência;
- a sequência do Step 8 (resolve → enrich → validate).

Também: corrigir `knowledge get --id` e `for-context` nos 6 lugares e adicionar conftest.py ou pytest.ini (pythonpath) para o comando do README funcionar.

**Ganho esperado:** Acaba com a perda de arestas e com o `graph validate` falso-negativo no fim de todo run que registrou decisões. Leva a 0% os updates perdidos, hoje de 19% a 50% sob concorrência. Elimina chamadas desperdiçadas em erro de argparse no Team Mode. Os testes passam a rodar na raiz.

**Riscos:** O lock de arquivo tem semântica diferente no Windows (usar msvcrt, ou um lock simples por arquivo com retry). É preciso decidir o que fazer com os project.* órfãos já gravados.

#### R2 — Dieta de saída: JSON compacto e respostas mínimas por padrão (P0 · esforço S)

- `budget file` passa a devolver só ids e tokens estimados de selected/omitted, com `--with-content` opcional.
- JSON compacto por padrão, com `--pretty` opcional.
- `state transition` responde com um ack mínimo: fase, status, previous e as directives.
- `state show` passa a devolver o resumo por padrão, com `--full` opcional.
- `risk classify` só traz contexto e histórico com `--verbose`.
- `hooks emit` omite o evento ecoado.

**Ganho esperado:** A saída cai de 197 KB para cerca de 12 KB por feature (−94%), algo como 46 mil tokens a menos por feature. Com 30 features, o Step 0 cai de 51 KB para 11 KB, ou menos.

**Riscos:** Quebra consumidores que liam campos verbosos (testes, dashboard, MCP structuredContent). Mitigar com flags e com a versão do contrato no próprio JSON.

#### R3 — Comandos agregados de harness: `next` (phase card) e `phase begin`/`phase complete` (P0 · esforço M)

Novos comandos:
- `sm next --feature X`: devolve a próxima ação num único payload: fase, prompt renderizado ou caminho, artefatos obrigatórios, escritas permitidas, gates, ids do orçamento de contexto, fases stale e obrigações do tier.
- `sm phase begin`: transition RUNNING, com risk classify quando for a hora, budget e um timestamp medido.
- `sm phase complete --status`: transition, validate_artifacts, hooks, record-round anexado pelo próprio core com duração medida, e delta snapshot.
- `sm resume`: compute, compare e grava o fingerprint no state; fecha a lacuna do Step 3.
- `sm trace add --batch`.

Os comandos finos continuam existindo como primitivas.

**Ganho esperado:** De 47 para cerca de 17 chamadas por feature (−64%), ou seja 30 turnos de LLM a menos por feature (HIPÓTESE: 1,5 a 4 minutos a menos por feature). Acaba com a edição manual de state.json e rounds.json. Métricas de duração passam a ser reais.

**Riscos:** Duplica a lógica de orquestração que hoje está no controller.py. Os dois devem compartilhar a mesma função de 'próximo passo', para não divergirem. O PROTOCOL precisa ser reescrito em torno desses comandos.

#### R4 — Startup: registro de subcomandos por grupo com imports lazy e sem PyYAML no caminho quente (P1 · esforço M)

- Dividir cli.py em commands/<grupo>.py, com `register(subparsers)` e import dentro do handler.
- Montar só o parser do grupo invocado, lendo argv[1].
- Mover para um `constants.py` leve as constantes usadas na montagem dos parsers (EVENT_TYPES, TIERS, STAGES, PHASES, FORMATS, DEFAULT_*).
- Gerar em build (e checar em teste) um `knowledge/index.json` com o frontmatter dos módulos.
- Usar o parser de fallback como padrão, que é idêntico no corpus atual.
- Tail-read de firings.jsonl (seek a partir do fim).

**Ganho esperado:** Chamada típica de 105–120 ms para 30–45 ms (−60% a −70%, pelo piso medido de 29 a 43 ms). `knowledge get` e `knowledge route` de 180 para cerca de 35 ms. Tempo de CLI por feature de 5,6 para cerca de 1,9 s.

**Riscos:** Pouco ganho de parede isoladamente, porque o custo dominante são os turnos de LLM. O índice JSON pode ficar desatualizado: gerar e validar no CI ou no init.sh.

#### R5 — Servidor persistente in-process e escritor único, com superfície MCP enxuta (P1 · esforço M)

O servidor MCP passa a importar o core uma vez, montar o parser uma vez e despachar in-process, com fila única de escrita (o que resolve CP-05 por construção). O subprocesso fica só como fallback, com `--isolate`.

A superfície de tools cai de 76 para 8 a 12 tools grossas: next, phase_begin, phase_complete, resume, record, trace, query, gates, knowledge, report. As primitivas ficam acessíveis por uma tool genérica `cli`. A CLI de shell continua para hosts sem MCP.

**Ganho esperado:** De 112 para 2 a 10 ms por chamada (−91% a −98%). Definições de tools de 34,8 KB (cerca de 8,7 mil tokens por sessão) para cerca de 5 KB (−85%). Serialização natural das escritas.

**Riscos:** Estado em memória pode divergir do disco se outro processo escrever (CLI e MCP ao mesmo tempo). Exige lock ou lease e recarga por mtime. Um bug no processo persistente derruba a sessão (usar watchdog e reinício).

#### R6 — State como event log append-only com snapshot materializado e limites de crescimento (P1 · esforço M)

Criar `.spec-master/events.jsonl`, com um único escritor, como fonte da verdade para transitions, firings, métricas, overrides e decisões. O state.json vira uma visão compactada (snapshot com seq), regenerada a cada N eventos.

- Rotação por tamanho (5 MB) e tail-read.
- rounds.json deixa de ser array e passa a ser eventos.
- O dashboard e os relatórios viram leitores sob demanda (`report`) e saem do caminho quente das transitions.
- Retenção de transcripts (manter as últimas N tentativas por fase, compactando as demais).
- A migração da versão 1 de state.json vira um evento inicial.

**Ganho esperado:** Latência de escrita O(1), independente do histórico (hoje 134 ms com 0,17 MB e 1.111 ms com 40 MB). Fim do render por transition (−12 ms por transition). Auditoria e replay determinísticos, que são a base de evals reais. Crescimento com teto.

**Riscos:** Migração e compatibilidade com leitores atuais (dashboard, pr_step, web_bundle, controller). Divergência entre log e snapshot em caso de crash (aplicar os eventos pendentes na leitura).

#### R7 — Levar o enforcement para o host: de extensão para harness (P1 · esforço L)

Gerar, via init.sh link, a config de hooks do host (Claude Code .claude/settings.json; equivalentes onde houver):
- PreToolUse(Write|Edit): permite escrita só se o caminho está em PHASE_ALLOWED_WRITES da fase RUNNING e fora de PROTECTED_PATHS;
- PreToolUse(Bash): política nega-por-padrão para operações destrutivas, com parse real de argv (substitui `policy preflight`);
- Stop e SubagentStop: bloqueiam o encerramento da fase até validate_artifacts e os gates passarem;
- SessionStart: injeta o phase card.

Generalizar os runners do guarded mode (hoje INTEGRATIONS só tem opencode) para `claude -p`, `codex exec` e `gemini`, capturando tokens do runtime (stream-json e eventos) para metrics.

**Ganho esperado:** Os contratos de fase, que hoje só valem no OpenCode, passam a valer no caminho principal. As 5 de 6 variantes destrutivas que hoje passam ficam bloqueadas. As métricas passam a ter tokens reais, o que habilita a calibration. É a mudança que caracteriza o Spec Master como harness, e não como extensão.

**Riscos:** O formato de hooks muda por host e por versão (manter adaptadores finos e testes de contrato). Falsos positivos de bloqueio frustram o usuário (modo auditoria antes do modo bloqueio).

#### R8 — Separar núcleo de plugins, congelar ou cortar o peso morto e unificar registries (P1 · esforço L)

- Empacotar como `spec_master`, com pyproject, console_script e uvx/pipx. Isso remove os 13 sys.path.insert e os nomes genéricos no topo.
- Núcleo de cerca de 3 mil LOC: state, contracts, controller, runners, fingerprint, gates, discovery, traceability, metrics, hooks reduzido e budget.
- Plugins via entry points, carregados sob demanda: dashboard, web_bundle, pr_step, metrics_export, ears, tracker, adapters_gen, Team Mode, knowledge e graph.
- Cortar: opencode_runner.py; evals.py e runtime_contract.py, trocados por evals reais de replay do event log e golden runs; graph.context, query, resolver e temporal.
- Congelar calibration até existirem métricas reais.
- Um registry único de papéis, gerado dos playbooks com frontmatter (e team_model vira dados), e um módulo `common` para fases, tiers, now e escrita atômica.

**Ganho esperado:** O que precisa rodar e ser mantido cai de 12,9 mil para cerca de 3 a 4 mil LOC. Os testes do núcleo sobem de 17% para a maioria da suíte. Com a distribuição via uvx, some a cópia espelhada do init.sh. Acaba a resolução manual de ids de papel no PROTOCOL.

**Riscos:** Quem já depende dos plugins sente a mudança (fazer deprecação em uma versão). Há o risco de cortar algo com uso externo não visível no repo: medir uso por telemetria opt-in antes de apagar e congelar primeiro.

#### R9 — Discovery pelo manifesto do Spec Kit e gates declarativos (P2 · esforço S)

A discovery passa a ler `.specify/integration.json` e `.specify/integrations/*.manifest.json` para descobrir os entrypoints de fase instalados, em modo commands ou skills. Isso absorve o tracker_orchestration.

Adicionar gates declarativos em `.spec-master/gates.json`, ou numa seção da constitution, com precedência sobre a heurística. Assim, projetos só com stdlib (o próprio Spec Master) ganham `python3 -m pytest` como gate bloqueante.

**Ganho esperado:** `speckit_commands` deixa de vir vazio em instalações no modo skills (o caso deste repo). O validate do dogfood deixa de rodar sem gate. Uma heurística a menos para manter.

**Riscos:** O formato do manifesto do Spec Kit pode mudar entre versões (fixar schema_version e manter a heurística atual como fallback).

#### R10 — Fast lane real por tier para cortar o excesso de cerimônia (P2 · esforço M)

Hoje só clarify pode ser pulado: SKIPPABLE_PHASES=('clarify',) e todos os perfis marcam o resto como required. Uma feature XS passa por 6 das 7 fases com analyze obrigatório.

Proposta:
- XS/S: um lane 'spec-lite → implement → validate', com plan e tasks gerados numa única passada e analyze leve e automático, sem ciclo de repair;
- M e acima: fluxo completo.

Os tiers, em versão simplificada, ficam no núcleo como o mecanismo anti-overengineering. Os limites só devem ser calibrados quando R7 fornecer tokens reais.

**Ganho esperado:** HIPÓTESE: de 3 a 4 fases a menos, com seus turnos, para mudanças pequenas. É a maior alavanca de performance do fluxo, bem acima de qualquer otimização de CLI.

**Riscos:** Features mal classificadas como XS saem com menos rigor. Mitigar mantendo os pisos de sensibilidade (auth, payment, secrets vão no mínimo para L) e a reclassificação antes do implement, que já existe.

### Perguntas abertas

- O guarded mode (controller.py) vai virar o motor padrão do harness, generalizado para claude -p, codex exec e outros? Ou o modo 'native', em que o agente lê o PROTOCOL, continua sendo o caminho principal? Isso define onde entram os comandos agregados e o enforcement.
- O Team Mode paralelo (worktrees e workstreams com vários agentes escrevendo ao mesmo tempo) é requisito real de curto prazo? Se for, o escritor único ou lock (R1, R5, R6) é bloqueante.
- Quais hosts precisam de suporte de primeira classe para os hooks de enforcement (Claude Code, Codex, Copilot, OpenCode)? Os mais de 30 adapters gerados continuam como fallback só consultivo?
- Qual será a fonte de tokens e duração para metrics: OTel do Claude Code, stream-json, eventos do OpenCode? Sem isso, calibration.py (413 LOC, complexidade 51) deve continuar congelado?
- O knowledge graph tem caso de uso real além da memória de decisões? Com 4 a 7 nós no dogfood, compensa manter cerca de 2 mil LOC em graph/, ou basta um arquivo de decisões e ADRs?
- Existem consumidores externos (outros repositórios ou usuários do init.sh) dos subcomandos e campos JSON que as recomendações R2 e R8 mudariam? É preciso compatibilidade retroativa do state.json versão 1?

### Referências

- spec-master/lib/cli.py
- spec-master/lib/state.py
- spec-master/lib/context_budget.py
- spec-master/lib/hooks.py
- spec-master/lib/dashboard.py
- spec-master/lib/graph/store.py
- spec-master/lib/graph/enrichment.py
- spec-master/lib/graph/parser.py
- spec-master/lib/knowledge/manifest.py
- spec-master/lib/knowledge/profiles.py
- spec-master/lib/team_model.py
- spec-master/lib/decision_memory.py
- spec-master/lib/risk_profile.py
- spec-master/lib/calibration.py
- spec-master/lib/metrics.py
- spec-master/lib/fingerprint.py
- spec-master/lib/tool_policy.py
- spec-master/lib/evals.py
- spec-master/lib/runtime_contract.py
- spec-master/lib/discovery.py
- spec-master/lib/phase_contracts.py
- spec-master/lib/phase_runner.py
- spec-master/lib/controller.py
- spec-master/lib/opencode_runner.py
- spec-master/mcp/spec_master_mcp.py
- spec-master/PROTOCOL.md
- spec-master/knowledge/playbooks/spec-master.md
- README.md
- .spec-master/state.json
- .spec-master/metrics/rounds.json
- .spec-master/reports/quality-gates.md
- .spec-master/reports/harness-100-upgrade.md
- .spec-master/reports/harness-revalidation.md
- docs/market-benchmark-roadmap.md
- <scratch>/core-python/bench.py
- <scratch>/core-python/bench1.json
- <scratch>/core-python/bench_lazy.py
- <scratch>/core-python/bench_inproc.py
- <scratch>/core-python/lazy_boot.py
- <scratch>/core-python/simulate.py
- <scratch>/core-python/sim20.json
- <scratch>/core-python/firings_scale.py
- <scratch>/core-python/ast_metrics.py
- <scratch>/core-python/importtime_2.txt
- <scratch>/core-python/pytest_run2.txt

---

## Acoplamento com o Spec Kit

### Resumo

O acoplamento do Spec Master com o Spec Kit está quase todo no protocolo e no ritual de fases. No código ele é pequeno: só ~100 das 13.691 linhas do core (0,7%, em 16 de 61 módulos) citam artefatos do Spec Kit. Já o custo em tokens é alto. Por feature, o agente lê ~24,7k tokens de skills e templates do Spec Kit (14,3x os prompts próprios) e gera em média 58KB (~14,5k tokens) de artefatos, de 8,7x a 12,5x o código entregue nas features 003–005.

Esse acoplamento já está quebrado:
- o discovery não enxerga nenhuma das 10 skills instaladas (o layout de skills vale para o Claude desde o Spec Kit v0.4.5);
- o adapter do Claude manda ler `.claude/commands/speckit.<phase>.md`, que não existe;
- os prompts usam `/speckit.<phase> --files`, mas o comando instalado é `/speckit-<phase>` e a flag `--files` não existe;
- a tabela do adapters_gen está defasada: faltam 3 agentes novos e o qodercli migrou para skills;
- os testes congelam o layout antigo.

O upstream lançou 14 versões (incluindo a major 1.0.0) em 42 dias desde o pin 0.16.4, e o bootstrap instala o HEAD sem pin. Há 4 conflitos de fonte da verdade demonstrados (numeração, estado de fase, constitution e branch). O fluxo leve é impossível por construção, e o próprio dono tirou 13 dos 16 itens do roadmap do ciclo.

A estratégia proposta: o Spec Master vira um harness com motor de fases próprio e "packs" declarativos (patch, feature-lite, bugfix, spike, full-sdd). O Spec Kit passa a ser o pack speckit-compat, com import e export de `specs/NNN`. O harness vira fonte única usando alavancas que o Spec Kit já expõe: `SPECIFY_FEATURE_DIRECTORY`, `--number` e `GIT_BRANCH_NAME`. Vale reaproveitar os templates de metodologia (MIT, sem nenhuma mudança entre 0.16.4 e 1.0.12). Não vale reimplementar a camada volátil: instalador de mais de 40 agentes, engine genérica de workflow, catálogo de extensões e clientes de tracker.

### Métricas

| Métrica | Valor | Método |
|---|---|---|
| Linhas do core acopladas ao Spec Kit | 100 de 13.691 (0,7%), em 16 de 61 módulos; 29 delas em phase_contracts.py | Busca por regex (.specify, speckit, spec_kit, specs/*, feature.json, spec/plan/tasks.md) em spec-master/lib/**, graph/, knowledge/ e mcp/ |
| Instruções do Spec Kit lidas por feature (6 fases) | 98.758 bytes ≈ 24,7k tokens (skills 81.349 + templates 17.409), contra 6.909 bytes ≈ 1,7k tokens dos prompts próprios: 14,3x | wc -c em .claude/skills/speckit-{specify,clarify,plan,tasks,analyze,implement}/SKILL.md e .specify/templates/{spec,plan,tasks}-template.md; tokens = bytes/4 |
| Boilerplate de extension hooks nas skills | ~39KB de 134KB (~29%); ~3,9KB por skill de fase. .specify/extensions.yml não existe neste repo | Heurística que soma os blocos que citam extensions.yml ou hooks.before_/after_, conferida manualmente em speckit-plan (linhas 22–56) |
| Artefatos por feature (specs/001–005) | Média de 58.146 bytes (~14,5k tokens). Razão artefatos/código: 005 = 12,2x (54.841 vs 4.502 B), 004 = 12,5x, 003 = 8,7x | find + wc recursivo por diretório, comparado com o módulo implementado em lib/ |
| Tasks por feature vs tamanho do código | 21 a 29 tasks para módulos de 92 a 131 linhas (~5 linhas de código por task) | grep '^- [ ] T###' em tasks.md; wc -l nos módulos |
| Custo modelado da camada Spec Kit (feature 005) | ~72k tokens com 1 passe de analyze, mais ~12,6k por ciclo de repair, para produzir ~2,5k tokens de código e testes (HIPÓTESE de modelo) | bytes/4 das skills e templates + releituras que cada skill manda fazer (spec, plan, research, data-model, contracts, quickstart, constitution) + artefatos escritos. As métricas do projeto não medem isso: tokens = 0 em rounds.json |
| Velocidade do upstream desde o pin | 14 releases de v0.16.4 (14/08/2026) a v1.0.12 (25/09/2026), com major 1.0.0; 281 commits; 138 tags em 2026 | git ls-remote e partial clone de github/spec-kit no scratchpad; git log por tag |
| Volatilidade por camada no upstream (0.16.4 → 1.0.12) | Templates de metodologia (spec, plan, tasks, constitution, checklist): 0 mudanças. integrations/: 47 arquivos (+3.896/−2.585). workflows/: 62 arquivos (+5.416/−3.497). templates/commands: 10 arquivos (+103/−46) | git diff --stat v0.16.4 v1.0.12 por caminho |
| Registro de integrações vs adapters_gen | 0.16.4 = 37 agentes (bate com a tabela: 33 + 4 bespoke). v1.0.12 = 41: entraram docker_agent, dsh e muse; qodercli migrou de .qoder/commands para .qoder/skills | git ls-tree de src/specify_cli/integrations por tag; comparação com adapters_gen.py list |
| Fases do Spec Kit detectadas pelo discovery neste repo | 0 de 10 skills instaladas (speckit_commands: [], speckit_command_paths: {}) | python3 spec-master/lib/cli.py discovery scan --path . na cópia do scratchpad (0,2s) |
| Entregas fora do ciclo Spec Kit | 13 de 16 itens do roadmap (81%); 7 de 10 features do state.json com status COMPLETED e as 7 fases em PENDING | docs/market-benchmark-roadmap.md:172-207 e inspeção de .spec-master/state.json |
| Inflação de tier causada pelo formato de tasks | 3 de 3 features do dogfood: S no intake viram M no pre_implement (21 a 26 tasks, limite 12) | cli.py risk classify --stage intake\|pre_implement na cópia do scratchpad |
| Peso de instalação do Spec Kit | No repo-alvo: .specify/ (20 arquivos, 102.941 B) + 10 skills (134.330 B) por integração, ~237KB ≈ 59k tokens versionados. CLI specify: Python ≥3.11 + 8 dependências (typer, click, rich, readchar, pyyaml, packaging, pathspec, json5), 242 módulos, ~2,5MB | find/wc no repo; pyproject.toml e git ls-tree -l do upstream v1.0.12 |
| Sobreposição com o ecossistema upstream | 174 extensões e 40 presets comunitários; ~81 extensões com tema sobreposto, entre elas tinyspec ('skip the heavy multi-step SDD process'), bugfix, fleet, orchestrator, worktrees, trace, speckit-utils, maqa e o preset command-density | Parse de extensions/catalog.community.json e presets/catalog.community.json em v1.0.12 com filtro por palavras-chave |

### Scorecard

| Dimensão | Nota | Máximo | Justificativa |
|---|---:|---:|---|
| Isolamento do core determinístico em relação ao Spec Kit | 8 | 10 | Só 0,7% das linhas tocam o Spec Kit; MCP, grafo, knowledge, métricas e hooks são agnósticos. Os pontos acoplados estão concentrados em phase_contracts, discovery e nos runners. |
| Robustez a mudanças do upstream | 2 | 10 | O drift já quebrou discovery, adapter e prompts; o bootstrap não tem pin nem checagem de versão; o upstream fez 14 releases em 42 dias e os testes congelam o layout antigo. |
| Clareza da fonte da verdade | 3 | 10 | Quatro conflitos demonstrados: numeração (colisão em 006), estado de fase (upsert contorna o guard), constitution (dupla governança) e branch (dupla naming). |
| Flexibilidade de fluxo (fluxos leves) | 2 | 10 | FEATURE_PHASES fixo; só clarify pode ser pulado; XS exige specify, plan, tasks e analyze; o dono contornou o ciclo em 81% dos itens. |
| Eficiência de tokens da camada metodológica | 3 | 10 | ~24,7k tokens de instruções mais ~14,5k de artefatos por feature, com ~29% de boilerplate irrelevante; custo não medido (tokens = 0). |
| Prontidão para virar harness com packs | 7 | 10 | O core já é agnóstico, o web bundle já executa fases sem o Spec Kit e as alavancas do Spec Kit (SPECIFY_FEATURE_DIRECTORY, --number, GIT_BRANCH_NAME) permitem um compat sem fork. Faltam o contrato de pack e a emenda de governança. |

### Achados

#### A1 — O drift de layout já quebrou a integração com o Spec Kit instalado (impacto: alto)

discovery.py só procura `speckit.*.md` em .claude/commands, .opencode/commands e .qwen/commands. Mas o Spec Kit instala o Claude como skills (`.claude/skills/speckit-<phase>/SKILL.md`) desde v0.4.5 (02/04/2026), e Copilot e Codex também usam skills. Resultado: a detecção falha nos 3 adapters principais. O adapter Claude e o PROTOCOL mandam ler `.claude/commands/speckit.<phase>.md`, que não existe. Pela regra do PROTOCOL, isso é FAILED. Os prompt templates invocam `/speckit.<phase>`, mas o separador instalado é '-', e o specify passa `--files`, flag que nenhuma skill aceita. Os testes cristalizam o layout antigo, então a suíte passa enquanto o comportamento real está errado. O dogfood detectou o drift em 26/09 e adiou a correção.

**Evidência:** discovery.py:141-164; saída real do scan: speckit_commands: []. adapters/claude-code.md:30-37; PROTOCOL.md:390-395 ('if that command/skill doesn't exist, this is a FAILED condition'); templates/prompts/specify.md:5 ('/speckit.specify --files …'), `grep --files` nas skills = 0 ocorrências; .specify/integration.json: "invoke_separator": "-"; tests/test_discovery.py:72-95; .spec-master/reports/discovery.md, seção 'Spec Kit command layout drift'; upstream: integrations/claude/__init__.py é SkillsIntegration desde v0.4.5.

#### A2 — Bootstrap sem pin e sem checagem de compatibilidade diante de um upstream muito rápido (impacto: alto)

PROTOCOL e init.sh instalam o Spec Kit do HEAD de main (`uvx --from git+https://github.com/github/spec-kit.git`), sem tag. A única checagem é a presença de `.specify/`; ninguém compara com `.specify/integration.json.version` (0.16.4). O upstream saiu 14 versões desde o pin, incluindo a major 1.0.0, e mudou contratos que o protocolo usa. Exemplos: o JSON do setup-plan passou de SPECS_DIR para FEATURE_DIR; o `specify init` travava em pickers de setas dentro de agent harnesses (#4178, corrigido só na 0.16.5), exatamente o comando que o Step 2 manda rodar; o qodercli migrou de layout na 1.0.0 (#4205). Com isso, cada instalação nova pode trazer um formato que o core não conhece.

**Evidência:** PROTOCOL.md:183-187; init.sh:470-472; discovery.py:126 (`spec_kit_present = os.path.isdir(... '.specify')`); .specify/init-options.json "speckit_version": "0.16.4"; upstream CHANGELOG 0.16.5 'fix(init): stop specify init hanging on arrow-key pickers in agent harnesses (#4178)'; git diff v0.16.4 v1.0.12 templates/commands/plan.md (SPECS_DIR→FEATURE_DIR).

#### A3 — Fonte da verdade conflitante na numeração e no diretório de feature (impacto: alto)

Nenhuma função determinística calcula `spec_directory`: o agente informa o valor no `upsert-feature`. Do lado do Spec Kit, a skill specify da 0.16.4 manda o próprio LLM escolher o próximo NNN varrendo `specs/`, o que também não é determinístico e contraria o Princípio I. O state.json reserva specs/006 a 012, que não existem em disco. Já specs/001 e 002 existem em disco, mas não estão no state. Um dry-run do create-new-feature.sh devolve 006 como próximo número, o que colide com `specs/006-sast-quality-gate`, já reservado no state.

**Evidência:** Dry-run: `{"BRANCH_NAME":"006-new-lite-flow","FEATURE_NUM":"006"}`, enquanto o state.json tem ['specs/006-sast-quality-gate']. `ls specs/` mostra só 001 a 005. .claude/skills/speckit-specify/SKILL.md:86-93 ('next available 3-digit number after scanning existing directories in specs/'); `grep spec_directory lib/` confirma que só há leitores, nenhum alocador.

#### A4 — O estado de fase não é evidência, e os contratos dependem de um ponteiro local do Spec Kit (impacto: alto)

(a) `state upsert-feature` aceita status COMPLETED com todas as fases PASSED apontando para um diretório inexistente, e o guard de `transition` fica contornado. Hoje 7 features estão COMPLETED com fases PENDING por causa de um campo `delivery` que o core desconhece. (b) Os contratos do guarded mode usam globs `specs/*` sem escopo por feature: artefatos de features antigas satisfazem ou contaminam a feature atual (falso placeholder em 001, cuja spec apenas cita `[PROJECT_NAME]`). Eles também exigem `.specify/feature.json`, que o próprio Spec Kit ignora no git: num checkout novo, o specify fica 'missing' e resolve_active_feature_dir lança ActiveFeatureUnresolved. (c) No guarded mode, as tentativas ficam por fase no nível do projeto e o prompt é genérico ('Execute /speckit.{phase} for this project'), sem feature.

**Evidência:** Teste na cópia: upsert de 'ghost' com fases PASSED e spec_directory specs/999-ghost foi aceito sem erro. state.py:141-154; phase_contracts.py:35-56 e 178-203; .specify/.gitignore:6 (`feature.json`); execução no scratch: `specify missing=['.specify/feature.json']`, `tasks placeholders=['specs/001-…/tasks.md', …]`; controller.py:136-151 e 274; `grep -rn delivery lib/` não encontra tratamento de `delivery.mode`.

#### A5 — Dois processos de governança para a mesma constitution (impacto: medio)

A skill speckit-constitution exige bump semver (MINOR para princípio novo) e um Sync Impact Report no topo do arquivo. O Spec Master usa um diff estrutural por heading (constitution_diff.py) e marca APPLIED. Em 26/09 os princípios VII a X foram adicionados sem bump e sem report: o arquivo continua em Version 1.0.0 e Last Amended 2026-08-17. O mesmo arquivo `.specify/memory/constitution.md` tem dois donos, e nenhum dos dois contratos foi cumprido por inteiro.

**Evidência:** .specify/memory/constitution.md:51-73 e 115; `git log -- .specify/memory/constitution.md`: 06dcef0 (2026-09-26) adiciona '### VII'…'### X' sem alterar a linha de versão; .claude/skills/speckit-constitution/SKILL.md:102-123 (semver + Sync Impact Report); state.json: constitution.status = APPLIED com additions VII a X.

#### A6 — Duas autoridades para branch e dois sistemas de hooks (impacto: medio)

git_strategy gera `feature/<slug>` ou preserva `APP-1234`. Ao mesmo tempo, recomenda instalar a extensão git do Spec Kit (`install_git_extension`), que cria branches `{number}-{slug}` no hook before_specify e exige que o último segmento comece com `{number}-`, com validação própria em speckit.git.validate. Com as duas ativas, os nomes divergem e a validação do Spec Kit reprova o nome do Spec Master. Na mesma linha, o Spec Kit despacha hooks via `.specify/extensions.yml` em todas as skills, enquanto o Spec Master tem hooks.py com `.spec-master/hooks.json`: dois barramentos de eventos para o mesmo ciclo.

**Evidência:** git_strategy.py:27-37 e 56-68; upstream v0.16.4 extensions/git/extension.yml (hooks before_specify → speckit.git.feature) e config-template.yml ('final path segment must start with {number}-'); hooks.py:1-45 (EVENT_TYPES); .claude/skills/speckit-plan/SKILL.md:22-56.

#### A7 — Fluxo leve impossível por construção, e o dono contornou o ciclo (impacto: alto)

FEATURE_PHASES é fixo com 7 fases e só clarify pode ser pulado. Todos os perfis de cerimônia, inclusive XS ('Trivial change'), exigem specify, plan, tasks, analyze, implement e validate. O plan do Spec Kit gera research, data-model, contracts e quickstart, e o tasks-template impõe Setup, Foundational, US1..N e Polish, o que dá 21 a 29 tasks para módulos de 92 a 131 linhas. Essa granularidade ainda infla o tier: as 3 features do dogfood foram de S para M no pre_implement só pela contagem de tasks, o que torna clarify obrigatório de novo. Na prática, o usuário pausou o ciclo e entregou 13 de 16 itens por fora, marcando `delivery.mode: agentic-outside-spec-master` à mão. Os commits sugerem que os artefatos da feature 005 chegaram 9 minutos depois do código (HIPÓTESE de documentação a posteriori).

**Evidência:** state.py:33-45; risk_profile.py:70-89 (`_profile`: "specify": "required", …, "analyze": "required" em todos os tiers); .specify/templates/tasks-template.md:48-150; risk classify: 005 intake=S → pre_implement=M ('tasks': 21, limite 12); docs/market-benchmark-roadmap.md:172-207; commits 1e37327 (11:31, código) → 6c31029 (11:40, 'code already landed').

#### A8 — A camada Spec Kit domina o custo de tokens por feature, e o projeto não consegue medir isso (impacto: medio)

São ~24,7k tokens de instruções por feature, 14,3x os prompts próprios, e ~29% disso é boilerplate de extension hooks inútil sem extensions.yml. Os artefatos somam ~14,5k tokens por feature, relidos por plan, tasks, analyze e implement. O modelo para a feature 005 dá ~72k tokens, mais ~12,6k por ciclo de repair, para produzir ~2,5k tokens de código e testes. O upstream reconhece o problema: /speckit-analyze devolve relatórios de 300 a 500 linhas que se acumulam até travar sessões longas (#3185), e a comunidade criou o preset command-density para comprimir os prompts. rounds.json registra tokens = 0 e durações de 0,0s ou com horários redondos, então o próprio harness não enxerga esse custo.

**Evidência:** Medições com wc -c e bytes/4 (ver métricas); upstream integrations/claude/__init__.py (comentário sobre FORK_CONTEXT_COMMANDS vazio e #3185); presets/catalog.community.json: command-density; .spec-master/metrics/rounds.json (9 linhas, soma total_tokens = 0; specify, clarify, plan e tasks com duration_seconds 0.0).

#### A9 — O core já é quase agnóstico e o web bundle prova que um motor próprio é viável (impacto: medio)

Só 0,7% das linhas do core tocam o Spec Kit, concentradas em phase_contracts, discovery, web_bundle, risk_profile, adapters_gen e nos runners guarded. O acoplamento pesado está no PROTOCOL.md (52 menções, 49,8KB) e no layout de artefatos. O web bundle já executa specify, plan e tasks sem nenhuma skill ou template do Spec Kit, usando só templates/prompts próprios (~1KB cada) e o contexto. Isso mostra que o motor próprio funciona e, ao mesmo tempo, contradiz a regra constitucional de que fases 'never simulated or hand-authored as a substitute'. O custo de desacoplar é baixo no código e alto na narrativa e na governança.

**Evidência:** Contagem por regex (ver métricas); web_bundle.py:1-22 e 272-306 (renderiza templates/prompts/<phase>.md); .specify/memory/constitution.md:99-103; PROTOCOL.md:21-28; grep de menções ao Spec Kit por arquivo.

#### A10 — O upstream está absorvendo a proposta de valor da 'extensão orquestradora' (impacto: medio)

O Spec Kit 1.x tem workflow engine próprio: 12 step types, incluindo gate, if/switch, while/do-while e fan-out/fan-in, além de pause/resume no ponto exato, overlays com prioridade e integração e modelo por step. Tem também events, presets e bundles. O catálogo comunitário cobre quase todas as features do Spec Master: fleet (ciclo com gates HITL), orchestrator (estado entre features), worktrees, trace, speckit-utils (resume e traceability), maqa (multiagente + QA), adrkit e memory (decisões), jira, linear e azure-devops. Existe até o tinyspec, que se descreve como 'skip the heavy multi-step SDD process'. Como extensão, o Spec Master vira mais um entre dezenas de orquestradores. O diferencial é o harness determinístico integrado (estado, promoção por evidência, tiers, papéis, grafo e métricas num pacote stdlib), e ele só aparece se o produto não depender do host.

**Evidência:** Upstream v1.0.12 docs/reference/workflows.md (seção Step Types, linhas 527-541); extensions/catalog.community.json (174 entradas; tinyspec, fleet, orchestrator, worktrees, trace, speckit-utils, maqa); presets/catalog.community.json (autonomous-run-governance, parallel-autonomous-run-governance, model-routing-governance); .specify/workflows/speckit/workflow.yml ('Full SDD Cycle' com gates, já instalado no repo).

#### A11 — O registro de integrações está duplicado e a experiência fica fragmentada no host (impacto: medio)

adapters_gen.py transcreve à mão o registry do Spec Kit ('as of the spec-kit commit inspected'), sem versão de origem, e já está defasado: faltam docker_agent, dsh e muse, e o qodercli aponta para .qoder/commands, que o Qoder 1.24+ não lê mais. No host, as 10 skills speckit-* têm `user-invocable: true` e `disable-model-invocation: false`: o modelo pode acioná-las sozinho e o usuário pode rodar /speckit-plan direto, sem passar pelo state machine. O Spec Master também não pode ajustar esses arquivos, porque o manifest do Spec Kit guarda o sha256 de cada um e um refresh os sobrescreve ou acusa conflito.

**Evidência:** adapters_gen.py:11-16 e 132 (`Agent("qodercli", ".qoder/commands", "command", …)`); upstream v1.0.12 integrations/qodercli/__init__.py:3-27 (SkillsIntegration, .qoder/skills); frontmatter das skills (grep user-invocable/disable-model-invocation: 10 de 10); .specify/integrations/claude.manifest.json (hashes por arquivo).

#### A12 — O guarded mode é duplamente acoplado e a validação depende dos marcadores do template core (impacto: baixo)

O guarded mode só funciona com OpenCode (`opencode run --command speckit.<phase>`) e fixa `.opencode/commands/*` no allowlist do constitution. A detecção de placeholders usa marcadores literais do template core, como [FEATURE NAME], [###-feature-name] e [DATE]. Só que a skill specify resolve o template pela pilha de presets ('equivalent to specify preset resolve spec-template'), então um preset que troque os marcadores enfraquece a validação sem aviso. É outro ponto em que a correção depende de detalhes internos do Spec Kit.

**Evidência:** phase_runner.py:100-110; opencode_runner.py:50-53; phase_contracts.py:44-49 e 72-91; .claude/skills/speckit-specify/SKILL.md:98-99; docs/spec-master/guarded-mode-spec.md:67 e 324 (GM-012: 'suportar inicialmente OpenCode').

### Recomendações

#### R1 — Estancar o drift atual sem mudar a arquitetura (P0 · esforço S)

1) Fazer o discovery ler o layout a partir de `.specify/integration.json` e `.specify/integrations/*.manifest.json`, que são a fonte da verdade do instalador, e usar varredura de diretórios só como fallback. Suportar skills (`.claude/skills`, `.github/skills`, `.agents/skills`). 2) Corrigir o adapter claude-code, o PROTOCOL.md:390-393 e os prompts: resolver `/speckit-<phase>` pelo `invoke_separator` e remover `--files`. 3) Trocar as fixtures de test_discovery pelo layout de skills e criar um teste de contrato que roda o discovery contra o `.specify/` real deste repo e exige as 10 skills detectadas.

**Ganho esperado:** Fases do Spec Kit detectáveis nos 3 adapters principais; fim do FAILED indevido; o CI passa a pegar drift de layout.

**Riscos:** Baixo. Manter o fallback para o layout de commands (opencode e qwen continuam em .../commands).

#### R2 — Pin e faixa de compatibilidade do Spec Kit, com doctor (P0 · esforço S)

Declarar `speckit_compat: ">=0.16,<1.1"` (faixa testada) no engine. Trocar o bootstrap por `uvx --from git+https://github.com/github/spec-kit.git@vX.Y.Z specify init --here --integration <agente>` (não interativo) no PROTOCOL.md:183-186 e no init.sh:472. Criar um `doctor` que compare `.specify/integration.json.version` com a faixa e emita WARN fora dela. Rodar um job noturno de smoke contra o último release, comparando `templates/commands` e o registry por diff.

**Ganho esperado:** Instalações reproduzíveis; drift detectado em horas, não em semanas; evita o travamento do init em agent harness.

**Riscos:** Com pin, correções do upstream não chegam sozinhas. Mitigar com o smoke noturno e uma política de bump mensal.

#### R3 — Harness como fonte única de identidade, ponteiro e promoção (P0 · esforço M)

1) Criar `feature allocate --slug`, determinístico: considera specs/, reservas no state e branches, e passa a ser o único caminho para gravar `spec_directory`. 2) No pack compat, repassar a decisão ao Spec Kit pelas alavancas oficiais: `SPECIFY_FEATURE_DIRECTORY` (common.sh:181-192 e skill specify:86-88), `--number` do create-new-feature.sh e `GIT_BRANCH_NAME` da extensão git. 3) Escopar os contratos de fase ao `spec_directory` do state em vez de `specs/*` e `.specify/feature.json`. 4) `upsert-feature` passa a rejeitar status de fase diferente de PENDING; promoção só via `transition`, com evidência (hash do artefato e resultado dos validadores). 5) Reconciliar o state: marcar 006–012 como `phantom` e importar 001 e 002.

**Ganho esperado:** Elimina as colisões de numeração e branch, funciona em checkout novo, CI e worktrees, e faz o PASSED voltar a significar alguma coisa.

**Riscos:** Features `delivery: outside` exigem migração explícita. A skill do Spec Kit precisa receber o diretório pelo prompt no modo native (instrução, não garantia). Validar com o teste de A4.

#### R4 — Contrato de pack e o fluxo atual como pack speckit-compat, sem mudança observável (P0 · esforço M)

Transformar em dados de `packs/<id>/pack.yaml` o que hoje está fixo no código: FEATURE_PHASES, SKIPPABLE_PHASES, PHASE_ARTIFACTS, PHASE_ALLOWED_WRITES, _PLACEHOLDER_PATTERNS e os prompts. Contrato mínimo: `id, version, engine: ">=2", applies_to{tiers, intents}, layout{feature_dir: "specs/{num}-{slug}"|".spec-master/work/{id}", numbering: sequential|timestamp|none}, phases[{id, kind: author|execute|review|decide, needs[], prompt, context[], budget_tokens, produces[{path, template, required}], allowed_writes[], validators[exists|non_empty|no_placeholders{patterns}|sections{required}|ears|coverage{from,to}|quality_gates|sast|graph_drift], gate: auto|human|none, repair{target, max_cycles}, skip_if, result_schema}], exports[]`. O engine garante promoção só por validadores, um estado único, métricas e hooks por fase e policy de writes. O pack speckit-compat reproduz o comportamento atual e delega cada fase à skill ou comando instalado. O state ganha `pack` por feature, com migração idempotente e default speckit-compat.

**Ganho esperado:** O motor de fases fica independente do Spec Kit. Os testes de `--mode native` continuam passando sem alteração (Constitution VI). É a base para todos os outros packs.

**Riscos:** Risco de criar uma 'mini linguagem de workflow'. Limitar a um DAG linear com repair e skip; nada de loops ou expressões genéricas.

#### R5 — Packs leves nativos e roteamento por tier e intenção (P0 · esforço M)

Entregar 4 packs sem dependência de `.specify/`, com templates stdlib próprios. patch (XS): intent → implement → verify (gates + checagem de AC). feature-lite (S): um único feature.md com problema, AC (EARS opcional) e checklist de tasks inline → implement → verify, com analyze trocado por lint determinístico AC↔tasks↔testes. bugfix: reproduce (comando que falha antes) → fix → regression → verify. spike: question → explore (writes restritos a `.spec-master/spikes/<id>/`) → decision record na decision memory, sem implement. Um router escolhe o pack pelo tier e pela intenção, com override do usuário. O Step 2 deixa de devolver FAILED quando o Spec Kit falta; só falha se o pack escolhido for speckit-compat. Isso oficializa, com evidência, o caminho que hoje é o `delivery.mode` manual.

**Ganho esperado:** XS e S passam de ~72k para ~5–15k tokens por feature (HIPÓTESE a medir), sem os 58KB de artefatos. O ciclo volta a ser usável para os 81% de itens que hoje correm por fora.

**Riscos:** Menos rastreabilidade se o router for leniente. Mitigar com pisos de sensibilidade (security, data e infra forçam full-sdd) e o re-tier no pre_implement que já existe.

#### R6 — full-sdd nativo e enxuto, com resultado de fase compacto e isolado (P1 · esforço L)

Pack para M, L e XL com templates próprios derivados dos templates spec, plan e tasks do Spec Kit (MIT, com atribuição; sem nenhuma mudança entre 0.16.4 e 1.0.12, logo estáveis). Sem boilerplate de extension hooks. Artefatos opcionais por tier: research, data-model e contracts só a partir de L; quickstart opcional. Cada fase devolve um `result_schema` JSON compacto (status, artefatos com hash, findings resumidos), para rodar em subagente ou contexto isolado do host (`.claude/agents/`, context fork) sem reinjetar relatórios de 300–500 linhas, o problema do upstream #3185. O guarded mode vira um runner genérico que recebe o comando do pack, em vez de ficar preso a OpenCode e `speckit.<phase>`.

**Ganho esperado:** Corta os ~29% de boilerplate e a releitura de artefatos desnecessários; sessões longas estáveis; isolamento por fase disponível fora do OpenCode.

**Riscos:** Divergência metodológica em relação ao Spec Kit. Mitigar com export compatível (R7) e testes de round-trip.

#### R7 — Import e export Spec Kit como interoperabilidade de primeira classe (P1 · esforço M)

`pack speckit import`: lê specs/NNN-* e cria ou mescla features no state (id pelo slug, fases inferidas dos artefatos, com hash como evidência e `source: imported`, sem marcar validate como PASSED sem gates). Roda automaticamente no Step 0 quando houver specs/ não rastreados. `pack speckit export`: materializa qualquer feature (inclusive de feature-lite) como specs/NNN-slug/{spec,plan,tasks}.md no formato dos templates, com número vindo do allocate, e grava `.specify/feature.json` só se `.specify/` existir. Opcional: compilar um pack para o `workflow.yml` do Spec Kit 1.x (steps command e gate) para quem quiser rodar dentro do Spec Kit.

**Ganho esperado:** Os usuários atuais continuam com specs/NNN e skills; os novos podem sair ou entrar no Spec Kit sem perder histórico. O Spec Kit vira destino e origem, não requisito.

**Riscos:** Inferência de fase a partir de artefatos pode superestimar o progresso. Mitigar marcando como IMPORTED, sem PASSED, até a revalidação pelos validadores.

#### R8 — Governança única: emendar o Princípio VII, a constitution do harness e um só barramento de hooks (P1 · esforço S)

Propor, via `constitution diff` e com aprovação explícita do usuário (a mudança conflita com cláusula MUST/NEVER), a troca de 'never reimplements a speckit.* command, only orchestrates' por 'Spec Master owns the harness and methodology packs; Spec Kit is a supported compatibility pack; ecosystem integrations (trackers, scanners, extensions) MUST still be reused'. Ajustar também a seção Development Workflow ('never simulated'). A constitution passa a ser artefato do harness, com bump semver automático calculado pelo diff e espelhada em `.specify/memory/constitution.md` apenas no pack compat. Manter hooks.py como barramento único e, no compat, traduzir para `.specify/extensions.yml` só quando o usuário usar extensões do Spec Kit.

**Ganho esperado:** Acaba o duplo dono da constitution e dos hooks; a governança fica coerente com a nova identidade de harness.

**Riscos:** Decisão de produto e de governança, que exige aprovação explícita. Sem ela, R4 a R7 violam a constitution vigente.

#### R9 — Plano de migração em ondas sem quebrar usuários (P1 · esforço M)

Onda 0 (R1, R2 e a reconciliação de R3): nada muda para o usuário. Onda 1: engine v2 com packs; `state migrate` v1→v2 idempotente e com backup; todo state existente e todo repo com `.specify/` usa speckit-compat por padrão; `/spec-master <ctx>` continua idêntico. Onda 2: packs leves opt-in (`--pack`, ou router com confirmação); repos sem `.specify/` passam a funcionar. Onda 3: full-sdd nativo e import/export; import automático no Step 0. Onda 4: router como default em projetos novos; speckit-compat segue suportado dentro da faixa de versões. Adapters: preferir o servidor MCP e o padrão `.agents/skills`/AGENTS.md; adapters_gen passa a derivar as linhas do registry instalado quando `.specify/` existir e mantém uma tabela mínima própria, versionada com a data e a versão de origem, só para o entrypoint do Spec Master. Nunca apagar `.specify/` nem specs/.

**Ganho esperado:** Transição sem ruptura; cada onda entrega valor e pode ser revertida; usuários atuais mantêm o fluxo e os artefatos.

**Riscos:** Período de dupla manutenção (compat + nativo). Mitigar com testes de contrato por pack e com o smoke do upstream de R2.

#### R10 — Lista explícita do que não reimplementar e métricas por pack (P2 · esforço S)

Documentar no README e na constitution o que fica de fora. (1) O instalador e registry de mais de 40 agentes: a camada mais volátil do upstream, com +3.896/−2.585 linhas em integrations desde o pin. (2) Catálogo ou marketplace de extensões, presets e bundles: packs são diretórios locais, publicáveis depois como preset ou bundle do Spec Kit. (3) Uma linguagem genérica de workflow com loops, fan-out, expressões e overlays, que já existe no Spec Kit 1.x (usar export, R7). (4) Clientes de tracker (Jira, Linear, ADO, GitHub Issues): manter o detect-then-instruct. (5) A automação git quando a extensão git estiver presente no compat. (6) Os prompts de clarify e analyze do compat, que devem ser delegados. (7) Runtime de modelo e sandbox. Instrumentar cada pack com tokens (quando o host expuser), tempo real, bytes de artefato e ciclos de repair, para validar o ganho previsto.

**Ganho esperado:** Foco no diferencial do harness e custo de manutenção contido. Decisões futuras baseadas em dados, sem as métricas zeradas ou fabricadas de hoje.

**Riscos:** Sem as métricas por pack, a tese do ganho de tokens continua como HIPÓTESE. O token count depende do adapter.

### Perguntas abertas

- Existe base de usuários externos que dependa do fluxo speckit-* e de specs/NNN? Isso define se speckit-compat deve continuar como default e por quanto tempo.
- O dono aprova emendar o Princípio VII e a seção Development Workflow ('never simulated')? Pela seção Governance, a mudança exige aprovação explícita, e sem ela os packs nativos violam a constitution vigente.
- Qual faixa de versões do Spec Kit o pack compat deve suportar (0.16.x, 1.x ou ambas) e qual será a política de atualização do pin?
- Os packs nativos devem manter o layout specs/NNN-slug (interop máxima) ou usar .spec-master/work/<id>, com export sob demanda?
- O guarded mode deve virar um runner genérico (subagentes Claude Code, Codex exec, OpenCode) ou ser aposentado em favor do isolamento por subagente do host?
- Onde a constitution deve morar no modelo harness: .spec-master/ com espelho em .specify/, ou continuar em .specify/memory/?
- Os packs devem ser distribuídos também como presets ou bundles do catálogo do Spec Kit (alcance) ou só por canal próprio (controle)?
- O PROTOCOL.md cita 'CLAUDE.md §N' 14 vezes (§5, §29, §38...), mas não existe CLAUDE.md no repo. Qual é a fonte normativa dessas regras, a ser reescrita como especificação do harness?
- 21 módulos de teste importam pytest (falham com unittest stdlib, contrariando o Princípio II), e o README anuncia 631 testes enquanto o unittest executa 502. Qual suíte é a referência para os testes de contrato por pack?

### Referências

- spec-master/lib/discovery.py:126-185
- spec-master/lib/phase_contracts.py:35-91,178-203
- spec-master/lib/state.py:33-47,141-154
- spec-master/lib/risk_profile.py:70-89
- spec-master/lib/git_strategy.py:27-69
- spec-master/lib/adapters_gen.py:11-16,132
- spec-master/lib/tracker_orchestration.py:12-18
- spec-master/lib/controller.py:136-151,270-277
- spec-master/lib/phase_runner.py:100-110
- spec-master/lib/opencode_runner.py:50-53
- spec-master/lib/web_bundle.py:1-22,272-306
- spec-master/lib/hooks.py:1-45
- spec-master/PROTOCOL.md:21-28,173-196,386-395,644-646
- spec-master/adapters/claude-code.md:30-37
- spec-master/templates/prompts/specify.md:5
- spec-master/tests/test_discovery.py:72-95
- .specify/memory/constitution.md:51-58,95-103,115
- .specify/init-options.json
- .specify/integration.json
- .specify/integrations/claude.manifest.json
- .specify/.gitignore:6
- .specify/workflows/speckit/workflow.yml
- .claude/skills/speckit-specify/SKILL.md:74-112
- .claude/skills/speckit-plan/SKILL.md:22-69
- init.sh:455-490
- .spec-master/state.json
- .spec-master/reports/discovery.md
- .spec-master/metrics/rounds.json
- docs/market-benchmark-roadmap.md:172-207
- Upstream github/spec-kit: tags v0.16.4 (2026-08-14) a v1.0.12 (2026-09-25); CHANGELOG 0.16.5 (#4178), 1.0.0 (#4205); docs/reference/workflows.md (Step Types); src/specify_cli/integrations/claude/__init__.py (FORK_CONTEXT_COMMANDS, #3185); src/specify_cli/integrations/qodercli/__init__.py; extensions/git/extension.yml e config-template.yml (v0.16.4); extensions/catalog.community.json e presets/catalog.community.json (v1.0.12)
- Scratchpad com a cópia do repo e o partial clone do upstream: <scratch>/acoplamento-speckit/

---

## Benchmark de mercado

### Resumo

Entre 2025 e 2026 o mercado tirou o valor do "processo escrito em prosa" e o colocou no harness: hooks que bloqueiam de fato, subagentes com contexto isolado, workflows determinísticos, evals comparados a um baseline e telemetria nativa, tudo distribuído como plugin ou Agent Skill.
Todos os frameworks SDD relevantes criaram "lanes" leves que encurtam o pipeline: Kiro (Quick Spec, Bugfix, vibe), BMAD (Quick Flow), OpenSpec (OPSX com delta specs), GSD (/gsd-quick) e Agent OS v3, que delega o planejamento ao plan mode do host.
Há evidência de que o ciclo Spec Kit completo sai caro em mudanças pequenas e médias. Na Scott Logic, custou ~7x mais tempo de agente e ~14x mais tempo humano. No próprio repo, a proporção é ~5:1 entre linhas de spec e linhas de código, e 7 das 10 features foram entregues fora do fluxo.
O Spec Master tem diferenciais reais: classificação de proveniência (EXPLICIT/INFERRED/DISCOVERED_FROM_CODEBASE/UNRESOLVED), core determinístico com 631 testes sem LLM, rastreabilidade por critério de aceite e risco por sensibilidade.
Está atrás em seis frentes:
- enforcement: 0 hooks do host; o preflight é chamado voluntariamente pelo agente;
- isolamento: o Team Mode é persona em prompt num único contexto;
- evals: 5 checagens fixas, sem tarefa nem baseline;
- telemetria: 9 de 9 rodadas com 0 tokens;
- economia de contexto: ~39k tokens de instruções por ciclo e 76 tools MCP (~8,7k tokens);
- distribuição: não há plugin.
Além disso, o Spec Kit 1.0 (o repo usa 0.16.4) já traz engine de workflows, extensões e presets, o que esvazia o papel de "orquestrador acima do Spec Kit".
Recomendação central: reposicionar o Spec Master como harness, ou seja, lanes por risco + hooks + subagentes + evals + telemetria, empacotado como plugin/skill. O Spec Kit vira um "process pack" usado só na lane Full, e a disciplina anti-alucinação vira um sensor determinístico aplicado por hooks.

### Métricas

| Métrica | Valor | Método |
|---|---|---|
| Versão do Spec Kit instalada vs upstream | 0.16.4 (instalada em 2026-08-17) vs v1.0.12 (2026-09-25); a v1.0.0 saiu em 2026-08-21 | .specify/init-options.json:8 e workflow-registry.json; página de releases do GitHub e newreleases.io |
| Instruções carregadas por ciclo completo (antes de qualquer contexto do projeto) | ~38,8k tokens: ~15,9k do Spec Master + ~22,9k das 7 skills speckit | wc -c, tokens = bytes/4. Spec Master: PROTOCOL 49.778 B + comando 3.117 + prompts por fase 8.269 + templates 2.685. Skills speckit das 7 fases: 91.432 B |
| Tamanho do PROTOCOL.md | 837 linhas / 49.778 B (~12,4k tokens), lido 'integralmente antes de fazer qualquer outra coisa' | wc -l; .claude/commands/spec-master.md:12. Referências de mercado: SKILL.md < 500 linhas (docs do Claude Code) e AGENTS.md de ~100 linhas (OpenAI) |
| Superfície do servidor MCP | 76 tools (47 readOnly); 34.781 B de schemas (~8,7k tokens) | python3 spec-master/mcp/spec_master_mcp.py --list-tools rodado numa cópia no scratchpad; bytes/4 do JSON compacto |
| Comandos do CLI que o agente precisa chamar | 64 comandos distintos no PROTOCOL; 31 distintos e 51 referências só no Step 6 (por feature) | regex de grupo/ação do CLI sobre spec-master/PROTOCOL.md |
| Latência do core Python | ~0,10 a 0,15 s por chamada: o gargalo é token x turno, não Python | bash time em 3 execuções de 'cli.py state show' numa cópia no scratchpad |
| Proporção artefato/código no dogfood (commit 06dcef0) | 1.729 linhas em specs/ + 2.020 linhas de churn em .spec-master/.specify vs 327 linhas de código de produção (+259 de teste), ~5,3:1 spec:código | git show --numstat 06dcef0 agregado por diretório |
| Features entregues fora do fluxo | 7/10 (70%) com status COMPLETED e as 7 fases PENDING (agentic-outside-spec-master); só 3/10 passaram pelas 7 fases | parse de .spec-master/state.json |
| Tokens registrados nas métricas | 0 em 9 de 9 rodadas (input, output e total) | parse de .spec-master/metrics/rounds.json; PROTOCOL.md:342 manda gravar 0 quando o adapter não expõe tokens |
| Cobertura de evals do harness | 5 checagens determinísticas fixas (evals.py, 50 linhas); 0 casos de tarefa, transcript ou baseline | leitura de spec-master/lib/evals.py |
| Hooks do host configurados | 0: não existem .claude/settings.json, hooks.json, .claude-plugin/plugin.json nem .claude/agents/ | find no repositório; grep em tool_policy.py (não lê stdin de hook nem emite permissionDecision) |
| Referências órfãs no protocolo | 11 citações a 'CLAUDE.md §N'; o arquivo não existe e nunca apareceu no histórico git (o README.md:495 o lista) | grep -c 'CLAUDE.md §' PROTOCOL.md; git log --all -- CLAUDE.md (saída vazia) |
| Benchmark externo: Spec Kit vs prompting iterativo | Spec Kit: ~57 min de agente + ~5,5 h de revisão e 4.839 linhas de markdown para ~990 LOC. Iterativo: 8 min + ~24 min, 0 markdown, ~1.000 LOC (~7x tempo de agente, ~14x tempo humano) | Scott Logic, 2025-11-26 (fonte primária) |
| Efeito de arquivos de contexto (AGENTS.md) | sem ganho geral de sucesso e custo de inferência +20% | Gloaguen et al., arXiv 2602.11988 (fev/2026, rev. jun/2026) |
| Enforcement real de regras em CLAUDE.md públicos | 4,4% das regras de segurança têm enforcement; 60% dos harnesses não têm testes/evals | survey da marmelab com 246 repositórios (2026-09-24) |
| Primitivas de hook por ecossistema | Claude Code: 33 eventos e 5 tipos de handler. Codex: 12 eventos com deny/exit 2. Kiro: 11 gatilhos (PreToolUse, PromptSubmit e PreTaskExecution bloqueiam). Spec Kit: hooks de extensão before_/after_ expostos ao agente pelos templates de comando | documentação oficial de cada produto (ver referências) |
| Efeito do harness com o mesmo modelo | 13 a 16 pontos percentuais em Terminal-Bench 2.x | fonte secundária (codex.danielvaughan.com); NÃO VERIFICADO em fonte primária |
| Economia estimada de instruções por lane | Standard ~14,6k tokens (-62%); Direct ~2 a 3k tokens (-93%), contra ~38,8k hoje | HIPÓTESE: bytes/4 supondo carga sob demanda por fase (specify+plan+tasks+implement ≈ 50,3 KB + router de ~2k tokens) |

### Scorecard

| Dimensão | Nota | Máximo | Justificativa |
|---|---:|---:|---|
| Disciplina anti-alucinação / proveniência | 4 | 5 | Contrato de primeira classe (EXPLICIT/INFERRED/DISCOVERED/UNRESOLVED) sem equivalente nos concorrentes pesquisados; perde um ponto por não ser verificado automaticamente. |
| Core determinístico e testabilidade | 4 | 5 | stdlib, 631 testes sem LLM, JSON no stdout, ~0,1 s por chamada; mas é o LLM quem precisa lembrar de chamá-lo. |
| Cerimônia adaptativa (lanes) | 2 | 5 | Tiers XS–XL com pisos de sensibilidade e calibração são bem desenhados, mas só o clarify pode ser pulado; o mercado encurta o pipeline. |
| Enforcement no host (hooks e permissões) | 1 | 5 | 0 hooks do host; preflight e hooks internos dependem de chamada voluntária. |
| Isolamento de contexto (subagentes) | 1 | 5 | 12 papéis como playbooks num único contexto; peer review sem contexto novo. |
| Evals de agente | 1 | 5 | 5 checagens unitárias fixas; sem tarefas, graders nem baseline. |
| Telemetria de custo e qualidade | 1,5 | 5 | Export OTLP e schema existem, mas 9/9 rodadas estão com 0 tokens e não há ingestão do host. |
| Economia de contexto | 1,5 | 5 | ~38,8k tokens de instruções por ciclo, PROTOCOL de 837 linhas lido inteiro, 76 tools MCP (~8,7k tokens), referências órfãs. |
| Distribuição e padrões abertos | 2 | 5 | Tem MCP e entrypoints para 30+ agentes, mas sem plugin/marketplace, sem SKILL.md conforme agentskills.io como porta principal e com adapters feitos à mão. |
| Runtime headless multi-host | 2 | 5 | O guarded mode tem contratos de fase úteis, mas só roda com OpenCode; não usa claude -p, Agent SDK, codex exec nem o engine de workflows do Spec Kit. |

### Achados

#### M1 — O mercado usa lanes que encurtam o pipeline; os tiers XS–XL do Spec Master só mudam a profundidade da revisão (impacto: alto)

Os concorrentes decidem quanto processo aplicar antes de gerar artefatos:
- Kiro: chat/vibe, Quick Spec (os 3 artefatos numa passada, sem gates), Feature Spec (requirements-first ou design-first) e Bugfix Spec.
- BMAD v6: Quick Flow (só tech-spec, 1 a 15 stories), BMad Method e Enterprise, com detecção de escopo e escalonamento que reaproveita o trabalho feito.
- OpenSpec OPSX: 'actions, not phases', /opsx:ff e delta specs.
- GSD: /gsd-quick (pesquisa e verificação opcionais) e perfis yolo/budget/quality.
- Factory: Normal Mode vs Spec Mode.
- Claude Code: 'If you could describe the diff in one sentence, skip the plan'.
No Spec Master, até um XS roda constitution → specify → plan → tasks → analyze → implement → validate; só o clarify pode ser pulado. Além disso, o tier de escopo usa sinais (critérios, tasks, arquivos) que só existem depois de specify/tasks, ou seja, paga-se a cerimônia para descobrir que ela não era necessária.

**Evidência:** spec-master/PROTOCOL.md:459 ('Only `clarify` may be skipped... The state machine refuses SKIPPED for every other phase'); kiro.dev/docs/specs/best-practices; wiki BMAD sobre scale-adaptive planning; OpenSpec docs/opsx.md; GSD USER-GUIDE; code.claude.com/docs/en/best-practices

#### M2 — O ciclo Spec Kit completo é overengineering comprovado para mudanças pequenas e médias, e o dogfood confirma (impacto: alto)

Evidência externa:
- Scott Logic: 2 features com Spec Kit custaram ~57 min de agente + ~5,5 h de revisão e 4.839 linhas de markdown para ~990 LOC. O prompting iterativo levou 8 min + ~24 min humanos.
- Böckeler: o fluxo em bug pequeno foi 'a sledgehammer to crack a nut'.
- Spec Kit Agents (arXiv 2604.05278): grounding e validação por fase dão +0,15/5 (+3%) de qualidade, com overhead. O próprio paper indica o uso para tarefas de risco maior.
- arXiv 2609.20804: para modelos fortes, planejar funciona como economia de custo, com pouca mudança de acurácia. Um plano leve vale a pena; artefatos pesados, não.

Evidência no repo:
- O commit 06dcef0 gerou 1.729 linhas de specs + 2.020 de churn de estado para 327 linhas de produção.
- O mantenedor pausou o ciclo para 13 dos 16 itens do roadmap.
- 7 das 10 features estão COMPLETED com as fases todas PENDING. O state.json virou um registro manual paralelo ao git; o OpenSpec, ao contrário, deriva o estado dos artefatos, sem arquivo de estado separado.

**Evidência:** git show --numstat 06dcef0; .spec-master/state.json; docs/market-benchmark-roadmap.md:176 ('não usar o Spec Master para evoluir o Spec Master'); blog.scottlogic.com (2025-11-26); arXiv 2604.05278; arXiv 2609.20804

#### M3 — O mercado usa hooks bloqueantes do host; o Spec Master depende de o agente chamar o CLI (impacto: alto)

Primitivas de enforcement no mercado:
- Claude Code: 33 eventos e 5 tipos de handler (command, http, mcp_tool, prompt, agent). Bloqueia por exit 2 ou permissionDecision. Hooks podem vir de plugin, do frontmatter de uma skill ou de um subagente. A doc diz: 'Unlike CLAUDE.md instructions which are advisory, hooks are deterministic'.
- Codex: 12 eventos com deny e trust por hash.
- Kiro: PreToolUse, PromptSubmit e PreTaskExecution bloqueiam.
- Cline e Factory também têm hooks.
- Survey da marmelab: só 4,4% das regras de segurança escritas em CLAUDE.md têm enforcement real.

No Spec Master, 'policy preflight' e 'hooks emit' são chamadas voluntárias do agente. tool_policy.py não aceita entrada de hook, e não há settings/hooks.json/plugin.

Os hooks de extensão do próprio Spec Kit também são expostos ao agente pelos templates de comando (marcadores EXECUTE_COMMAND), ou seja, são mediados por prompt. Existe um espaço claro para o Spec Master ser a camada que torna essas regras obrigatórias.

**Evidência:** PROTOCOL.md:592 ('call `policy preflight`... execute only commands classified as allowed'); find sem .claude/settings.json, hooks.json ou plugin.json; grep em tool_policy.py; code.claude.com/docs/en/hooks; learn.chatgpt.com/docs/hooks; kiro.dev/docs/hooks; marmelab 2026-09-24; github.github.io/spec-kit/reference/extensions.html

#### M4 — Isolamento de contexto por subagente é padrão; o Team Mode é persona em prompt num único contexto (impacto: alto)

Como o mercado isola contexto:
- Anthropic: subagentes devolvem resumos de 1.000 a 2.000 tokens; o harness de longa duração separa initializer e coding agent, com uma feature por sessão.
- GSD: executor com contexto novo de 200K tokens por plano.
- 12-factor #10: 'Small, Focused Agents'.
- Roo: o Orchestrator roda subtarefas em contexto próprio, e os modos restringem edição por fileRegex.
- Claude Code: subagentes com tools, model, permissionMode, isolation: worktree, skills, hooks e memory; agent teams com hooks TaskCompleted e TeammateIdle.

No Spec Master, os 12 papéis são playbooks (45 KB) que o mesmo agente lê. O PROTOCOL não menciona subagentes. O peer review 'por outro dev agent' não tem mecanismo de contexto isolado, então o revisor herda o viés do autor.
A doc do Claude Code alerta que um revisor instruído a achar lacunas 'leads to over-engineering' e que agent teams consomem 'significantly more tokens'.

**Evidência:** PROTOCOL.md:305-323 (dev agents e peer review); ls spec-master/knowledge/playbooks (13 arquivos); grep 'subagent' em PROTOCOL.md (0 ocorrências); code.claude.com/docs/en/sub-agents; /agent-teams.md; /best-practices; anthropic.com/engineering/effective-context-engineering-for-ai-agents; github.com/humanlayer/12-factor-agents

#### M5 — Custo de contexto fixo alto e sem progressive disclosure (impacto: alto)

O que o agente carrega por ciclo:
- ~15,9k tokens de instruções próprias. O PROTOCOL tem 837 linhas e deve ser lido 'integralmente'.
- ~22,9k tokens das 7 skills speckit, somando ~38,8k tokens antes de qualquer contexto do projeto.
- O MCP expõe 76 tools, ~8,7k tokens de schema.

Referências de mercado:
- SKILL.md com menos de 500 linhas e referências carregadas sob demanda (Claude Code, Agent Skills).
- AGENTS.md de ~100 linhas funcionando como mapa (OpenAI).
- O marketplace do Claude Code destaca plugins cujo custo fixo por turno passa de 2.000 tokens.
- Gloaguen et al.: arquivos de contexto não melhoram a taxa de sucesso e aumentam o custo em mais de 20%.
- Vercel: remover 80% das tools levou o sucesso de 80% para 100%, com -37% de tokens e 3,5x mais velocidade.

Além disso, 11 citações 'CLAUDE.md §N' apontam para um arquivo que nunca existiu: é contexto que o agente não consegue resolver.

**Evidência:** wc -c/-l em PROTOCOL.md e .claude/skills/speckit-*/SKILL.md; spec_master_mcp.py --list-tools (76 tools); .claude/commands/spec-master.md:12; PROTOCOL.md:84 ('CLAUDE.md §5'); git log --all -- CLAUDE.md vazio; code.claude.com/docs/en/plugins/measure; arXiv 2602.11988; vercel.com/blog/we-removed-80-percent-of-our-agents-tools

#### M6 — O LLM conduz a orquestração turno a turno; o mercado usa script, workflow ou hook (impacto: medio)

O PROTOCOL cita 64 comandos distintos do CLI, 31 só no Step 6 (state transition, risk classify, metrics record-round, traceability add, hooks emit...). Cada um é um round-trip do modelo que reenvia o contexto inteiro. O CLI em si custa ~0,1 s por chamada, então o gargalo de performance é token x turno.

Alternativas de mercado:
- Spec Kit ≥ 0.16/1.0: engine de workflows (command, prompt, shell, gate, if/switch, while, fan-out/fan-in), com estado e resume em .specify/workflows/runs/ e integração/modelo por step.
- Claude Code: dynamic workflows (agent(), pipeline(), parallel(), schema de saída, resume, tokens por fase, distribuíveis em plugin).
- 12-factor #8: 'Own your control flow'.

No Spec Master, só o guarded mode controla o loop, e ele só suporta OpenCode.

**Evidência:** regex sobre PROTOCOL.md (64/31/51); bash time em cli.py state show (~0,1 s); README.md:431 ('Suporta apenas a integração OpenCode'); .specify/workflows/speckit/workflow.yml; github.github.io/spec-kit/reference/workflows.html; code.claude.com/docs/en/workflows.md

#### M7 — Os 'harness evals' do projeto não são evals de agente; o mercado mede ganho contra um baseline (impacto: alto)

evals.py tem 50 linhas e testa DAG, preflight, budget e graph com entradas fixas. Não há tarefa, trial, transcript, grader nem baseline.

No mercado:
- Anthropic ('Demystifying evals'): prefere checagens de estado e outcome.
- `claude plugin eval`: roda cada caso 3 vezes com e sem o plugin, reporta Δ e custo e gateia o CI. Graders: regex, tool_used, tool_order, file_exists, llm e baseline.
- Tessl: pivotou de 'spec-as-source' para 'agent enablement platform', com before/after evals a cada mudança. O benchmark interno (roadmap:211) ainda a trata como spec-as-source.

Por isso, afirmações como 'Readiness: 100% for Hosted/Hybrid Harness' não têm lastro em resultado. Também não há evidência de que Team Mode, analyze-repair ou os tiers melhorem o resultado em relação ao baseline.

**Evidência:** spec-master/lib/evals.py; .spec-master/reports/harness-100-upgrade.md; docs/market-benchmark-roadmap.md:211; code.claude.com/docs/en/plugin-evals; tessl.io; anthropic.com/engineering/demystifying-evals-for-ai-agents (verificado por resumos e anúncio)

#### M8 — Métricas são auto-relatadas e zeradas, embora o host já exponha tokens e custo atribuídos (impacto: medio)

As 9 rodadas têm tokens = 0, e o PROTOCOL manda gravar 0. O export OTLP serializa esses zeros, e a calibração de tiers cai para duração ou contagem de rodadas.

O que o host já oferece:
- Claude Code exporta claude_code.token.usage e claude_code.cost.usage com agent.name, skill.name, plugin.name e query_source.
- `claude -p --output-format json` devolve total_cost_usd.
- Todo hook recebe session_id e transcript_path.
- As OTel GenAI semconv definem spans invoke_agent/execute_tool e atributos gen_ai.usage.*.

**Evidência:** parse de .spec-master/metrics/rounds.json (9/9 zero); PROTOCOL.md:342; spec-master/lib/metrics_export.py:15-18,378-413; code.claude.com/docs/en/monitoring-usage; /headless; semantic-conventions-genai gen-ai-agent-spans.md

#### M9 — A distribuição ficou fora dos padrões que o mercado consolidou (impacto: medio)

Padrões de 2026:
- Agent Skills (agentskills.io) é suportado por Claude Code, Codex, Copilot/VS Code, Cursor, Gemini CLI, OpenCode, Kiro, Roo, Factory, Amp, Goose e outros.
- A AAIF (Linux Foundation, dez/2025) abriga MCP e AGENTS.md.
- Plugins do Claude Code (skills, agents, hooks, MCP, workflows) têm marketplace, escopos, estimativa de context cost e evals; o Codex tem plugins com hooks.
- O BMAD já instala via `npx skills add` e pelos marketplaces do Claude Code e do Codex.
- Um estudo com 2.853 repositórios achou que context files dominam e que Skills e Subagents são pouco usados, o que abre espaço para quem entregar isso pronto.

O Spec Master usa init.sh + 4 adapters manuais + 30+ entrypoints gerados (adapters_gen.py, 440 linhas) que só apontam para o protocolo. Não há plugin.json nem marketplace.

**Evidência:** find sem .claude-plugin; spec-master/lib/adapters_gen.py; README.md:436-485; agentskills.io; linuxfoundation.org (AAIF); code.claude.com/docs/en/plugins; learn.chatgpt.com/docs/build-skills; github.com/bmad-code-org/BMAD-METHOD; arXiv 2602.14690

#### M10 — O upstream e os hosts absorveram parte do valor de orquestração, e o repo está defasado (impacto: medio)

Situação do Spec Kit:
- O repo tem instalada a 0.16.4; o upstream está na 1.0.12.
- O Spec Kit 1.0 tem 5 primitivas (extensions, presets, integrations, workflows, steps), mais bundles e catálogos: 157 extensões e 33 presets.
- Trouxe o comando converge e processos avulsos de bug e assess, e o taskstoissues está saindo do core.
- O workflow 'speckit' instalado já encadeia specify → gate → plan → gate → tasks → implement, com resume.

O Agent OS v3 (jan/2026) removeu seus próprios workflows de spec e implementação: 'It doesn't make sense to reinvent these core functions, which are much better handled by the core tools'.

Por isso, o posicionamento de 'orquestrador acima do Spec Kit' está se esvaziando. O que continua diferenciado é o que é harness.

**Evidência:** .specify/init-options.json:8; .specify/workflows/speckit/workflow.yml; github.com/github/spec-kit/releases; manorrock.com (Spec Kit 1.0.0, 2026-08-21); rywalker.com/research/github-spec-kit; github.com/buildermethods/agent-os/discussions/310

#### M11 — Diferenciais reais do Spec Master que valem preservar (impacto: medio)

1. Proveniência EXPLICIT/INFERRED/DISCOVERED_FROM_CODEBASE/UNRESOLVED por requisito. Nenhum concorrente pesquisado (Spec Kit, Kiro, OpenSpec, BMAD, GSD) tem isso como contrato de primeira classe; o Spec Kit só tem [NEEDS CLARIFICATION], análogo parcial de UNRESOLVED. O paper Spec Kit Agents mostra que grounding no repositório reduz APIs alucinadas.
2. Core determinístico em stdlib, com 631 testes sem LLM e contratos JSON. Está alinhado ao 12-factor (#5, #6) e ao achado de que runtimes de produção usam 'hand-rolled async loops and deterministic retrieval'.
3. Rastreabilidade por critério de aceite, com store por feature.
4. Risco por escopo x sensibilidade, com pisos (auth/payment/secrets → L) e calibração. É mais sofisticado que a heurística do BMAD por número de stories.
5. Quality gates só a partir de evidência do repo, como o auto-lint/test do Aider.

Fraqueza comum a todos: são sensores que dependem de o agente chamar o CLI.

**Evidência:** README.md:82-86 e 128-133; PROTOCOL.md:84-99 e 426-446; 631 test functions em spec-master/tests; arXiv 2604.05278; arXiv 2609.00006; aider.chat/docs/usage/lint-test.html

#### M12 — O harness faz tanta diferença quanto o modelo; o núcleo do produto deve ser o loop de feedback, não a prosa (impacto: medio)

Evidências:
- Böckeler (abr/2026): 'Agent = Model + Harness'. Guias (feedforward) sem sensores (feedback) produzem um agente 'that encodes rules but never finds out whether they worked'.
- OpenAI, segundo fonte secundária: regras 'not documented. Enforced' via linters e testes estruturais com mensagem de remediação; AGENTS.md como mapa; 'Ralph Wiggum loop'.
- Anthropic (long-running): feature list em JSON, porque o modelo tende menos a sobrescrever JSON do que Markdown; um feature por vez; testes como gate contra 'premature victory'.
- arXiv 2603.25723: harnesses em linguagem natural atingem resultados comparáveis ao código quando são curtos.

O Spec Master tem muita prosa (feedforward) e poucos sensores automáticos: o validate depende do agente.

**Evidência:** martinfowler.com/articles/harness-engineering.html; anthropic.com/engineering/effective-harnesses-for-long-running-agents; alexlavaee.me/blog/openai-agent-first-codebase-learnings (secundária; openai.com retornou 403); arXiv 2603.25723

### Recomendações

#### R1 — Lanes de processo com roteamento antes de gerar qualquer artefato (P0 · esforço M)

Substituir o tier que só muda a revisão por quatro lanes que mudam o próprio pipeline:
- Direct: diff descritível em uma frase. Faz implement + gates + registro mínimo de rastreabilidade.
- Delta/Quick: proposal + delta spec (ADDED/MODIFIED/REMOVED) + tasks numa passada, no estilo OpenSpec ff, Kiro Quick Spec e BMAD Quick Flow.
- Standard: specify → plan → tasks → implement, com analyze leve.
- Full/Governed: ciclo Spec Kit completo com clarify, analyze profundo, ADR e revisão isolada, só para L/XL ou quando um piso de sensibilidade é atingido.

Como rotear:
- Classificar no intake com sinais baratos: paths e diff via git, pisos de sensibilidade por path, override só para cima.
- Escalar automaticamente de lane em pre_implement, reaproveitando os artefatos já feitos.
- Liberar SKIPPED para plan/tasks/analyze nas lanes baixas.
- Registrar entregas das lanes leves como entregas normais, sem o rótulo 'fora do Spec Master'.

**Ganho esperado:** Em mudanças pequenas e médias, ordem de grandeza de 7x menos tempo de agente e 14x menos tempo humano (referência Scott Logic). Elimina a proporção de ~5:1 de markdown por código observada no dogfood. Instruções caem de ~38,8k para ~2 a 15k tokens conforme a lane (estimativa). Permite usar o próprio Spec Master para evoluir o Spec Master.

**Riscos:** Classificar risco abaixo do real. Mitigação: pisos de sensibilidade por path/diff, reclassificação obrigatória em pre_implement e evals por lane (R4).

#### R2 — Enforcement via hooks do host, gerados a partir do hooks.py atual (P0 · esforço M)

Gerar hooks.json para o plugin/settings do Claude Code, para o Codex e para o Kiro (.kiro/hooks):
- PreToolUse(Bash): tool_policy vira hook que lê JSON do stdin, emite permissionDecision deny/ask e usa exit 2.
- PostToolUse(Write|Edit em specs/**): validador de proveniência/EARS e atualização automática de traceability/state.
- Stop/SubagentStop/TaskCompleted: gates bloqueantes (testes, cobertura de critérios de aceite, UNRESOLVED=0 nas lanes Standard+).
- SessionStart: injeta um resumo de state/resume no lugar da leitura integral do protocolo.
- PreCompact: preserva o estado.
Hosts sem hooks rodam num modo 'advisory' explícito.

**Ganho esperado:** Tira do loop do LLM a maior parte das 31 chamadas de bookkeeping por feature (menos turnos e menos tokens). Regras críticas passam a ser garantidas, e não apenas pedidas (o mercado tem 4,4% de enforcement em regras escritas).

**Riscos:** Loops de Stop, que exigem teto e checagem de stop_hook_active; latência dos hooks; esquemas diferentes entre hosts. Mitigação: um único core Python com adapters finos de I/O.

#### R3 — Distribuir como plugin + Agent Skill padrão + AGENTS.md curto, com MCP enxuto (P0 · esforço M)

- Criar .claude-plugin/plugin.json (skills, agents, hooks, workflows, MCP) num marketplace próprio, mais um plugin Codex equivalente.
- Usar um SKILL.md conforme agentskills.io como porta universal e um AGENTS.md de ~100 linhas como mapa.
- Aposentar a maior parte de adapters_gen.py e do init.sh.
- Metas: custo fixo menor que 2k tokens (medido com `claude plugin details`) e MCP reduzido de 76 para 5 a 8 tools coarse-grained (por exemplo next_step, record, gate_check, trace, status), com readOnlyHint.

**Ganho esperado:** Instalação com um comando, versionamento e atualização via marketplace, telemetria por plugin, cerca de 8k tokens a menos por sessão em clientes MCP sem tool search, e menos código de manutenção.

**Riscos:** Formatos de plugin ainda evoluem. Manter um fallback advisory para a longa cauda de agentes.

#### R4 — Evals de agente com baseline, por lane e por componente (P0 · esforço L)

Montar uma suíte evals/ executável via `claude plugin eval` e via um runner headless para Codex/OpenCode.
- Casos: XS bugfix, S feature brownfield, M feature e L feature com auth.
- Graders de resultado: testes passam, arquivos esperados, tool_order (gates rodaram antes do fim), cobertura de rastreabilidade, 0 requisitos sem fonte.
- Arms: sem Spec Master, lane leve, lane completa, Team Mode ligado/desligado, analyze-repair ligado/desligado.
- Métricas: taxa de sucesso, tokens, custo, tempo total e linhas de artefato.
Gatear o CI e alimentar a calibração com esses dados.

**Ganho esperado:** Decisões de cerimônia baseadas em evidência, com prova do valor de peer review, analyze-repair e dos 12 papéis. Detecção de regressão a cada novo modelo. Substitui o '100% readiness' por números de resultado.

**Riscos:** Custo (3 trials x vários arms) e instabilidade de juízes LLM. Preferir graders computacionais e rodar a suíte completa só por release.

#### R5 — Telemetria real do host em vez de auto-relato (P1 · esforço S)

- Capturar tokens e custo do host: OTel claude_code.token.usage/cost.usage com skill.name e agent.name; total_cost_usd de `claude -p`/Agent SDK; transcript_path lido por hooks SubagentStop/Stop.
- Gravar as rodadas automaticamente.
- Alinhar o export às OTel GenAI semconv (invoke_agent, execute_tool, gen_ai.usage.*) e manter o schema próprio só como visão.

**Ganho esperado:** A calibração de tiers passa a ter sinal (hoje 9/9 rodadas com 0 tokens), com custo por fase, lane e papel. É a base para medir o ganho de R1 e R6.

**Riscos:** Privacidade: não logar prompts por padrão. A granularidade varia entre hosts.

#### R6 — Isolar contexto por fase e papel com subagentes nativos (P1 · esforço M)

- Definir em .claude/agents/ (e equivalentes no Codex): discovery/researcher read-only; spec-writer; implementer com isolation: worktree; verifier/reviewer com contexto novo, vendo só o diff e os critérios, instruído a reportar apenas lacunas de correção ou requisito; security sob demanda.
- Cada subagente devolve um resumo estruturado de até 2k tokens, com schema.
- Reduzir o Team Mode de 12 papéis ativos para 3 ou 4 papéis executáveis. Os demais playbooks viram skills carregadas sob demanda (paths/preload).

**Ganho esperado:** Contexto principal abaixo de ~40% de ocupação (a 'dumb zone'), revisão realmente independente e paralelismo com worktrees. Menos tokens do que simular 12 personas no mesmo contexto.

**Riscos:** O total de tokens pode subir se forem usados agent teams. Preferir subagentes e validar com R4.

#### R7 — Runtime determinístico multi-host no lugar do guarded mode só com OpenCode (P1 · esforço L)

- Claude Code: um dynamic workflow .claude/workflows/spec-master.js distribuído no plugin (agent() por fase com schema, resume nativo, tokens por fase).
- CI/headless: um runner fino sobre `claude -p --bare --json-schema`, o Claude Agent SDK, `codex exec` e `specify workflow run` (Spec Kit ≥ 1.0, com integração e modelo por step).
- GitHub: gh-aw com safe outputs.
controller.py e phase_contracts passam a ser validadores de artefato chamados por hooks e steps.

**Ganho esperado:** Controle do loop ('own your control flow') sem depender de o LLM seguir 837 linhas; resume confiável; reuso do engine upstream; suporte a vários modelos, inclusive locais.

**Riscos:** As APIs de workflow ainda mudam, e haverá dois caminhos (interativo e headless) para manter. Isolar com contract tests.

#### R8 — Context engineering do protocolo: router curto + referências sob demanda (P1 · esforço S)

- Quebrar o PROTOCOL.md (837 linhas) num SKILL.md router de ~150 linhas, com teto de 500, mais referências por lane/fase/papel carregadas just-in-time.
- Mover as regras invariantes para hooks (R2) e apagá-las da prosa.
- Corrigir as 11 citações a 'CLAUDE.md §N' e o README.md:495.
- Tirar dos playbooks defaults de tecnologia sem evidência (por exemplo WireMock/Cypress em PROTOCOL.md:326), coerente com a regra de nada hardcoded.

**Ganho esperado:** Menos de 10k tokens de instruções na lane Standard, contra ~38,8k no ciclo completo hoje, menos 'rules lost in noise' e menor custo por turno.

**Riscos:** Regressão de comportamento ao cortar texto. Validar com as evals (R4) antes e depois.

#### R9 — Spec Kit como 'process pack' plugável e estado derivado de artefatos (P2 · esforço M)

- Atualizar o Spec Kit de 0.16.4 para 1.0.x.
- Empacotar a integração como bundle/preset/extension do Spec Kit (hooks before_/after_, converge, presets bug/assess) e usá-la na lane Full.
- Oferecer packs alternativos: delta no estilo OpenSpec e direto.
- Derivar o estado de artefatos + git, como no OpenSpec, com o state.json atuando só como cache.

**Ganho esperado:** Menos código próprio duplicando o upstream; acesso a 157 extensões e 33 presets; fim da divergência entre estado e realidade (as 7 features PENDING/COMPLETED). O Spec Master fica com o que é harness.

**Riscos:** Churn de API upstream (55+ releases no ano). Isolar num adapter com testes de contrato.

#### R10 — Provenance Guard: transformar o diferencial anti-alucinação em sensor automático (P2 · esforço S)

Criar um validador determinístico de proveniência:
- todo requisito ou critério precisa de tag;
- DISCOVERED_FROM_CODEBASE exige evidência file:line verificável;
- INFERRED não vira critério de aceite sem revisão;
- UNRESOLVED bloqueia implement nas lanes Standard+.
Ele roda em hook PostToolUse e como gate de Stop, com a métrica '% de requisitos com evidência verificada'. Publicar também como skill/extension independente para usuários de Spec Kit, OpenSpec e Kiro.

**Ganho esperado:** Converte a disciplina de prompt em garantia medível e cria um canal de adoção onde o mercado não tem equivalente.

**Riscos:** Falsos positivos em specs longas e manutenção dos parsers de markdown. Começar só com as tags e as referências file:line.

### Perguntas abertas

- Qual é o host primário: Claude Code, Codex, OpenCode ou um modelo local? Isso define se o plugin, os hooks e os dynamic workflows do Claude Code viram o runtime principal e se a paridade com 30+ agentes pode ficar só em modo advisory.
- O Spec Kit continua dependência obrigatória, ou vira um 'process pack' opcional ao lado de uma lane Delta própria?
- Quais metas de performance por lane serão critério de aceite da reformulação: tokens por feature, tempo total para XS/S, taxa de sucesso contra o baseline sem Spec Master, linhas de artefato por linha de código?
- Existe exigência de compliance ou auditoria que justifique os 12 papéis e todos os artefatos, ou eles podem virar playbooks sob demanda com 3 a 4 papéis executáveis?
- O guarded mode para modelos locais (OpenCode) é requisito estratégico, por exemplo on-premises? Se for, o runner multi-host precisa priorizar OpenCode e codex exec além do Claude Agent SDK.
- Qual política de telemetria é aceitável no ambiente-alvo: só contagens e custo, ou também prompts e conteúdo de tools?
- O time aceita usar as lanes Direct/Delta para evoluir o próprio Spec Master, encerrando a pausa do dogfood?

### Referências

- https://martinfowler.com/articles/harness-engineering.html
- https://marmelab.com/blog/2026/09/24/the-state-of-ai-harness-engineering-2026.html
- https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents
- https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- https://www.anthropic.com/engineering/building-effective-agents
- https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents (conhecido por resumos e pelo anúncio no X; conteúdo não lido diretamente)
- https://openai.com/index/harness-engineering/ (retornou 403; conteúdo via https://alexlavaee.me/blog/openai-agent-first-codebase-learnings/, fonte secundária)
- https://arxiv.org/abs/2609.20804
- https://arxiv.org/abs/2609.00006
- https://arxiv.org/abs/2602.14690
- https://arxiv.org/abs/2602.11988
- https://arxiv.org/abs/2604.05278
- https://arxiv.org/abs/2603.25723
- https://blog.scottlogic.com/2025/11/26/putting-spec-kit-through-its-paces-radical-idea-or-reinvented-waterfall.html
- https://github.com/github/spec-kit/releases
- https://github.github.io/spec-kit/index.html
- https://github.github.io/spec-kit/reference/workflows.html
- https://github.github.io/spec-kit/reference/extensions.html
- https://github.github.io/spec-kit/reference/presets.html
- https://github.github.com/spec-kit/reference/agentic-sdd.html
- https://www.manorrock.com/blog/2026/08/21/spec_kit_turns_one.html
- https://newreleases.io/project/github/github/spec-kit/release/v1.0.0
- https://rywalker.com/research/github-spec-kit (secundária)
- https://github.com/github/spec-kit/issues/4746
- https://kiro.dev/docs/specs/
- https://kiro.dev/docs/specs/best-practices/
- https://kiro.dev/docs/hooks/
- https://kiro.dev/docs/steering/
- https://github.com/Fission-AI/OpenSpec
- https://github.com/Fission-AI/OpenSpec/blob/main/docs/opsx.md
- https://github.com/bmad-code-org/BMAD-METHOD
- https://mintlify.wiki/bmad-code-org/BMAD-METHOD/concepts/scale-adaptive-planning
- https://tessl.io/
- https://github.com/buildermethods/agent-os/discussions/310
- https://github.com/humanlayer/12-factor-agents
- https://www.humanlayer.dev/blog/advanced-context-engineering (conhecido via resultados de busca)
- https://github.com/gsd-build/get-shit-done/blob/main/docs/USER-GUIDE.md
- https://github.com/Priivacy-ai/spec-kit (Spec Kitty; via resultados de busca)
- https://code.claude.com/docs/en/hooks
- https://code.claude.com/docs/en/sub-agents
- https://code.claude.com/docs/en/skills
- https://code.claude.com/docs/en/plugins
- https://code.claude.com/docs/en/plugin-evals
- https://code.claude.com/docs/en/plugins/measure
- https://code.claude.com/docs/en/monitoring-usage
- https://code.claude.com/docs/en/headless
- https://code.claude.com/docs/en/workflows.md
- https://code.claude.com/docs/en/agent-teams.md
- https://code.claude.com/docs/en/best-practices
- https://agentskills.io
- https://www.linuxfoundation.org/press/linux-foundation-announces-the-formation-of-the-agentic-ai-foundation
- https://learn.chatgpt.com/docs/build-skills (Codex skills)
- https://learn.chatgpt.com/docs/hooks (Codex hooks)
- https://developers.openai.com/codex/plugins (via resultados de busca)
- https://docs.cline.bot/features/hooks
- https://roocodeinc.github.io/Roo-Code/features/custom-modes
- https://docs.factory.ai/autonomy-and-safety/specification-mode
- https://docs.factory.ai/cli/user-guides/auto-run (via resultados de busca)
- https://ampcode.com/manual (via fontes secundárias e agentskills.io)
- https://aider.chat/docs/usage/lint-test.html
- https://aider.chat/2024/09/26/architect.html
- https://vercel.com/blog/we-removed-80-percent-of-our-agents-tools
- https://codex.danielvaughan.com/2026/04/19/the-harness-effect-same-model-different-tool-different-score/ (secundária, NÃO VERIFICADO)
- https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-agent-spans.md
- https://github.blog/changelog/2026-02-13-github-agentic-workflows-are-now-in-technical-preview/
- https://github.com/github/gh-aw/issues/5769
- Evidência local: spec-master/PROTOCOL.md, .claude/commands/spec-master.md, .specify/init-options.json, .specify/workflows/speckit/workflow.yml, .spec-master/state.json, .spec-master/metrics/rounds.json, spec-master/lib/evals.py, spec-master/lib/tool_policy.py, spec-master/mcp/spec_master_mcp.py, docs/market-benchmark-roadmap.md, .spec-master/reports/harness-100-upgrade.md; saída do --list-tools em <scratch>/mercado/tools.txt
