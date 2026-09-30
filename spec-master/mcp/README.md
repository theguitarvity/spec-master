# Spec Master MCP server

`spec_master_mcp.py` exposes every command of the deterministic core
(`spec-master/lib/cli.py`) as an MCP tool over **stdio**. It is stdlib-only
(no `mcp` SDK, no network) and runs under plain `python3` (PyYAML is optional,
as it is for the CLI).

```bash
python3 spec-master/mcp/spec_master_mcp.py [--project PATH] [--timeout SECONDS] [--tools all|entrypoint]
python3 spec-master/mcp/spec_master_mcp.py --list-tools   # print the tools as JSON and exit
```

`--tools entrypoint` (or `SPEC_MASTER_MCP_TOOLS=entrypoint`) lists only
`harness_entrypoint`. The plugins start the server that way: their skills
need only that tool, and a host that loads every schema at session start
would otherwise carry the whole list (about 49 KB) in each session.

Register it in Claude Code with a project `.mcp.json`:

```json
{
  "mcpServers": {
    "spec-master": {
      "type": "stdio",
      "command": "python3",
      "args": ["spec-master/mcp/spec_master_mcp.py"]
    }
  }
}
```

After `init.sh`, the global engine copy lives at
`~/.spec-master-engine/mcp/spec_master_mcp.py`; pass `--project` (or set
`SPEC_MASTER_PROJECT`) when the client does not start servers in the project
root.

## Project root

In order: `--project`, `SPEC_MASTER_PROJECT`, the host's own variable
(`CLAUDE_PROJECT_DIR`, `CURSOR_PROJECT_DIR`, `GEMINI_PROJECT_DIR`), then the
working directory. When the root came from the working directory and the
client supports MCP roots, the server asks for them after
`notifications/initialized` (and again on `roots/list_changed`) and takes the
first one. Plugin hosts often start servers in the plugin's own directory:
while the root still looks like an install directory, every tool except
`harness_entrypoint` is refused with a pointer to the CLI, so nothing is ever
written inside the plugin.

## Entrypoints

`harness_entrypoint {"flow": "full-cycle"|"lane", "argument": ...}` returns
the instructions for a run with this engine's absolute paths filled in, which
is how the path-free plugin skills find the engine on any host. The same
texts are served as MCP prompts: `spec-master` (argument `context`, optional)
and `spec-master-lane` (argument `request`, required).

## Tools

The tool list is built at startup from `cli.build_parser()`, so new CLI groups
appear with no server change:

| CLI | MCP tool |
|---|---|
| `state show --summary` | `state_show {"summary": true}` |
| `git-strategy plan --feature-name f` | `git_strategy_plan {"feature_name": "f", ...}` |
| `graph neighbors <node_id>` | `graph_neighbors {"node_id": "..."}` |
| a group with no actions | `<group>` |

- Properties are named after the argparse `dest`. `type=int/float` become
  `integer`/`number`, `choices` an `enum`, `store_true` a `boolean` (flag passed
  only when true), `append`/`nargs` an `array` (repeated flag), `required=True`
  and positionals a `required` entry, `help` the property description.
  `store_false`/`store_const` flags are named after the flag (`--no-color` ->
  `no_color`). Unknown arguments are rejected; `null` means "omit". Objects
  passed to string parameters (e.g. `payload_json`) are JSON-encoded.
- Tool descriptions come from the subparser `help=`/`description=`; add one in
  `cli.py` and it shows up in `tools/list`.
- `annotations.readOnlyHint` is `true` only for a conservative allowlist of
  action names (`show`, `list`, `get`, `search`, `validate`, `stats`,
  `neighbors`, `detect`, `scan`, `order`, `diff`, `firings`, `routes`,
  `decisions`, `summarize`, ...) plus a few verified pure tools
  (`git_strategy_plan`, `evals_run`, ...). Anything that may write (`render`,
  `report`, `health`, `snapshot`, `init`, `transition`, `worktree plan`, ...)
  is `false`. See `READ_ONLY_ACTIONS` / `READ_ONLY_TOOLS`.

## Execution

`tools/call` rebuilds the argv (`--flag=value`, `--` before positionals that
start with `-`) and runs `sys.executable spec-master/lib/cli.py ...` in a
subprocess: argv list, never a shell; `cwd` fixed to the project root (relative
paths resolve there); timeout `SPEC_MASTER_MCP_TIMEOUT` (default 120 s).
The result is the CLI stdout as text content, `isError` = non-zero exit (stderr
appended on errors), and `structuredContent` when stdout is a JSON object.
Unknown tools, bad arguments and timeouts are tool errors (`isError: true`),
not protocol errors.

## Protocol

Newline-delimited JSON-RPC 2.0 on stdin/stdout; logs go to stderr only.
Methods: `initialize` (echoes a supported `protocolVersion` —
2025-11-25, 2025-06-18, 2025-03-26, 2024-11-05 — else answers 2025-06-18),
`notifications/*` (no reply), `ping`, `tools/list`, `tools/call`,
`prompts/list`, `prompts/get`; the server itself sends `roots/list` (see
[Project root](#project-root)). Errors:
-32700 parse, -32600 invalid request, -32601 unknown method, -32602 invalid
params. JSON arrays are handled as JSON-RPC 2.0 batches (array reply of the
non-notification responses; empty batch -> -32600). Requests are processed
sequentially. If `cli.py` fails to import, the server still starts, lists no
tools and reports the import error.

Tests: `spec-master/tests/test_mcp_server.py`.
