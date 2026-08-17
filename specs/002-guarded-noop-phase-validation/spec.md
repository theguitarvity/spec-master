# Feature Specification: Validar fases protegidas sem alteração de artefato

**Feature ID**: `guarded-noop-phase-validation`  
**Status**: Draft  
**Source**: execução real do case `qwen-greeting-api` em modo `guarded`

## 1. Problema

O controlador protegido atualmente exige que pelo menos um artefato obrigatório seja modificado em toda fase. Essa regra evita falso sucesso quando o agente retorna código zero sem produzir resultado, mas é incorreta para fases cujo resultado válido pode ser concluir que nenhuma mudança é necessária.

No case `qwen-greeting-api`:

1. `constitution` passou após produzir uma constituição válida;
2. `specify` passou após produzir `spec.md` e `.specify/feature.json`;
3. a especificação já não continha ambiguidades relevantes;
4. `clarify` terminou sem modificar `spec.md`;
5. o controlador classificou a tentativa como `missing_artifact`, apesar de o artefato existir, estar preenchido e não conter marcadores de esclarecimento;
6. a fase foi marcada como `BLOCKED` depois de esgotar as tentativas.

Portanto, o controlador confunde duas situações diferentes:

- **falso sucesso**: o agente não produziu nem validou o resultado exigido;
- **no-op válido**: o artefato anterior já satisfaz o contrato e a fase conclui legitimamente que não há correção a aplicar.

## 2. Objetivo

Permitir que fases classificadas como `inspect-or-update` sejam aprovadas sem alteração de arquivo quando seus artefatos preexistentes satisfizerem validações determinísticas específicas da fase.

A correção deve preservar as garantias atuais:

- arquivos obrigatórios precisam existir e não podem estar vazios;
- placeholders obrigatórios continuam proibidos;
- escrita fora da allowlist continua bloqueante;
- chamadas de ferramenta simuladas continuam bloqueantes;
- timeout continua bloqueante;
- fases produtoras continuam obrigadas a criar ou modificar seus artefatos;
- ausência de alteração nunca deve ser aceita apenas porque o processo retornou código zero.

## 3. Escopo

### Incluído

- classificar fases por política de resultado;
- permitir `no-op` determinístico em `clarify`;
- definir comportamento para `analyze` e outras fases potencialmente sem alteração;
- registrar explicitamente `outcome: no_changes_required`;
- diferenciar `missing_artifact`, `unchanged_artifact` e `valid_noop`;
- corrigir retomada de workflows bloqueados incorretamente por esse caso;
- testes unitários e de integração com agente falso;
- teste de regressão baseado no case `qwen-greeting-api`.

### Fora do escopo

- confiar irrestritamente na resposta textual do modelo;
- aprovar automaticamente ambiguidades de produto;
- alterar comandos do GitHub Spec Kit;
- remover allowlists ou snapshots;
- considerar timeout como no-op válido;
- reavaliar semanticamente toda a especificação usando outro LLM;
- mudar a política de tentativas global.

## 4. Classificação das fases

Cada fase deve possuir uma política explícita em `phase_contracts.py`.

### 4.1 `produce-or-update`

Exige que pelo menos um artefato obrigatório seja criado ou modificado.

Fases iniciais:

```text
constitution
specify
plan
tasks
validate
```

### 4.2 `inspect-or-update`

Pode modificar artefatos ou concluir sem alteração quando as condições determinísticas de no-op forem satisfeitas.

Fases iniciais:

```text
clarify
analyze
```

### 4.3 `execute`

Valida trabalho executado por tarefas e quality gates. A ausência de alteração deve ser avaliada por critérios próprios, não pela regra genérica de arquivo modificado.

Fase inicial:

```text
implement
```

## 5. Regras para `clarify`

Uma tentativa sem alteração em `spec.md` pode resultar em `PASSED` somente quando todas as condições abaixo forem verdadeiras:

1. o processo terminou antes do timeout;
2. o código de saída é zero;
3. não houve escrita proibida;
4. não há ferramenta simulada no transcript;
5. existe exatamente uma feature ativa resolvida por `.specify/feature.json`;
6. o `spec.md` apontado existe e não está vazio;
7. o `spec.md` não contém placeholders estruturais;
8. o `spec.md` não contém `[NEEDS CLARIFICATION` nem marcador equivalente;
9. o transcript contém uma conclusão reconhecível e estruturada de que nenhuma mudança é necessária;
10. o agente não solicitou decisão do usuário;
11. o agente não declarou erro, bloqueio ou informação ausente.

Quando essas condições forem atendidas:

```json
{
  "status": "PASSED",
  "reason": "valid_noop",
  "outcome": "no_changes_required"
}
```

## 6. Resultado estruturado da fase

Para evitar depender de frases livres, o prompt protegido deve exigir que a fase finalize com um bloco estruturado emitido como texto comum:

```json
{
  "phase_result": "no_changes_required",
  "artifact": "specs/001-greeting-api/spec.md",
  "checks": {
    "needs_clarification_markers": 0,
    "user_decision_required": false
  }
}
```

Valores aceitos inicialmente:

```text
artifact_updated
no_changes_required
user_decision_required
failed
```

O controlador deve extrair o último bloco `phase_result` válido do transcript. Texto fora desse bloco não pode promover uma fase.

O bloco estruturado é evidência complementar. Ele nunca substitui as verificações no filesystem.

## 7. Resolução do artefato ativo

O controlador não deve aceitar qualquer `specs/*/spec.md` encontrado por glob quando `.specify/feature.json` estiver presente.

Ordem obrigatória:

1. ler `.specify/feature.json`;
2. validar que `feature_directory` é relativo ao projeto;
3. rejeitar `..`, caminho absoluto e symlink que escape do projeto;
4. resolver `<feature_directory>/spec.md`;
5. validar somente esse arquivo para `clarify`.

Se `.specify/feature.json` estiver ausente ou inválido, `clarify` deve falhar com:

```text
active_feature_unresolved
```

## 8. Regras para `analyze`

`analyze` também pode ser um no-op válido, pois a ausência de inconsistências não exige modificar `spec.md`, `plan.md` ou `tasks.md`.

Para passar sem alteração:

1. `spec.md`, `plan.md` e `tasks.md` da feature ativa existem e estão preenchidos;
2. não possuem placeholders bloqueantes;
3. o processo termina sem timeout e com código zero;
4. não ocorre escrita proibida nem ferramenta simulada;
5. o resultado estruturado informa `no_changes_required`;
6. o resultado informa zero achados `CRITICAL` e `HIGH`;
7. não há `USER_DECISION_REQUIRED` ou `SPEC_DRIFT` aberto.

Exemplo:

```json
{
  "phase_result": "no_changes_required",
  "checks": {
    "critical_findings": 0,
    "high_findings": 0,
    "spec_drift": false,
    "user_decision_required": false
  }
}
```

## 9. Regras para fases produtoras

Esta correção não deve permitir no-op na primeira execução válida de:

- `constitution` quando o arquivo ainda for template;
- `specify` sem criar `spec.md` e `.specify/feature.json`;
- `plan` sem criar `plan.md`;
- `tasks` sem criar `tasks.md`;
- `validate` sem criar os relatórios exigidos.

Se os artefatos já existirem de uma tentativa anterior não promovida, a fase pode passar somente se:

1. a tentativa atual produzir um resultado estruturado `artifact_updated` ou `no_changes_required` permitido pelo contrato específico;
2. o controlador validar integralmente os artefatos existentes;
3. os artefatos estiverem associados ao mesmo fingerprint de contexto;
4. não houver evidência de que vieram de uma tentativa rejeitada por escrita proibida ou escape de diretório.

## 10. Motivos de resultado

Padronizar os motivos retornados por `phase_runner`:

| Motivo | Significado |
|---|---|
| `missing_artifact` | arquivo obrigatório não existe ou está vazio |
| `placeholder_artifact` | arquivo contém placeholder bloqueante |
| `unchanged_artifact` | fase produtora terminou sem mudar artefato |
| `valid_noop` | fase de inspeção validou que nenhuma mudança era necessária |
| `phase_result_missing` | transcript não apresentou resultado estruturado |
| `phase_result_invalid` | resultado estruturado é inválido ou contradiz o filesystem |
| `user_decision_required` | fase depende legitimamente de decisão humana |
| `forbidden_write` | houve escrita fora da allowlist |
| `fake_tool_marker` | ferramenta foi simulada em texto |
| `timeout` | processo excedeu o limite |
| `tool_error` | processo terminou com erro recuperável |

`valid_noop` é sucesso. `user_decision_required` deve pausar, não consumir todas as tentativas automaticamente.

## 11. Retomada após bloqueio incorreto

O comando `resume` deve reavaliar a última tentativa bloqueada quando:

- a versão do contrato de fase mudou;
- o motivo anterior foi `missing_artifact` ou `unchanged_artifact`;
- o artefato obrigatório existe;
- o fingerprint do contexto não mudou.

Se a tentativa antiga satisfizer o novo contrato determinístico, o controlador pode registrar uma nova entrada:

```json
{
  "number": 3,
  "status": "PASSED",
  "reason": "valid_noop",
  "source": "contract_revalidation"
}
```

O histórico anterior não deve ser apagado ou reescrito.

## 12. Estado persistente

Adicionar aos registros de tentativa:

```json
{
  "contract_version": 2,
  "policy": "inspect-or-update",
  "status": "PASSED",
  "reason": "valid_noop",
  "outcome": "no_changes_required",
  "active_artifacts": [
    "specs/001-greeting-api/spec.md"
  ],
  "artifact_hashes_before": {},
  "artifact_hashes_after": {},
  "structured_result": {}
}
```

## 13. Requisitos funcionais

- **NPV-001**: classificar cada fase como `produce-or-update`, `inspect-or-update` ou `execute`.
- **NPV-002**: permitir `clarify` sem alteração quando o spec ativo estiver completo e sem ambiguidades.
- **NPV-003**: permitir `analyze` sem alteração quando não houver achados bloqueantes.
- **NPV-004**: exigir resultado estruturado para promover um no-op.
- **NPV-005**: resolver o artefato pela feature ativa, evitando glob ambíguo.
- **NPV-006**: manter a exigência de alteração para fases produtoras.
- **NPV-007**: distinguir `missing_artifact`, `unchanged_artifact` e `valid_noop`.
- **NPV-008**: pausar imediatamente em `user_decision_required` sem desperdiçar tentativas.
- **NPV-009**: preservar allowlists, proteção de paths e detecção de ferramenta simulada.
- **NPV-010**: permitir revalidação recuperável de uma tentativa bloqueada pelo contrato antigo.
- **NPV-011**: registrar política, versão do contrato, outcome e hashes no estado.
- **NPV-012**: manter compatibilidade com workflows já concluídos.

## 14. Requisitos não funcionais

- Toda validação de no-op deve ser determinística e testável sem LLM.
- O parser do resultado estruturado não deve executar conteúdo do transcript.
- JSON inválido deve ser rejeitado com segurança.
- Paths informados pelo agente devem ser tratados como não confiáveis.
- A mudança não deve reduzir as proteções de fases produtoras.
- Testes não devem depender de OpenCode, Ollama ou rede.

## 15. Cenários de aceite

### Cenário A — Clarify válido sem alteração

Dado um `spec.md` completo e sem marcadores, quando o agente retornar `no_changes_required`, então `clarify` deve passar como `valid_noop` sem modificar o arquivo.

### Cenário B — Clarify falso sucesso

Dado um `spec.md` com `[NEEDS CLARIFICATION]`, quando o agente retornar `no_changes_required`, então a fase deve falhar com `phase_result_invalid`.

### Cenário C — Artefato ausente

Quando não houver feature ativa ou `spec.md`, a fase deve falhar com `active_feature_unresolved` ou `missing_artifact`.

### Cenário D — Escrita indevida

Quando `clarify` criar `coverage_analysis.md` na raiz, a fase deve falhar com `forbidden_write`, mesmo que o spec esteja completo.

### Cenário E — Analyze limpo

Dado spec, plano e tasks válidos, quando `analyze` retornar zero achados bloqueantes sem modificar arquivos, a fase deve passar como `valid_noop`.

### Cenário F — Decisão humana

Quando `clarify` retornar `user_decision_required`, o workflow deve ficar `PAUSED` e apresentar as perguntas, sem iniciar uma segunda tentativa automaticamente.

### Cenário G — Regressão do case real

Ao retomar `qwen-greeting-api`, a segunda tentativa de `clarify` deve ser reavaliada ou repetida sob o novo contrato e não pode ser bloqueada somente porque `spec.md` permaneceu inalterado.

## 16. Testes obrigatórios

### `test_phase_contracts.py`

1. classificação das políticas por fase;
2. resolução segura da feature ativa;
3. rejeição de path absoluto e `..`;
4. detecção de marcador de esclarecimento;
5. spec completo elegível para no-op;
6. analyze com zero achados elegível para no-op.

### `test_phase_runner.py`

1. `clarify` sem alteração e resultado estruturado válido passa;
2. `clarify` sem alteração e sem resultado estruturado falha;
3. resultado estruturado contraditório falha;
4. escrita proibida prevalece sobre no-op válido;
5. timeout nunca vira no-op;
6. `analyze` limpo e sem alteração passa;
7. fase produtora sem alteração continua falhando.

### `test_controller.py`

1. `valid_noop` promove `clarify` para `PASSED`;
2. `user_decision_required` pausa sem consumir nova tentativa;
3. resume revalida tentativa bloqueada pelo contrato anterior;
4. histórico de tentativas permanece preservado;
5. workflow falso completo com no-op em `clarify` e `analyze` chega a `COMPLETED`.

## 17. Estrutura sugerida

```text
spec-master/lib/
├── phase_contracts.py     # política e validadores determinísticos
├── phase_result.py        # parser seguro do resultado estruturado
├── phase_runner.py        # decisão final da tentativa
└── controller.py          # promoção, pausa e retomada
```

## 18. Critérios de aceite

1. A suíte atual continua passando.
2. Novos testes cobrem todos os cenários da seção 16.
3. `clarify` pode passar sem alteração somente sob contrato determinístico válido.
4. `clarify` com ambiguidade não pode ser aprovado por declaração do modelo.
5. `analyze` pode passar sem alteração quando não houver achados bloqueantes.
6. `constitution`, `specify`, `plan`, `tasks` e `validate` continuam protegidos contra falso sucesso.
7. `user_decision_required` pausa o workflow sem esgotar tentativas.
8. O case `qwen-greeting-api` consegue sair do bloqueio de `clarify` sem edição artificial no spec.
9. O relatório final diferencia `artifact_updated` de `no_changes_required`.

## 19. Definição de pronto

A correção estará concluída quando as fases de inspeção aceitarem no-op válido sem enfraquecer os gates de filesystem, os motivos de resultado estiverem padronizados, a retomada do case real funcionar e todos os testes determinísticos passarem.
