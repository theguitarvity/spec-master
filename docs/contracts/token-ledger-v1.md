# Contrato — Token ledger e event stream v1 (ciclo 2)

> Status: INFERRED (fixado pelo orquestrador em 2026-10-19 para permitir que
> `token-ledger-and-statusline` (produtor) e `live-react-dashboard` (consumidor)
> rodem em paralelo). Mudanças exigem atualizar este arquivo e as duas features.

Todos os arquivos ficam sob `.spec-master/` do projeto-alvo, em JSONL (um objeto
JSON por linha, append-only, UTF-8). Timestamps em ISO-8601 UTC (`...Z`).

## 1. `.spec-master/events.jsonl` — eventos de execução (atribuição)

Campos comuns: `schema` = `"spec-master.event/v1"`, `ts`, `type`, `session_id` (string|null),
`feature_id` (string|null), `phase` (string|null).

| `type` | Campos extras |
|---|---|
| `phase.started` / `phase.finished` | `status` (`RUNNING`/`PASSED`/`FAILED`/`BLOCKED`/`SKIPPED`) |
| `agent.started` / `agent.finished` | `agent_id`, `agent_type` (papel ou nome do subagente), `worktree` (string|null), `transcript_path` (string|null) |
| `gate.result` | `name`, `command`, `exit_code`, `blocking` |
| `hook.fired` | `hook_id`, `event` |

## 2. `.spec-master/metrics/tokens.jsonl` — ledger de tokens

Uma linha por requisição ao modelo (deduplicada por `request_id` quando existir).

```json
{
  "schema": "spec-master.tokens/v1",
  "ts": "2026-10-19T12:00:00Z",
  "source": "claude-code-transcript | otel | codex | opencode",
  "session_id": "…", "request_id": "…|null",
  "agent_id": "…|null", "agent_type": "…|null",
  "feature_id": "…|null", "phase": "…|null",
  "model": "claude-…",
  "input_tokens": 0, "output_tokens": 0,
  "cache_read_tokens": 0, "cache_creation_tokens": 0,
  "cost_usd_estimate": 0.0
}
```

`feature_id`/`phase` são preenchidos por atribuição: janela do último
`phase.started` sem `phase.finished` correspondente na mesma sessão, e
`agent_id` via `agent.started`/`agent.finished`. Não atribuível → `null`, nunca inventado.

## 3. Agregado — `python3 spec-master/lib/cli.py tokens summary [--path .] [--since ISO]`

Saída JSON (`schema: "spec-master.tokens-summary/v1"`):

```json
{
  "totals": {"input_tokens":0,"output_tokens":0,"cache_read_tokens":0,"cache_creation_tokens":0,"total_tokens":0,"cost_usd_estimate":0.0,"cache_hit_ratio":0.0},
  "by_feature": {"<id>": {…mesmos campos…}},
  "by_phase": {"<feature_id>:<phase>": {…}},
  "by_agent": {"<agent_id>": {"agent_type":"…", …}},
  "by_model": {"<model>": {…}},
  "burn_rate_tokens_per_min": 0.0,
  "window": {"first_ts":"…","last_ts":"…"}
}
```

`cache_hit_ratio = cache_read / (input + cache_read + cache_creation)`; 0 quando o denominador é 0.

## 4. Live server (`live-react-dashboard`)

- `GET /api/model` → `dashboard.build_model()` (schema `spec-master.dashboard/v1`)
  acrescido da chave `tokens` com o agregado da §3 (ou `null` se o ledger não existir).
- `GET /api/events` → SSE. Cada mensagem `event: <type>` + `data: <linha JSON>`
  para novas linhas de `events.jsonl`, `metrics/tokens.jsonl` (`type: "tokens"`)
  e `hooks/firings.jsonl` (`type: "hook.fired"`); `event: model` quando
  `state.json` mudar. Heartbeat `: ping` a cada 15 s.
- Bind exclusivo em `127.0.0.1`.
