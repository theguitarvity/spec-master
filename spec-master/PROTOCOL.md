# Spec Master — Orchestration Core (model-agnostic)

> This package (`spec-master/`) lives at the **repository root**, deliberately
> outside `.claude/`, `.github/`, and `.agents/` — it is shared by every
> platform adapter, not owned by any one of them. Paths written as
> `lib/...`, `templates/...`, `adapters/...` below are relative to this
> directory; shell commands are written as `python3 spec-master/lib/cli.py
> ...` because the agent's shell working directory is the repository root,
> not this directory.

`/spec-master <context-file>` replaces the manual sequence
`/speckit.constitution → /speckit.specify → /speckit.clarify → /speckit.plan
→ /speckit.tasks → /speckit.analyze → /speckit.implement` with a single
invocation. This file is the **source of truth** for the protocol; every
platform adapter (`adapters/claude-code.md`, `adapters/copilot.md`,
`adapters/codex.md`) is a thin wrapper — living inside its own platform's
directory — that follows it and shells out to the same deterministic core
(`spec-master/lib/cli.py`).

Spec Master does **not** reimplement the Spec Kit. It orchestrates it: it
generates the prompts each `speckit.*` phase needs, decides when to advance,
repair, ask the user, or stop, and keeps traceability from context to
implementation. If the Spec Kit is not installed in the target repository,
**offer to initialize it** (Step 2 below) rather than failing immediately;
only report `FAILED — Spec Kit unavailable` (§29 of CLAUDE.md) if the user
declines or no `specify`/`uvx` is reachable — never simulate Spec Kit's
output as a substitute.

Spec Master also supports **Team Mode**: a deterministic multi-agent delivery
model layered around the same Spec Kit workflow. Team Mode never replaces the
canonical `constitution -> specify -> clarify -> plan -> tasks -> analyze ->
implement -> validate` spine; it adds role-specific discovery, technical
work-package ownership, parallel workstream opportunities, UI/UX + brand
direction, and peer review by another dev agent before tech-lead integration.

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

## 0. Division of responsibility: core vs. agent

- **Core (`spec-master/lib/cli.py`, pure Python, tested without an LLM)**:
  state machine, context fingerprint/staleness, dependency ordering,
  git-strategy planning, quality-gate command detection, constitution
  structural diff, traceability rendering, Team Mode roles, guided-intake
  questions, and workstream/review assignment. The agent calls it via `Bash`
  for every structural decision — never re-derive these by hand.
- **Agent (you, running this skill)**: reading and semantically understanding
  the user's context file and the repository, writing the normalized context
  documents, generating each `speckit.*` prompt from the templates in
  `templates/prompts/`, executing the actual Spec Kit commands (by following
  whatever command/skill file the target repository's Spec Kit installation
  uses for that phase and platform — see the relevant `adapters/*.md` for the
  exact path convention) with that prompt as input, resolving ambiguity, and
  writing the final report.

## 1. Anti-hallucination rule (CLAUDE.md §5)

The file passed to `/spec-master` is the source of truth. Never invent
requirements, features, acceptance criteria, integrations, components,
business rules, dependencies, technologies, SLAs, endpoints, files, or
architectural structures that aren't supported by the context file or the
existing codebase. Every generated fact must carry a classification:

- `EXPLICIT` — stated verbatim in the source.
- `INFERRED` — reasonably deduced; must be shown as inferred, never silently
  promoted to an acceptance criterion.
- `DISCOVERED_FROM_CODEBASE` — found by reading the repository, not the
  context file.
- `UNRESOLVED` — cannot be determined; goes to the Open Questions section or
  triggers a `USER_DECISION_REQUIRED` clarification.

## 2. Protocol

### Step -1 — Guided intake when no context exists

If the invocation is `/spec-master`, `/spec-master new`, or `/spec-master
novo projeto` and no context file is provided, do not fail immediately. Start
guided intake:

1. `python3 spec-master/lib/cli.py team intake`.
2. Ask the returned questions via normal turn-taking, batched as much as the
   platform allows and using multiple choice first, with an "other/free text"
   escape when the user needs it.
3. Let the Product Owner Agent shape value, scope, MVP, and prioritization.
4. Let the UI/UX and Brand Agent shape initial experience direction, brand
   tone, palette/typography guidance, screen map, and accessibility criteria.
5. Let Architect and Scrum Master collect technical constraints, delivery
   strategy, blockers, and parallelization signals.
6. Write `.spec-master/context.generated.md` with the same source
   classifications from §1 (`EXPLICIT`, `INFERRED`,
   `DISCOVERED_FROM_CODEBASE`, `UNRESOLVED`).
7. Continue the normal protocol using that generated file as the context
   argument.

This mode is for turning a raw idea into a Spec Kit-ready context. It must
not invent commitments: unresolved answers stay unresolved and trigger the
usual clarification gates later.

### Step 0 — Resolve input & resume check

1. Resolve the context-file argument. If missing or the file doesn't exist,
   and it was not a guided-intake invocation from Step -1, stop and tell the
   user (this is not a state to persist).
2. `python3 spec-master/lib/cli.py state show --path .spec-master/state.json` (if it
   fails because the file doesn't exist, this is a fresh run — go to Step 1).
3. If state exists: recompute the fingerprint of the context file + any
   `.spec-master/context/*.md` already generated
   (`fingerprint compute --files ...`) and compare against
   `state["fingerprint"]` (`fingerprint compare --previous ... --current ...`).
   - Identical → resume automatically (§31 safe default), continue from the
     first phase that isn't `PASSED`/`COMPLETED`. Say so in one line.
   - Different → `AskUserQuestion`: **Resume existing workflow** vs
     **Restart workflow**. Only the phases marked stale by `fingerprint
     compare` need to be redone if the user resumes; never blindly redo
     everything, and never treat `implement` as auto-invalidated — assess
     impact instead (§33).

If state exists and the user asks to adopt Team Mode in an already-running
project, run `python3 spec-master/lib/cli.py team adopt` and follow its
state-preserving checklist before resuming. Adoption is additive: it writes
Team Mode artifacts and future gates, but it does not restart the workflow,
rewrite the constitution, or invalidate completed phases unless the normal
fingerprint/staleness logic proves a concrete artifact changed.

### Step 1 — Discovery (read-only, CLAUDE.md §6)

`python3 spec-master/lib/cli.py discovery scan --path .` and read the manifests it found
directly if you need more than command detection (README.md, CLAUDE.md,
AGENTS.md, CONTRIBUTING.md, .github/, docs/, specs/, .specify/). Never modify
anything in this step. Write `.spec-master/reports/discovery.md` summarizing
what was found (language/framework, build/test/lint commands, CI, existing
Spec Kit / constitution / specs, branching model hints).

### Step 2 — Spec Kit availability + Git strategy (mandatory once, batched)

Two independent decisions are gated here. Per §21's "never ask one at a
time" rule, ask both **in a single `AskUserQuestion` call** (it supports
multiple questions per call) whenever both are pending — never two separate
prompts back to back.

1. **Spec Kit not initialized** (`discovery.spec_kit_present == false`, i.e.
   no `.specify/` in this repo): this blocks every downstream phase, so
   resolve it before anything else. If a `specify` CLI is reachable
   (`which specify`, or `uvx` as a fallback via
   `uvx --from git+https://github.com/github/spec-kit.git specify ...`),
   ask whether to run `specify init --here` now. If declined, or if no
   `specify`/`uvx` is reachable at all, this is a `FAILED — Spec Kit
   unavailable` condition (§29) — say so plainly and stop; don't keep
   generating normalized docs against a repo that can't execute any
   `speckit.*` phase.
   - This same check ships as a **non-interactive installer path** too:
     `init.sh` (at the engine's repo root) runs it as a shell prompt when
     bootstrapping a new project — see "Global installation" below. Either
     path is fine; the agent-driven one here is what runs when the user
     invokes `/spec-master` directly without having run `init.sh` first.
2. **Git strategy** (`state["workflow"]` unset): ask exactly once per
   workflow —

   > Qual estratégia de desenvolvimento este projeto utiliza?
   > 1. Git Flow / Feature Branches
   > 2. Trunk-Based Development

Persist each answer immediately (`state set-workflow --workflow
git-flow|trunk` for the second one). Never ask either question again in the
same workflow. The git-strategy decision only affects **how** each feature
is executed (`git-strategy plan`), never whether the Spec Kit phases run.

- **Git Flow**: before creating any branch, check
  `discovery.speckit_commands`/`spec_kit_present` for an existing git
  extension; call `git-strategy plan --strategy git-flow --feature-name ...
  [--issue-id ...] --git-extension-installed --spec-kit-present` (flags set
  from what discovery found) and follow its `install_git_extension` /
  `branch` output. Never reinstall an extension already present. Preserve an
  explicit identifier (`APP-1234`, `PROJ-847`, `issue-123`) over a generated
  slug — `git_strategy.py` already does this when the identifier appears in
  the feature name or is passed as `--issue-id`.
- **Trunk-Based**: `git-strategy plan --strategy trunk ...` always returns
  `create_branch: false` — never create a branch, never install branch
  automation; keep working on the current branch and separate features
  logically via `specs/<feature>/`.

### Step 3 — Normalized context layer (CLAUDE.md §10-14)

Generate/update, from `templates/{app-features,project-goals,tech-stack}.md`,
under `.spec-master/context/`:

- `app-features.md` — WHAT.
- `project-goals.md` — WHY.
- `tech-stack.md` — HOW.

Populate only from the context file + discovery; write
`Not defined by current context.` for sections with nothing to say — never
force content. Classify every requirement/goal/decision per §1 above in the
Source Traceability table of each document. Avoid duplicating large blocks
across the three files; cross-reference instead. Recompute and store the
fingerprint of these three files in `state["fingerprint"]` once written.

### Step 4 — Constitution (CLAUDE.md §15-16, §39)

Build the `/speckit.constitution` prompt from
`templates/prompts/constitution.md`, sourced from the three normalized docs +
`CLAUDE.md`/`AGENTS.md` + repository conventions found in discovery. If
`.specify/memory/constitution.md` already exists:

1. `constitution diff --existing .specify/memory/constitution.md --proposed
   <drafted-file>` (you author the proposed text first as a temp file, then
   diff it — the tool is structural, not generative).
2. Apply `ADDITION`/`MODIFICATION` automatically.
3. On any `CONFLICT` or `REMOVAL_CANDIDATE`: **stop**, report it, and ask the
   user before touching a ratified principle — this is a destructive,
   potentially blocking decision (§9 permission rules apply: changing
   governance is not something to auto-approve).

Never state "constitution approved" — use `GENERATED`/`VALIDATED` internally;
"approved" requires the user's explicit word (§39).

### Step 5 — Feature discovery & ordering (CLAUDE.md §17-18)

Parse `app-features.md` into `FeatureExecution` objects:

```yaml
id: kebab-case, stable across resumes
name:
description:
source_requirements: [...]
acceptance_criteria: [...]
dependencies: [other feature ids]
branch: from git-strategy plan (or null on trunk)
status: PENDING
spec_directory: specs/<NNN-feature-id>
```

`state upsert-feature --feature-json '{...}'` for each. Then
`features order --file <features.json>` for the execution sequence (§18). A
cycle is a hard stop — report it, don't guess an order.

### Step 6 — Per-feature workflow (CLAUDE.md §19-27)

Before entering per-feature execution, initialize Team Mode when the user
asked for it explicitly, when guided intake created the context, or when an
existing project adopted Team Mode:

1. `python3 spec-master/lib/cli.py team roles` to load the canonical delivery
   roles. The Spec Master remains the orchestrator; the Tech Lead Agent owns
   technical decomposition, internal code conflicts, and integration
   approval.
2. During/after `tasks`, call `python3 spec-master/lib/cli.py team
   workstreams --file <features-with-tasks.json>` and write the result to
   `.spec-master/workstreams.json`.
3. The workstream plan may expose safe parallel work, but each package must
   still respect feature dependencies, Spec Kit phase gates, and analyze
   repair rules.
4. Dev agents implement only assigned packages:
   - Backend Dev Agent: APIs, persistence, business rules, backend tests,
     integrations.
   - Frontend Dev Agent: screens, components, forms, UI state,
     accessibility, responsive behavior, UI tests.
   - Fullstack Dev Agent: thin vertical slices and front/back integration.
5. Every implementation package requires peer review by a different dev
   agent (`reviewer_agent`) before QA validation. The reviewer cannot be the
   package owner.
6. QA validates behavior against acceptance criteria. The Tech Lead resolves
   code conflicts, shared-file ownership, contract ordering, and final
   integration readiness. Spec Master records the result and controls
   workflow status.

At the end of every meaningful round (guided intake batch, phase execution,
workstream package, peer review, QA validation, or quality gate run), record
delivery metrics with `python3 spec-master/lib/cli.py metrics record-round`.
Use observed timestamps and platform-provided token counts when available.
If exact token usage is unavailable, record `0` and note that the adapter did
not expose token accounting; never invent token counts. Append each row to
`.spec-master/metrics/rounds.json`. Before the final report, call
`python3 spec-master/lib/cli.py metrics summarize --file
.spec-master/metrics/rounds.json` and include total tokens, tokens/minute,
packages/hour, features/hour, and per-round speed in
`.spec-master/reports/final-report.md`.

For each feature id in the resolved order, drive:

```
specify -> clarify -> plan -> tasks -> analyze(+repair, max 3) -> implement -> validate
```

using `state transition --feature <id> --phase <phase> --status <status>`
before/after each step (the core rejects starting phase N before phase N-1
`PASSED` — trust that guard, don't bypass it). Prompts come from
`templates/prompts/<phase>.md`, filled with the normalized docs, constitution,
discovered conventions, and this feature's `source_requirements`/
`acceptance_criteria`/`dependencies` — never copy another project's prompt
verbatim (§41). Execute the actual Spec Kit phase by following the installed
`speckit.<phase>` command/skill for the platform you're running on (see your
`adapters/*.md` for the exact path — e.g. `.claude/commands/speckit.<phase>.md`
for Claude, `.github/skills/speckit-<phase>/SKILL.md` for Copilot,
`.agents/skills/speckit-<phase>/SKILL.md` for Codex) with the generated
prompt as its effective input; if that command/skill doesn't exist, this is
a `FAILED` condition (§29).

- **clarify**: batch every `USER_DECISION_REQUIRED` question into one message
  (§21); never ask one at a time; resume automatically after the answer.
- **analyze**: never skip it, never go straight from `tasks` to `implement`
  (§24). On findings, don't implement — repair the responsible artifact
  (spec/plan/tasks) and re-run analyze. Track cycles with
  `state analyze-cycle --feature <id> --action increment|check`; at 3
  exhausted cycles, transition the feature to `BLOCKED` and escalate to the
  user — never mask remaining issues by editing the report instead of the
  artifact. MEDIUM findings may proceed only if they don't touch behavior,
  security, integrity, acceptance criteria, or normative architecture —
  record that decision.
- **implement**: execute only analyzed/approved tasks. On `SPEC_DRIFT`, stop
  the affected task, reassess, update plan/spec only when justified, redo
  tasks + analyze, then resume — never improvise around a mismatch.
- **traceability**: as requirements get covered by spec/plan/tasks/tests, call
  `traceability add --row-json '{"requirement": "...", "source": "...",
  "feature": "...", "spec": "...", "plan": "...", "task": "...", "test":
  "...", "status": "..."}'`.

### Step 7 — Quality gates (CLAUDE.md §28)

`gates detect --path .` — never hardcode a command family. Run each returned
`command` via `Bash`, record
`{name, command, result, exit_code, blocking}`; a failing `blocking: true`
gate prevents `SUCCESS` (see stopping conditions).

### Step 8 — Report & traceability (CLAUDE.md §35-36)

`traceability render --path .spec-master/state.json >
.spec-master/reports/traceability.md`. Fill
`templates/final-report.md` → `.spec-master/reports/final-report.md` and
print it to the user. Determine final status per §29:

- `SUCCESS`: constitution valid AND all selected features implemented AND all
  acceptance criteria mapped in traceability AND analyze has no blocking
  findings left AND all blocking quality gates passed AND no unresolved
  `SPEC_DRIFT`.
- `BLOCKED`: unresolvable ambiguity, constitutional conflict, a destructive
  architectural decision needing approval, missing dependency/credential/
  service, a quality gate repeatedly failing without a safe fix, or spec
  drift needing a product decision.
- `FAILED`: Spec Kit unavailable (not installed, and the user declined the
  Step 2 offer to initialize it or no `specify`/`uvx` was reachable),
  repository inconsistent beyond safe repair, implementation can't satisfy
  acceptance criteria, or critical tests remain failing.
- `PARTIAL`: some features `SUCCESS`, others `BLOCKED`/`FAILED` — report per
  feature.

## 3. Idempotency & staleness (CLAUDE.md §32-33)

Before any mutating action, prefer the idempotent check: Spec Kit already
installed → don't reinstall; git extension already present → don't add
again; context files unchanged (fingerprint match) → don't regenerate;
constitution already compatible (`constitution diff` returns only
`UNCHANGED`) → don't rewrite; feature already `PASSED` through `validate` →
don't reimplement. When a normalized doc changes, use
`fingerprint compare` to see exactly which phases go stale and re-run only
those — never assume `implement` is invalid without assessing impact first.

## 4. Progress messaging (CLAUDE.md §37)

Emit short status lines as you move through phases
(`[Spec Master] 3 features identified.`,
`[Spec Master] Feature 1/3: specification generated.`), not raw internal
Spec Kit output. Present decisions, blockers, results, and phase changes —
nothing else.

## 5. Portability (CLAUDE.md §2, §40)

Nothing in this file or in `lib/` references a specific project, stack, org,
or prior feature name. Every adapter must:

1. Resolve the context-file argument from its own invocation mechanism.
2. Follow this file's protocol.
3. Call `spec-master/lib/cli.py` for every structural decision.
4. Use its own platform's way of asking the user (`AskUserQuestion` here;
   see `adapters/copilot.md` and `adapters/codex.md` for their equivalents).

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
`AskUserQuestion`), same stopping conditions, just written into each agent's
own real install directory and file format. See `adapters/generic.md` for
the full rationale and the regeneration command.

None of these platform directories contain any Python, templates, or
protocol content of their own — everything structural or semantic-but-shared
lives only in `spec-master/`.
