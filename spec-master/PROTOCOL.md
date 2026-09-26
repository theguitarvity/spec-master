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
  structural diff, per-feature traceability store and rendering, spec delta
  between runs, declarative event hooks, Team Mode roles, guided-intake
  questions, workstream/review assignment, escalation routing and decision
  memory, risk tiers, worktree waves, SAST/secrets gate detection, tracker
  extension detection, PR planning, EARS lint, execution dashboard, metrics
  export, web bundles, context budget accounting, command policy preflight,
  graph snapshots/drift checks, runtime capability contracts, and
  deterministic harness evals. The agent calls it via `Bash` (or the MCP
  server, §5) for every structural decision — never re-derive these by hand.
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
4. Whenever state exists (resume either way), show the user what changed in
   the feature artifacts since the last run:
   `delta report --path . --format markdown --output
   .spec-master/reports/delta.md`. It lists ADDED/MODIFIED/REMOVED entries for
   each `spec.md`/`plan.md`/`tasks.md` (sections, task ids, checkbox flips) plus
   the constitution and `.spec-master/context/*.md`, and the phases each change
   makes stale — the same style as `constitution diff`. After a phase finishes
   (or at the end of the session), refresh the baseline with
   `delta snapshot --path .` so the next resume diffs against it. A missing
   snapshot is not an error: the report comes back with `baseline: false`
   and nothing to show — take the snapshot and move on.

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
2. Before instantiating any role for a package, review, or gate decision,
   load its binding playbook — never improvise a role's practices from
   general knowledge: `python3 spec-master/lib/cli.py knowledge get --id
   playbook.<role-id>` (resolve team_model.py ids like `po`, `infra`,
   `ui-ux-brand` to their knowledge-base ids `product-owner`,
   `infrastructure`, `ux` first — `knowledge for-role` does this
   resolution automatically). Pull additional budgeted context for the
   specific task with `knowledge for-context --role <role-id> --keywords
   "<feature/task keywords>" --tech-stacks "<detected stack>"`. Playbooks
   define each role's concrete must-do/must-avoid practices, testing
   conventions, stack/tooling defaults, and escalation triggers — see
   `spec-master/knowledge/playbooks/*.md` (or `playbook.spec-master` for
   the orchestrator's own escalation-routing rules).
3. During/after `tasks`, call `python3 spec-master/lib/cli.py team
   workstreams --file <features-with-tasks.json>` and write the result to
   `.spec-master/workstreams.json`.
4. The workstream plan may expose safe parallel work, but each package must
   still respect feature dependencies, Spec Kit phase gates, and analyze
   repair rules.
5. Dev agents implement only assigned packages, per their playbook:
   - Backend Dev Agent: APIs, persistence, business rules, backend tests,
     integrations (`playbook.backend-dev`).
   - Frontend Dev Agent: screens, components, forms, UI state,
     accessibility, responsive behavior, UI tests (`playbook.frontend-dev`).
   - Fullstack Dev Agent: thin vertical slices and front/back integration
     (`playbook.fullstack-dev`).
   When a dev agent finds an architecture inconsistency or a candidate
   design-pattern decision that crosses its package (see
   `design.gof-patterns`), it does not resolve this unilaterally — it
   escalates to the Architect Agent per its playbook's Escalation
   Triggers, which routes to the Tech Lead to create a scoped, owned
   remediation package (see `playbook.architect`, `playbook.tech-lead`).
   The Scrum Master Agent folds that new package into the visible plan and
   metrics (`playbook.scrum-master`).
6. Every implementation package requires peer review by a different dev
   agent (`reviewer_agent`) before QA validation. The reviewer cannot be the
   package owner, and checks conformance against the owner's playbook, not
   just correctness.
7. QA validates behavior against acceptance criteria using its own test
   pyramid rules (`playbook.qa`: unit owned by the dev agent, backend
   integration tests stub external systems with WireMock, frontend
   component/E2E tests use Cypress). The Tech Lead resolves code conflicts,
   shared-file ownership, contract ordering, and final integration
   readiness. Spec Master records the result and controls workflow status.
8. When discovery or the feature set implies more than one independently
   deployable service, the Architect Agent proposes containerization and
   Kubernetes/Helm; the DevOps and Infrastructure Agents own the concrete
   CI/CD pipeline (any of GitHub Actions, Jenkins, Azure DevOps, Spinnaker,
   Nexus — pick from evidence, not default) and Terraform provisioning
   (`playbook.devops`, `playbook.infrastructure`). Do not propose this
   tooling for a single deployable service.

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

Every row in `rounds.json` must match `spec-master/schemas/metrics-round.schema.json`
(JSON Schema 2020-12: one row at the root, the array at `#/$defs/rounds`; the
optional keys are `notes`, `feature_id` and `tier`, and any other key is rejected).
Before the final report, run `python3 spec-master/lib/cli.py metrics validate
--path .`. It exits 1 and lists `{index, path, message}` for each error. Fix the
rows it names; do not delete them to make the check pass. Its warnings, such as
`total_tokens != input + output`, a reversed interval or a duplicate `round_id`,
do not block anything, but mention them in the report.

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

- **risk tier**: classify each feature at intake (before `clarify`) and again
  before `implement`, and apply the resulting ceremony profile. See
  "Risk-adaptive ceremony" below.
- **clarify**: batch every `USER_DECISION_REQUIRED` question into one message
  (§21); never ask one at a time; resume automatically after the answer.
  Skip it only when the feature's profile says `clarify: skippable`, and
  record the skip with `--status SKIPPED`.
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
  "...", "status": "..."}'`. Rows go to one file per feature,
  `.spec-master/traceability/features/<feature-id>.json` (`state init` enables
  this store for new states; for a state created before it existed, run
  `traceability migrate` once — idempotent — to move the legacy inline array
  out of `state.json`).
  Never edit those files or the rendered report by hand.

#### Risk-adaptive ceremony (tiers XS–XL) and calibration

Ceremony scales with risk. Every feature gets a tier. The tier picks a ceremony profile: how deep the pipeline goes, who reviews, and whether work is split into role packages. The core is deterministic (stdlib only). The orchestrator records decisions but never invents a tier.

##### Tier = max(scope, sensitivity floors, override)

- **Scope** is measured against `.spec-master/risk/thresholds.json`. If that file is absent, the built-in defaults apply. The signals are:
  - acceptance criteria
  - words in the description
  - tasks
  - files touched
  - architectural layers
- A feature's scope tier is the first tier whose limits hold every signal. The output's `scope.binding` shows which signals pushed it higher.
  - **At intake** these are estimates from the spec text plus any `--paths` hints.
  - **At `pre_implement`** the tasks come from `<spec_directory>/tasks.md`: the task count, plus the files and layers cited in the tasks.
- **Sensitivity** comes from the hook events `feature.intake` and `feature.pre_implement`. The default `sensitivity-*` hooks use `raise_tier` with these floors:
  - auth, payment, secrets: floor **L**
  - schema, public_contract, external_provider: floor **M**
  - Project hooks in `.spec-master/hooks.json` can disable a default hook or add new floors.
- An **override** can only raise the tier. See the override rules below.

##### Ceremony profiles (`risk profiles`)

| Tier | clarify   | analyze | work packages | ADR check | review                   |
|------|-----------|---------|---------------|-----------|--------------------------|
| XS   | skippable | light   | no            | no*       | self                     |
| S    | skippable | light   | no            | no*       | peer                     |
| M    | required  | deep    | no            | no*       | peer                     |
| L    | required  | deep    | yes           | yes       | peer + tech-lead         |
| XL   | required  | deep    | yes           | yes       | peer + tech-lead + architect |

\* The ADR check is forced on at any tier when sensitivity includes auth, payment, secrets or external_provider (see `profile.adr_reason`).

Only `clarify` may be skipped. Record a skip with `state transition --feature ID --phase clarify --status SKIPPED`. The state machine refuses SKIPPED for every other phase. It does not check the profile itself, so the orchestrator must skip clarify only when `profile.clarify == "skippable"`. In guarded mode, `controller.py run --feature ID` does this on its own: when the saved `feature.risk.tier` makes clarify skippable, it records `SKIPPED`, emits `phase.transition` with `source: risk_profile`, and never starts a clarify session. The next phase then accepts `SKIPPED` as the previous status, the same as `PASSED`.

For L/XL features, `risk work-packages --feature ID --tier L` returns role packages in this order: contract → data-model → backend → frontend → e2e → docs. Each package carries an owner, a peer reviewer and `depends_on`. Register them with the workstreams, and do not create new speckit steps.

##### When the orchestrator MUST classify

1. **Intake.** Run this before `speckit.clarify`:
   `python3 spec-master/lib/cli.py risk classify --path . --feature ID --stage intake --save [--paths a,b]`
   - It persists `feature.risk` and emits `feature.intake`. The firings go to `.spec-master/hooks/firings.jsonl`.
   - It returns `context`: the change delta since the last snapshot, plus prior decisions for this feature. Show these to the agents at intake.
   - Apply `profile` to decide whether clarify is skippable, how deep analyze goes, and who reviews.
2. **Pre-implement.** Run this after `speckit.tasks` and before `speckit.implement`:
   `python3 spec-master/lib/cli.py risk classify --path . --feature ID --stage pre_implement --save`
   - If `escalated` is true, stop. Announce `added_obligations`, then re-run every phase in `rerun_phases` before implementing: `analyze` always, and `clarify` if it did not PASS.
   - If `deescalated` is true, report it, but keep the obligations already met.
   - If `warnings` includes "tasks.md not found", the tier is still the intake estimate.

`risk classify` without `--save` is a dry run. It writes nothing and emits nothing.

##### Override rules

`python3 spec-master/lib/cli.py risk override --path . --feature ID --tier L --reason "..." [--by user]`

- A reason is mandatory. The command fails if the reason is empty.
- Overrides can only go **up**. A request below the current tier is refused (exit 1). It is still appended to `.spec-master/risk/overrides.jsonl` with `accepted: false`, for audit.
- An accepted override sets `feature.risk.override` and `feature.risk.tier`. It is logged with `accepted: true`, and it survives later reclassification. The command returns `added_obligations` and the new `profile` and `work_packages`.
- Every accepted override is a calibration signal. It means the computed tier was too low.
- Never lower a tier to save time. If a sensitivity floor looks wrong, change the project hooks config and record why.

##### Calibration (`metrics calibrate`)

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

#### Optional EARS acceptance criteria

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

#### Event hooks (declarative automation)

`state transition` and the guarded-mode controller emit events
(`phase.started`, `phase.transition`, `gate.result`, `workflow.status`, …);
`.spec-master/hooks.json` maps them to actions. The built-in defaults cover
the recurring rules — `hooks list --path .` shows the effective set, `hooks
init --path .` writes an editable config (a project hook with the same `id`
overrides a default; `disabled: [ids]` turns one off), `hooks validate` checks
it.

- **Directives** (`repair`, `revalidate`, `escalate`, `raise_tier`, `block`,
  `notify`) are instructions for *you*: `state transition` prints them under
  `hook_directives`, and `hooks emit --event <type> --payload-json '{...}'`
  returns them for events you raise yourself (`analyze.findings` with the
  finding counts after every analyze, `package.contract_changed` when a
  package changes a public contract, `gate.result` for each gate you run by
  hand). Follow them: `repair` → repair the named phase/artifact (analyze
  repair rules still apply), `revalidate` → re-run `constitution diff`,
  `escalate` → hand the issue to the returned `route.chain` (the first hop
  decides), `block` → transition the feature to `BLOCKED` and tell the user.
- **Internal actions** (`render_dashboard`, `record_decision`) are executed by
  the core itself and never stop a run if they fail.
- Every firing is appended to `.spec-master/hooks/firings.jsonl` (`hooks
  firings --limit N`). Hooks are advisory plumbing: a broken `hooks.json` is
  reported by `hooks validate` but never breaks `state transition` or the
  controller.

#### Escalations and decision memory

When a role hits one of its playbook's escalation triggers, don't route it by
hand: `team escalate --path . --kind <kind> --raised-by <role> [--feature
<id>] [--summary "..."]` returns the playbook route (`chain`, `decided_by`,
`package_owner`, `adr_candidate`); `team routes` lists every kind. Once the
deciding role has decided, record it:

```
team resolve --path . --kind <kind> --raised-by <role> --decision "<what was decided>"
  [--decided-by <role>] [--rationale "..."] [--feature <id>] [--title "..."]
  [--alternative "<rejected option>" ...] [--adr-trigger <trigger> ...]
```

This writes a `Decision` node to the knowledge graph (`DECIDED_BY` the
deciding agent, `INFLUENCES` the feature node when it exists) — re-recording
the same decision is idempotent. ADR triggers (`new_external_provider`,
`new_core_data_model`, `security_privacy_change`, `boundary_change`,
`infra_change`, `rejected_alternatives`; `systemic_violation` escalations add
one automatically) also write an ADR file into the repository's existing ADR
directory (`docs/adr`, `docs/decisions`, …), or `.spec-master/adr/` when the
repository has none. Before a role acts, load its past decisions together
with its playbook: `knowledge for-role --role <role> --path .` (adds a
`decisions` list), or `team decisions --path . --role <role> | --feature <id>`.

### Step 7 — Quality gates (CLAUDE.md §28)

`gates detect --path .` — never hardcode a command family. Before running any
returned shell command, call `policy preflight "<command>"`; execute only
commands classified as `allowed: true`. Commands classified as blocked or
requiring approval must be reported to the user instead of bypassed. Run each
allowed `command` via `Bash`, record
`{name, command, result, exit_code, blocking}`; a failing `blocking: true`
gate prevents `SUCCESS` (see stopping conditions).

Security scanners follow the same evidence rule. `gates detect` also returns
SAST/secret-scanning gates (`category: "sast"` or `"secrets"`) — but only for
scanners the repository already opted into (a Semgrep/Bandit/Gitleaks config,
a pre-commit hook, a package script, or a CI workflow running CodeQL/Semgrep);
no evidence means no gate, never a failure. These gates are always
`blocking: true`. A gate with `execution: "ci"` has `command: null`: don't
invent a local equivalent — record it as `DEFERRED_TO_CI` (the guarded-mode
controller does this automatically) and confirm the CI check result before
declaring `SUCCESS`. A failing security gate escalates to the Security Agent
through the `escalate-security-gate-failure` hook. `discovery scan` reports
the same evidence under `sast_scanners`.

For prompts that include generated context, preflight the assembled context
with `budget file --files <comma-separated-files> --token-budget <budget>`.
If relevant context is omitted, list the omitted IDs/files in the phase notes
instead of silently exceeding budget.

### Step 8 — Report & traceability (CLAUDE.md §35-36)

`traceability render --path .spec-master/state.json --output
.spec-master/reports/traceability.md` (add `--feature <id>` for a single
feature's matrix). The report is always a render of the per-feature store —
never the source of truth, never edited by hand. Fill
`templates/final-report.md` → `.spec-master/reports/final-report.md`.
Before printing the final status, run:

1. `graph enrich-discovery --path .`
2. `graph validate --path .`
3. `graph snapshot --path . --name final`
4. `graph health --path .`
5. `evals run`
6. `runtime contract --runtime-type hybrid`

Print the report to the user only when graph validation and deterministic
harness evals pass, or clearly classify the result as `PARTIAL`/`BLOCKED`.
Determine final status per §29:

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

#### Local dashboard

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

#### Optional PR step (Git Flow only — never automatic)

At the end of a Git Flow feature, after `validate` is `PASSED` and the
final report is filled, you *may* offer to open a pull request:

1. `pr plan --path . --feature <id> [--base <branch>] [--draft]`. This renders
   the PR description (summary, acceptance criteria, phases, the feature's
   traceability matrix and the final report) to
   `.spec-master/reports/pr-<id>.md` and returns an `action`:
   - `noop`: the workflow is trunk-based or not chosen. Do nothing.
   - `blocked`: there is no recorded `feature.branch`, `validate` is not
     `PASSED`, or head equals base. Report the `reason` and don't open a PR.
   - `confirm_required`: show the user the `title`, `head → base`,
     `provider`, and `body_path`, and **ask explicitly** whether to open the
     PR. If the answer is no, stop there. The body file stays as an artifact.
2. Only after an explicit "yes" in chat, re-run with `--confirm`. The result
   is `action: open_pr` with `pre_directives` and a `directive`:
   - Execute each `pre_directives[].argv` first. This is `git push -u <remote>
     <head>`, emitted only when the remote-tracking ref is missing.
   - Then execute `directive.argv` (`gh pr create …`, `glab mr create …` or
     `az repos pr create …`, depending on the provider detected from the
     remote URL). If `directive.argv` is `null` (unknown provider), show the
     user `directive.manual` and the body file instead.
   - If `tool_available` is false, tell the user which CLI is missing. Don't
     install it.
3. Record the PR URL printed by the tool in the final report and the feature
   notes.

The core never runs `git push`/`gh`/`glab`/`az` itself. It only emits
directives with `requires: ["user_confirmed"]`. One confirmation covers one
PR. Don't reuse it for other features. `pr plan` exits 0 for
`noop`/`blocked`/`confirm_required`, so always branch on `action`.

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
`AskUserQuestion`), same stopping conditions, just written into each target
project's agent-specific install directory and file format when `init.sh
link <project>` or `adapters_gen.py generate` runs. The source repo keeps the
generator table, not every generated directory at its root. See
`adapters/generic.md` for the full rationale and the regeneration command.

None of these platform directories contain any Python, templates, or
protocol content of their own — everything structural or semantic-but-shared
lives only in `spec-master/`.

### MCP server (dedicated, stdio)

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

### Web bundle (chat UIs without tools)

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
