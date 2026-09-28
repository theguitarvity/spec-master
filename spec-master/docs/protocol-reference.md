# Spec Master — protocol reference

> Material moved out of `PROTOCOL.md` so the agent does not load it on every
> run. Nothing here changes the protocol; `PROTOCOL.md` points to each section
> where it matters. Paths are relative to the `spec-master/` package unless a
> command says otherwise.

## Global installation

This engine doesn't have to live inside a single project. `init.sh` (next to
this file, at the repo root of the *ai-sdd-master-skill* source) mirrors this
whole `spec-master/` package to `~/.spec-master-engine` and registers a
**global** entrypoint for the documented adapters, each in that agent's own
documented personal/user-level skill directory:

- Claude Code: `~/.claude/commands/spec-master.md`,
  `~/.claude/skills/spec-master/SKILL.md`.
- GitHub Copilot CLI: `~/.copilot/skills/spec-master/SKILL.md` and
  `~/.copilot/agents/spec-master.agent.md`.
- OpenAI Codex CLI: `~/.codex/skills/spec-master/SKILL.md`.
- Shared fallback both Copilot CLI and Codex CLI also scan:
  `~/.agents/skills/spec-master/SKILL.md`.

So `/spec-master <context-file>` (or `$spec-master`, or `@spec-master`,
depending on the agent) works in every project on the machine, for every
adapter, without vendoring a copy. `init.sh link <project>` additionally
generates a small per-project pointer (`.github/skills/spec-master/SKILL.md`,
`.agents/skills/spec-master/SKILL.md`) for teammates who haven't run
`init.sh` themselves, or repos that want the pointer committed. Either way,
there is exactly one copy of `lib/`, `templates/`, and this protocol on a
given machine; every adapter, in every project, reads from it.

## Metrics export (OTLP)

When the user wants the metrics in an observability stack, run
`python3 spec-master/lib/cli.py metrics export --path . --format otlp --output
.spec-master/metrics/rounds.otlp.json`. This produces an OTLP/JSON
`ExportMetricsServiceRequest` that can be POSTed to a collector's
`/v1/metrics` endpoint:

- `spec_master.round.duration` is a Gauge in `s`.
- `spec_master.tokens.input`, `spec_master.tokens.output`,
  `spec_master.work_packages.completed` and `spec_master.features.completed`
  are monotonic DELTA Sums with one data point per round.
- Each data point carries the attributes `spec_master.round_id` and
  `spec_master.phase`, plus `spec_master.feature_id` and `spec_master.tier`
  when the row has them.

Use `--format jsonl` for log pipelines. The export validates the rows first and
writes nothing if they are invalid. Spec Master never sends the file anywhere
itself: shipping it to a collector is a separate action the user must confirm.

## Calibration

Attribute every round so calibration can use it:

`python3 spec-master/lib/cli.py metrics record-round ... --feature-id ID --tier <feature.risk.tier>`

Rows without these two flags are counted in `ignored_rounds` and are not used.

`python3 spec-master/lib/cli.py metrics calibrate --path . [--rounds FILE] [--window 3] [--state PATH] [--apply]`

- For each completed feature, calibration compares the actual cost with its tier's budget. The cost basis is tokens, falling back to duration ≥ 60 s, then round count. Each feature is then marked:
  - `under`: it cost more than its tier's budget
  - `over`: it cost less than 75% of the budget of the tier below
  - `ok`
  - `pending`: not yet completed
- A feature whose tier came from sensitivity or an override is never counted as `over`.
- **Drift** means the last `--window` features of a tier went the same way. It is reported as, for example, "XS está custando como S há 3 features seguidas".
  - Drift `under` tightens that tier's thresholds (×0.8).
  - Drift `over` loosens the tier below (×1.25), so cheap features move down.
  - The monotonic order of tiers is always preserved.
- Without `--apply`, calibration only reports. `proposed_thresholds` shows the result.
- With `--apply`:
  - It writes `.spec-master/risk/thresholds.json` and appends to `.spec-master/risk/calibration-log.jsonl`.
  - Evidence that was already used (`consumed_until`) never fires the same drift again.
  - Run it only with the user's agreement, at a retrospective or a milestone.

## EARS

Acceptance criteria *may* use EARS-like syntax (EN or PT). Supported patterns:
ubiquitous (`The <system> shall <response>` / `O <sistema> deve <resposta>`),
event (`When`/`Quando`), state (`While`/`Enquanto`), unwanted
(`If … then`/`Se … então`), optional (`Where`/`Onde`), and complex
(several preconditions). The modal is `shall` (EN) or `deve`/`deverá` (PT).
`must`/`should`/`will` are only flagged with a `weak_modal` hint.

- `ears check --path . [--feature <id>]` checks the criteria stored in
  `state.json`. `ears check --text "<criterion>" [--text …]` checks draft text
  before `state upsert-feature`.
- The check is **advisory by default**: it always exits 0 and reports
  `coverage`, per-criterion `pattern`/`clauses`, and `hints`, such as
  `no_modal`, `weak_modal`, `missing_system`, `missing_comma`, `missing_then`,
  `vague_term` and `multiple_shall`. Use the hints to tighten wording during
  `/speckit.clarify`. Never rewrite criteria silently. Propose the rewrite and
  keep the user's meaning.
- `--strict` is opt-in. Use it only when the constitution or the user requires
  EARS. With `--strict`, any non-EARS criterion makes `valid: false` and the
  command exits 1. Treat that as a clarify issue, not a blocker for other
  features.

## Local dashboard

`.spec-master/reports/dashboard.html` is a static, self-contained page: inline CSS only, no CDN, fonts or network requests. It follows light or dark mode from the OS and works on narrow screens. It is a **render**, never a source of truth. Open it with `file://` in any browser.

```bash
python3 spec-master/lib/cli.py dashboard render --path . [--output PATH] [--refresh N]
# -> {"output": "<abs path>", "features": 10, "completeness": 30.0, "active": false}
python3 spec-master/lib/cli.py dashboard model --path .    # the read-only JSON model the page is built from
```

- **When it updates.** The default `dashboard-refresh` hook re-renders the page on `phase.started`, `phase.transition` and `workflow.status`. Hook failures are swallowed and never block a transition. Run `dashboard render` to refresh it on demand.
- **Read-only.** Rendering never writes `state.json` or any other source. The only thing it creates is the output file and its parent directory. The write is atomic: a temp file in the same directory, then `os.replace`. The knowledge graph is read only if `.spec-master/knowledge/graph` already exists.
- **Graceful degradation.** Each source is optional: state, `workstreams.json`, `metrics/rounds.json`, `hooks/firings.jsonl`, traceability rows, decision memory and the graph.
  - A missing source shows an empty section.
  - A corrupt source is listed under "Some sources could not be read".
  - A missing `state.json` renders a "Not initialized" page instead of failing.
- **Completeness.** A phase counts as done when it is `PASSED` or `SKIPPED`. Per-feature % is done/phases. Global % is weighted by phase count across all features.
- **Refresh rule.** The page is static, so its run state is decided when it is rendered:
  - `running`: `.spec-master/run.lock` is fresh (not older than `execution.phase_timeout_seconds`, default 600s), or some feature phase is `RUNNING`. The page gets a spinner and `<meta http-equiv="refresh" content="N">`. N comes from `--refresh` and defaults to 5.
  - `settling`: not running, but `state.json` or the firings log changed in the last 120s, and the workflow is not terminal (`COMPLETED/BLOCKED/FAILED/PAUSED`) or the last logged lifecycle event is `phase.started`. There is no meta refresh. A tiny inline script reloads every N seconds until 120s after generation. This bridges the gap between phases, where the controller has already released the lock.
  - `idle`: everything else. No refresh and no script.
  - `--refresh 0` disables both the meta refresh and the settling script.
  - This rule is a heuristic over files on disk. A crashed agent that leaves a phase `RUNNING` keeps the page in `running` until the state is corrected.

## Adapters

Four adapters are hand-written today, each a thin pointer file living in its
own platform's directory, all reading this same file and calling the same
`spec-master/lib/cli.py`:

- `.claude/commands/spec-master.md` + `.claude/skills/spec-master/SKILL.md`
  (Claude Code, `/spec-master`, `$ARGUMENTS`) — see `adapters/claude-code.md`.
- `.github/skills/spec-master/SKILL.md` (GitHub Copilot, `/spec-master`,
  matching Spec Kit's own `speckit-<command>/SKILL.md` layout for Copilot) —
  see `adapters/copilot.md`.
- `.agents/skills/spec-master/SKILL.md` (OpenAI Codex CLI, `$spec-master`,
  matching Spec Kit's own `$speckit-<phase>` skills-mode layout for Codex) —
  see `adapters/codex.md`.
- Qwen-based environments, via `adapters/qwen.md`, for shells or agents that
  expose the same file-system + command-execution primitives.

Every other agent [GitHub Spec Kit](https://github.com/github/spec-kit)
supports (30+ — Gemini CLI, Cursor, IBM Bob, Trae, Kilo Code, Goose, Cline,
Devin, Factory Droid, Grok Build, RovoDev, ZCode, Zed, Kiro CLI, Tabnine,
Forge, Kimi Code, and more) gets a *generated* entrypoint instead, rendered
by `spec-master/lib/adapters_gen.py` from a table transcribed from Spec
Kit's own integration registry — same four points above (argument
resolution, this protocol, the deterministic core, turn-taking in place of
`AskUserQuestion`), same stopping conditions, just written into each target
project's agent-specific install directory and file format when `init.sh
link <project>` or `adapters_gen.py generate` runs. The source repo keeps the
generator table, not every generated directory at its root. See
`adapters/generic.md` for the full rationale and the regeneration command.

None of these platform directories contain any Python, templates, or
protocol content of their own — everything structural or semantic-but-shared
lives only in `spec-master/`.

## MCP server

Agents that speak MCP can call the deterministic core as tools instead of
shelling out: `spec-master/mcp/spec_master_mcp.py` is a stdlib-only stdio MCP
server that exposes **every** `cli.py` command. The tool list is introspected
from `cli.build_parser()` at startup — `<group> <action>` becomes the tool
`<group>_<action>` (dashes as underscores: `state_show`, `git_strategy_plan`,
`traceability_render`, `graph_neighbors`, `hooks_emit`, `team_decisions`, ...),
so a new CLI group is available over MCP with no server change. Arguments are
the argparse `dest` names (`{"feature": "001-auth", "phase": "plan", "status":
"PASSED"}` for `state_transition`).

Each call runs `python3 spec-master/lib/cli.py ...` in a subprocess (argv
list, no shell) with `cwd` fixed to the project root, so the MCP path and the
shell path share the same code, JSON output and exit codes: `structuredContent`
carries the CLI's JSON object, `isError: true` mirrors a non-zero exit (e.g.
`{"error": "state file not found: ..."}`). Tools annotated
`readOnlyHint: true` never write (`*_show`, `*_list`, `*_validate`,
`graph_stats`, `graph_neighbors`, `gates_detect`, ...); every other tool may
update `.spec-master/` exactly like its CLI command — the protocol rules above
(when to transition, when to record traceability) apply unchanged.

Register it per project in `.mcp.json` (Claude Code starts stdio servers in
the project root):

```json
{"mcpServers": {"spec-master": {"type": "stdio", "command": "python3",
  "args": ["spec-master/mcp/spec_master_mcp.py"]}}}
```

With the global engine, use `~/.spec-master-engine/mcp/spec_master_mcp.py`
and pass `--project <repo>` (or `SPEC_MASTER_PROJECT`) if the client does not
start servers in the repository root. `SPEC_MASTER_MCP_TIMEOUT` (default 120 s)
bounds each call; `--list-tools` prints the tool catalog for debugging. See
`mcp/README.md`.

## Web bundle

`python3 spec-master/lib/cli.py bundle build --path . --feature <id>
[--phase <phase>] [--budget 12000] [--output FILE | --stdout] [--no-timestamp]`
writes one Markdown file to `.spec-master/bundles/<feature>-<phase>.md`. You
can paste that file into a chat assistant that has no file-system or shell
access. When `--phase` is omitted, the phase is the feature's first one that is
not `PASSED` or `SKIPPED`. `--phase constitution` works without `--feature`.

The bundle contains, in order:

1. Usage steps for the user and hard rules for the assistant:
   - it has no tool access;
   - it must return every deliverable in full, preceded by `File: <path>`;
   - it must never invent sources, and must ask for anything left out.
2. The phase prompt, rendered from `templates/prompts/<phase>.md`:
   - placeholders are filled from `state.json` and the project files;
   - anything that cannot be filled stays visible as `{{name}}` and is listed
     under "Unresolved placeholders".
3. The feature record.
4. The prior artifacts, constitution and normalized context for that phase, in
   priority order, trimmed as whole files by `context_budget.budget_items()`.
5. A **Not included** list of every file dropped for the budget or not found.

The deliverable paths come from `phase_contracts.PHASE_ARTIFACTS`. The
`validate` phase has no template, so it gets a built-in prompt that marks
every quality gate `NOT RUN`.

The bundle is a convenience for people outside an agent runtime. It does not
replace the guarded flow. Once the user has saved the returned files, record
the outcome with the normal CLI (`state transition`, `traceability add`, and so
on). A bundle is never evidence that a phase passed.
