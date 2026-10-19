# Contract: dashboard server (consumer of docs/contracts/token-ledger-v1.md §3–§4)

| Route | Behaviour |
|---|---|
| `GET /api/model` | `dashboard.build_model(root)` + `tokens` (§3 aggregate or `null`), `agents`, `timeline`. `Cache-Control: no-store`. |
| `GET /api/events` | `text/event-stream`. `event: <type>\ndata: <one-line JSON>\n\n`. Types: events.jsonl record `type`; `tokens`; `hook.fired`; `hook.decision`; `change`; `model`. Heartbeat `: ping\n\n` every 15 s. |
| `GET /healthz` | `{"ok": true}` |
| `GET /` and assets | committed bundle; missing bundle -> static HTML from the current model |
| other method | 405; foreign `Host` -> 403; unknown path -> 404 |

`agents[]`: `{agent_id, agent_type, worktree, feature_id, phase, started_at, finished_at|null, active}`.
`timeline[]`: `{feature_id, phase, session_id, started_at, finished_at|null, status}`.
`change` payload: `{id, status, updated_at}` (or `{id}` if unreadable).
`model` payload: `{generated_at, reason: "state.json changed"}`.
