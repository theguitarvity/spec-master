# Especificação: execução protegida para modelos menos robustos

## 1. Contexto

O Spec Master atualmente delega ao agente a condução semântica e operacional do fluxo completo:

```text
constitution → specify → clarify → plan → tasks → analyze → implement → validate
```

Modelos robustos conseguem manter a fase atual, chamar ferramentas reais e atualizar o estado. Modelos locais menores ou menos confiáveis podem:

- implementar antes da fase `implement`;
- ignorar comandos `speckit.*`;
- imprimir chamadas de ferramenta como texto;
- reentrar no próprio skill Spec Master;
- criar artefatos em caminhos incorretos;
- declarar sucesso sem produzir o artefato obrigatório;
- perder a fase atual depois de uma compactação;
- parar repetidamente sem progresso.

Precisamos oferecer um controlador determinístico opcional que mantenha o modelo restrito a uma fase por execução.

## 2. Objetivo

Adicionar ao Spec Master três modos de execução:

```text
--mode native
--mode guarded
--mode auto
```

- `native`: preserva o comportamento agentic atual.
- `guarded`: um controlador externo conduz todas as transições e entrega ao modelo somente uma fase por sessão.
- `auto`: começa em `native` e muda irreversivelmente para `guarded` quando detectar comportamento inseguro ou ausência de progresso.

O modo padrão deve ser `auto`.

## 3. Escopo

### Incluído

- seleção explícita ou automática do modo;
- controlador determinístico de fases;
- sessão isolada por fase no OpenCode;
- allowlist de arquivos modificáveis por fase;
- validação de artefatos e conteúdo mínimo;
- detecção de ferramentas simuladas;
- timeout e limite de tentativas;
- retomada idempotente;
- promoção de estado somente após validação;
- relatório das tentativas e da mudança automática de modo;
- configuração de modelo, agente e timeout;
- testes unitários e de integração sem depender de um LLM real.

### Fora do escopo

- escolher ou baixar modelos automaticamente;
- avaliar qualidade literária dos documentos por heurística subjetiva;
- substituir o GitHub Spec Kit;
- executar duas fases simultaneamente;
- corrigir automaticamente decisões de produto ambíguas;
- garantir que qualquer modelo local consiga completar o projeto;
- suportar inicialmente todos os agentes do registro do Spec Kit em modo protegido.

O primeiro incremento protegido deve suportar OpenCode. A arquitetura não deve impedir adaptadores futuros.

## 4. Interface de uso

### Comando principal

```text
/spec-master --mode auto context.md
/spec-master --mode native context.md
/spec-master --mode guarded context.md
```

Quando `--mode` não for informado:

```text
mode = auto
```

### CLI determinística

```bash
python3 spec-master/lib/controller.py run \
  --project . \
  --context context.md \
  --mode guarded \
  --integration opencode \
  --model ollama-neon/qwen3-coder-agent:30b
```

Retomada:

```bash
python3 spec-master/lib/controller.py resume --project .
```

Inspeção:

```bash
python3 spec-master/lib/controller.py status --project .
```

## 5. Fluxo do modo guarded

Para cada fase:

1. Ler `.spec-master/state.json`.
2. Confirmar que a fase anterior está `PASSED`.
3. Criar um snapshot dos arquivos relevantes.
4. Renderizar um prompt curto e específico da fase.
5. Iniciar uma sessão nova, sem histórico de fases anteriores.
6. Desabilitar skills, subagentes e continuação automática nessa sessão.
7. Executar somente o comando `speckit.<fase>` correspondente.
8. Aplicar timeout.
9. Coletar transcript, ferramentas usadas e alterações no filesystem.
10. Validar os artefatos obrigatórios.
11. Se válido, transicionar a fase para `PASSED`.
12. Se inválido, registrar a causa e repetir dentro do limite.
13. Ao esgotar tentativas, marcar a fase como `BLOCKED` e parar.

O controlador nunca deve marcar uma fase como concluída apenas porque o processo do agente retornou código zero.

## 6. Contrato por fase

| Fase | Artefatos obrigatórios | Escritas permitidas |
|---|---|---|
| `constitution` | `.specify/memory/constitution.md` sem placeholders | constituição e sincronizações de templates do Spec Kit |
| `specify` | `.specify/feature.json`, `specs/<feature>/spec.md`, checklist | diretório da nova feature e ponteiro ativo |
| `clarify` | `spec.md` atualizado e sem decisões obrigatórias pendentes | `spec.md` da feature ativa |
| `plan` | `plan.md` e artefatos técnicos exigidos pelo comando | diretório da feature ativa |
| `tasks` | `tasks.md` com tarefas identificáveis | `tasks.md` da feature ativa |
| `analyze` | relatório de análise sem achados bloqueantes | artefatos da feature durante ciclos de reparo |
| `implement` | arquivos previstos pelas tarefas e tarefas atualizadas | projeto, exceto caminhos protegidos |
| `validate` | resultados dos quality gates e rastreabilidade | relatórios e estado do Spec Master |

São sempre protegidos contra escrita pelo modelo:

- motor global do Spec Master;
- credenciais e arquivos fora do projeto;
- `.git/`;
- `.spec-master/state.json`, que somente o controlador pode promover;
- transcripts de tentativas anteriores.

## 7. Validações obrigatórias

### Validações gerais

- processo terminou sem timeout;
- código de saída compatível com sucesso;
- transcript não contém `<function=`, `<tool_call>` ou equivalentes usados como texto;
- nenhuma escrita ocorreu fora da allowlist;
- pelo menos um artefato obrigatório mudou na fase;
- nenhum artefato obrigatório permanece vazio;
- nenhuma variável de template obrigatória permanece, como `[PROJECT_NAME]`;
- a fase não criou código antes de `implement`;
- caminhos modificados permanecem dentro do projeto.

### Validações estruturais

- `specify`: spec possui cenários, requisitos e critérios de sucesso;
- `clarify`: não restam marcadores obrigatórios de esclarecimento;
- `plan`: plano referencia a feature ativa;
- `tasks`: tarefas possuem identificadores e podem ser verificadas;
- `analyze`: nenhum achado crítico ou alto permanece aberto;
- `implement`: todos os arquivos modificados podem ser associados a tarefas;
- `validate`: todos os gates bloqueantes retornam sucesso.

As validações estruturais devem ser determinísticas e conservadoras. Elas não devem tentar substituir avaliação semântica completa.

## 8. Política de tentativas

Valores padrão:

```text
max_attempts_per_phase = 2
phase_timeout_seconds = 600
max_analyze_repair_cycles = 3
```

Uma nova tentativa deve receber:

- a causa objetiva da falha anterior;
- a lista de caminhos permitidos;
- os artefatos esperados;
- somente o contexto mínimo da fase.

Ela não deve receber o transcript integral anterior.

## 9. Modo auto

O modo `auto` começa em `native`. Deve migrar para `guarded` quando ocorrer qualquer evento crítico:

- código criado antes de `implement`;
- escrita fora do projeto;
- chamada de ferramenta simulada como texto;
- fase declarada concluída sem artefato;
- tentativa de pular uma transição rejeitada pelo core;
- reentrada no skill Spec Master durante uma fase;
- dois timeouts ou duas respostas consecutivas sem progresso.

Também deve migrar após dois eventos recuperáveis:

- caminho incorreto;
- placeholder não removido;
- artefato criado no local errado;
- encerramento após erro de ferramenta recuperável.

Após a migração:

- registrar `mode_transition: native -> guarded` no estado;
- registrar os motivos;
- não retornar automaticamente ao modo `native` durante o mesmo workflow;
- retomar da primeira fase ainda não validada.

## 10. Estado persistente

Adicionar ao `.spec-master/state.json`:

```json
{
  "execution": {
    "requested_mode": "auto",
    "active_mode": "guarded",
    "integration": "opencode",
    "model": "ollama-neon/qwen3-coder-agent:30b",
    "mode_transitions": [
      {
        "from": "native",
        "to": "guarded",
        "reason": "implementation_before_implement_phase",
        "timestamp": "2026-08-17T18:00:00Z"
      }
    ]
  },
  "attempts": {
    "constitution": [
      {
        "number": 1,
        "status": "FAILED",
        "reason": "placeholder_artifact",
        "transcript": ".spec-master/logs/constitution-1.jsonl"
      }
    ]
  }
}
```

Escritas no estado devem permanecer atômicas.

## 11. Isolamento OpenCode

O adaptador inicial deve usar um agente dedicado, por exemplo `spec-phase`, com:

- skill loading negado;
- `auto-continue` desabilitado;
- web desabilitada por padrão;
- uma fase por sessão;
- modelo explicitamente configurado;
- ferramentas de filesystem e shell disponíveis;
- diretório do projeto fixado;
- saída em JSONL arquivada.

O controlador deve invocar:

```bash
opencode run \
  --pure \
  --format json \
  --dir <project> \
  --agent spec-phase \
  --model <model> \
  --command speckit.<phase> \
  <phase-prompt>
```

## 12. Retomada e idempotência

- Fases `PASSED` não devem ser repetidas quando seus artefatos e fingerprint permanecem válidos.
- Uma execução interrompida deve retomar da primeira fase não validada.
- Um `run.lock` abandonado deve ser reconhecido como stale após o timeout configurado.
- Alterações no contexto devem usar o mecanismo existente de fingerprint e staleness.
- Artefatos de uma tentativa inválida devem ser preservados em `.spec-master/failed-attempts/` ou revertidos por uma estratégia recuperável.
- O controlador nunca deve executar `git reset --hard` ou apagar trabalho não atribuído à tentativa atual.

## 13. Observabilidade e relatório

Cada fase deve emitir eventos curtos:

```text
[Spec Master] constitution attempt 1/2 started (guarded).
[Spec Master] constitution failed: official file still contains placeholders.
[Spec Master] constitution attempt 2/2 passed.
```

O relatório final deve separar:

- resultado do workflow;
- resultado de cada quality gate;
- contribuição efetiva do modelo;
- tentativas rejeitadas;
- mudança de modo;
- arquivos preservados para diagnóstico.

Um projeto implementado por fallback/controlador não pode ser apresentado como aprovação do modelo avaliado.

## 14. Requisitos funcionais

- **GM-001**: aceitar `native`, `guarded` e `auto`.
- **GM-002**: usar `auto` quando nenhum modo for informado.
- **GM-003**: isolar cada fase em uma sessão no modo protegido.
- **GM-004**: impedir promoção de estado sem validação de artefato.
- **GM-005**: rejeitar escrita fora da allowlist da fase.
- **GM-006**: rejeitar implementação anterior à fase `implement`.
- **GM-007**: detectar chamadas de ferramenta simuladas.
- **GM-008**: aplicar timeout e limite de tentativas.
- **GM-009**: migrar automaticamente de `native` para `guarded` conforme a política.
- **GM-010**: retomar workflows protegidos de forma idempotente.
- **GM-011**: preservar transcripts e causas de falha.
- **GM-012**: suportar inicialmente OpenCode sem quebrar os adaptadores existentes.

## 15. Requisitos não funcionais

- O controlador deve usar Python stdlib sempre que possível.
- Testes unitários não devem depender de Ollama, OpenCode ou rede.
- Processos externos devem ser mockáveis.
- Paths devem ser resolvidos e validados antes de qualquer operação.
- Snapshots devem ignorar `.venv`, caches, dependências instaladas e logs do próprio controlador.
- A adição não deve alterar o comportamento de `--mode native`.

## 16. Testes obrigatórios

### Unitários

1. parsing dos três modos;
2. modo padrão `auto`;
3. transição `native -> guarded` por evento crítico;
4. acumulação de eventos recuperáveis;
5. rejeição de escrita fora da allowlist;
6. detecção de placeholder;
7. detecção de ferramenta simulada;
8. detecção de implementação antecipada;
9. timeout;
10. limite de tentativas;
11. retomada da primeira fase incompleta;
12. lock stale;
13. snapshot ignorando caches;
14. estado escrito atomicamente.

### Integração com agente falso

1. agente produz constituição válida;
2. agente retorna sucesso sem alterar artefato;
3. agente cria `src/app.py` durante `constitution`;
4. agente escreve `<tool_call>` como texto;
5. agente tenta escrever fora do projeto;
6. primeira tentativa falha e segunda passa;
7. tentativas se esgotam e fase fica `BLOCKED`;
8. workflow completo simulado chega a `COMPLETED`.

### Smoke test opcional com modelo real

Executar o case `qwen-todo-api` em `guarded`, preservando os transcripts. Esse teste não deve fazer parte da suíte unitária bloqueante.

## 17. Critérios de aceite

1. `python3 -m unittest discover -s spec-master/tests -v` passa integralmente.
2. O modo `native` mantém os testes e o comportamento existentes.
3. Um agente falso não consegue marcar `constitution` como `PASSED` mantendo o template original.
4. Um agente falso não consegue criar código durante `constitution`, `specify`, `clarify`, `plan`, `tasks` ou `analyze` sem a tentativa ser rejeitada.
5. O modo `auto` migra para `guarded` após implementação antecipada.
6. O modo `guarded` executa todas as oito fases simuladas em sessões separadas.
7. Uma execução interrompida retoma sem repetir fases válidas.
8. O relatório diferencia claramente `workflow SUCCESS` de `model FAILED`.
9. O case real pequeno pode ser iniciado com um único comando documentado.

## 18. Estrutura sugerida

```text
spec-master/
├── lib/
│   ├── controller.py
│   ├── execution_mode.py
│   ├── phase_contracts.py
│   ├── phase_runner.py
│   └── opencode_runner.py
├── tests/
│   ├── test_controller.py
│   ├── test_execution_mode.py
│   ├── test_phase_contracts.py
│   └── test_phase_runner.py
└── templates/
    └── prompts/
        └── guarded/
```

Essa estrutura é uma sugestão e pode ser simplificada, desde que as responsabilidades permaneçam testáveis.

## 19. Migração

1. Preservar o protocolo e o modo atual como `native`.
2. Incorporar o runner OpenCode existente ao novo contrato de fases.
3. Adicionar o modo `guarded` sem mudar o padrão inicialmente.
4. Validar com agentes falsos e com `qwen-todo-api`.
5. Depois dos testes, alterar o padrão para `auto`.
6. Atualizar README, adapters e instalador global.

## 20. Definição de pronto

A melhoria estará concluída quando os três modos estiverem disponíveis, o controlador protegido impedir promoção falsa de fases, a retomada funcionar, todos os testes determinísticos passarem e o case pequeno produzir um relatório que distinga corretamente o sucesso do workflow do desempenho do modelo.
