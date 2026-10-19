# Contract: host subagent files (F18, T015)

Docs check status: INFERRED. Host docs were not reachable from the implement sandbox, so formats below come from the implementer's knowledge of each host and are marked by confidence. Anything not confirmed uses `fallback_instructions` (never a guessed file).

| Host | Plugin root | Agent file | Status |
|---|---|---|---|
| Claude Code | `spec-master/` | `spec-master/agents/sm-*.md`, Markdown + frontmatter `name, description, tools` | rendered (confident) |
| Cursor, Copilot (share the Claude plugin root) | `spec-master/` | same `agents/*.md` files are discovered | rendered, shared file (medium confidence) |
| Gemini CLI | repo root | `agents/sm-*.md`, Markdown + frontmatter, Gemini tool names (`read_file`, `write_file`, `replace`, `run_shell_command`) | rendered (medium confidence) |
| Qwen Code, Codex, Kiro | - | agents live in user/project config, not in a plugin | fallback |
| Agent Plugins root, Antigravity | repo root | no agent component in the manifest | fallback |

Rules enforced by `test_packaging.SubagentTests`: three roles per rendered host; `sm-review` tools carry no write/edit tool; each body references `cards/dispatch.md` and is under 1.5 KB; render is deterministic; `check` fails on a tampered file.

Follow-up: verify Cursor/Copilot/Gemini discovery on a real install and add Qwen/Codex/Kiro renderers if their plugins gain an agents component.
