# Tech Stack

## Architecture Overview

Motor de orquestração Python stdlib (`spec-master/lib/`) exposto via uma
CLI (`spec-master/lib/cli.py`, hoje com grupos `state`, `fingerprint`,
`discovery`, `features`, `git-strategy`, `gates`, `constitution`,
`traceability`). O agente (skill Claude Code / Copilot / Codex / OpenCode)
chama essa CLI para toda decisão estrutural e executa as fases reais do
Spec Kit. A feature guarded-mode adiciona uma segunda forma de condução:
um controlador determinístico (`controller.py`) que substitui o agente
como condutor de transições de fase, delegando a execução de cada fase a
um processo externo isolado (inicialmente `opencode run`) em vez de deixar
o próprio agente conduzir livremente.

## Languages

- Python 3 (stdlib apenas, sem dependências externas — `spec-master/lib/`,
  `spec-master/tests/`).
- Bash (`init.sh`, scripts de instalação global).

## Frameworks

- Nenhum framework externo — `unittest` da stdlib para testes
  (`python3 -m unittest discover -s spec-master/tests -v`).

## Runtime

- Executado localmente via `python3`, sem servidor persistente.
- Integração externa opcional: `opencode` CLI (subprocess), `ollama`
  (modelo local, referenciado via `--model ollama-neon/...` no exemplo da
  CLI determinística).

## Infrastructure

- Nenhuma infraestrutura de nuvem — ferramenta local/CLI.
- Estado persistido em arquivo: `.spec-master/state.json` (por projeto).

## Components

### `controller.py` (novo)

Responsibilities:

- Orquestrar o loop determinístico do modo `guarded`/`auto`: ler estado,
  confirmar fase anterior `PASSED`, criar snapshot, renderizar prompt,
  invocar o runner da integração escolhida, validar artefatos, promover ou
  registrar falha, aplicar timeout/limite de tentativas.
- Expor subcomandos `run`, `resume`, `status`.

Affected areas:

- `.spec-master/state.json` (leitura/escrita atômica via `state.py`
  existente, estendido com o bloco `execution`).
- `.spec-master/logs/`, `.spec-master/failed-attempts/`.

### `execution_mode.py` (novo)

Responsibilities:

- Parsing e validação dos três modos (`native`/`guarded`/`auto`).
- Política de migração automática `native -> guarded` (eventos críticos vs.
  recuperáveis, acumulação de dois eventos recuperáveis).

Affected areas:

- `state["execution"]` (`requested_mode`, `active_mode`,
  `mode_transitions`).

### `phase_contracts.py` (novo)

Responsibilities:

- Contrato por fase: artefatos obrigatórios, allowlist de escrita,
  validações gerais e estruturais (tabela §6 e §7 da spec original).
- Detecção de placeholder, detecção de ferramenta simulada como texto,
  detecção de implementação antecipada, verificação de caminhos dentro do
  projeto.

Affected areas:

- Todas as fases `constitution`..`validate`; somente leitura fora da
  allowlist da fase corrente.

### `phase_runner.py` (novo)

Responsibilities:

- Executar uma fase isolada: sessão nova sem histórico, timeout, coleta de
  transcript/ferramentas/alterações de filesystem, aplicação das
  validações de `phase_contracts.py`.

Affected areas:

- Delegação ao adaptador de integração (`opencode_runner.py` inicialmente).

### `opencode_runner.py` (já existente, não commitado)

Responsibilities:

- Invocar `opencode run --pure --format json --dir <project> --agent
  spec-phase --model <model> --command speckit.<phase> <phase-prompt>` e
  capturar saída estruturada.

Affected areas:

- A integrar ao novo contrato de fases (`phase_runner.py`) conforme §19
  passo 2 da spec original.

### `discovery.py` (já estendido, não commitado)

Responsibilities:

- Descobrir comandos `speckit.*` por integração (`claude`, `opencode`,
  `qwen`), expondo `speckit_command_paths`.

Affected areas:

- Usado pela CLI determinística e potencialmente pelo controlador para
  resolver o comando `speckit.<phase>` correto por integração.

## Integration Points

- GitHub Spec Kit (`specify` CLI / `.specify/`) — já inicializado neste
  repositório com integração `claude` (Skills em `.claude/skills/`).
- OpenCode CLI (`opencode run`) — adaptador inicial do modo guarded.
- Modelo local via Ollama, referenciado por nome de modelo na CLI
  determinística (não gerenciado por este projeto — fora do escopo baixar
  ou escolher modelos).

## Configuration

- `--mode {native,guarded,auto}` no comando principal `/spec-master`.
- `--integration`, `--model` na CLI determinística
  (`spec-master/lib/controller.py run`).
- Defaults de política: `max_attempts_per_phase = 2`,
  `phase_timeout_seconds = 600`, `max_analyze_repair_cycles = 3`
  (este último já existente no protocolo atual, reafirmado pela spec).

## Technical Constraints

- Stdlib-only sempre que possível.
- Testes unitários não podem depender de rede, Ollama ou OpenCode reais —
  processos externos mockáveis.
- Snapshots devem ignorar `.venv`, caches, dependências instaladas e logs
  do próprio controlador.
- `--mode native` deve permanecer comportamentalmente inalterado.

## Architectural Principles

- Core determinístico e testável sem LLM (mesma divisão de
  responsabilidade já documentada no `PROTOCOL.md` §0 — Core vs. Agente —
  estendida agora para "Core vs. Agente vs. Controlador guarded").
- Escritas no estado devem ser atômicas.
- O controlador nunca marca uma fase como concluída apenas porque o
  processo do agente retornou código zero — validação de artefato é
  sempre necessária.

## Testing Strategy

### Unit

14 casos listados em `docs/spec-master/guarded-mode-spec.md` §16 (parsing
de modos, modo padrão, transições, allowlist, placeholder, ferramenta
simulada, implementação antecipada, timeout, limite de tentativas,
retomada, lock stale, snapshot ignorando caches, escrita atômica de
estado).

### Component

Testes de cada módulo novo (`execution_mode.py`, `phase_contracts.py`,
`phase_runner.py`) isoladamente, seguindo o padrão já usado em
`spec-master/tests/` (ex.: `test_opencode_runner.py`, `test_discovery.py`).

### Integration

8 casos de integração com agente falso (§16): constituição válida, sucesso
sem alterar artefato, código criado durante `constitution`, `<tool_call>`
como texto, escrita fora do projeto, retry que passa na segunda tentativa,
esgotamento de tentativas → `BLOCKED`, workflow completo simulado →
`COMPLETED`.

### E2E

Smoke test opcional, não bloqueante, com modelo real: case `qwen-todo-api`
em modo `guarded`, preservando transcripts.

## Quality Gates

- `python3 -m unittest discover -s spec-master/tests -v` (gate bloqueante,
  citado explicitamente como critério de aceite 1 da spec original).

## Repository Conventions

- Módulos novos em `spec-master/lib/`, testes espelhados em
  `spec-master/tests/test_<module>.py` (padrão já observado em
  `discovery.py`/`test_discovery.py`, `opencode_runner.py`/
  `test_opencode_runner.py`).
- Estrutura sugerida (§18 da spec original, não obrigatória tal qual):
  `spec-master/templates/prompts/guarded/` para os prompts curtos por fase.

## CI/CD

- Nenhuma CI configurada neste repositório (`ci_present: false` na
  discovery).

## Technical Non-goals

Ver `[[app-features]]` — idêntico ao `## Fora do escopo` da spec original.

## Open Technical Questions

- Formato exato do "prompt curto e específico da fase" (§8) além de
  conteúdo mínimo listado (causa da falha anterior, allowlist, artefatos
  esperados, contexto mínimo da fase) — a ser resolvido na fase `clarify`
  se necessário.
- Mecanismo exato de "sessão nova, sem histórico" para a integração
  OpenCode — se via novo processo `opencode run` por fase (mais provável,
  dado que cada `opencode run` já é uma invocação isolada) ou outro
  mecanismo — a confirmar durante `plan`.

## Source Traceability

| Decision / Constraint | Source | Classification |
|---|---|---|
| Estrutura sugerida de módulos (§18) | guarded-mode-spec.md §18 | EXPLICIT |
| Comando de invocação OpenCode (§11) | guarded-mode-spec.md §11 | EXPLICIT |
| Requisitos não funcionais (§15) | guarded-mode-spec.md §15 | EXPLICIT |
| Testes obrigatórios (§16) | guarded-mode-spec.md §16 | EXPLICIT |
| `opencode_runner.py`/`discovery.py` já existentes | leitura do repositório | DISCOVERED_FROM_CODEBASE |
| Nenhuma CI configurada | `discovery scan` (`ci_present: false`) | DISCOVERED_FROM_CODEBASE |
| Formato do prompt curto por fase, mecanismo exato de isolamento OpenCode | inferência a partir de texto geral da spec | UNRESOLVED |
