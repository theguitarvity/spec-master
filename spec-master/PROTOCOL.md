# Spec Master — Orchestration Core (model-agnostic)

> This package (`spec-master/`) lives at the **repository root**, deliberately
> outside `.claude/`, `.github/`, and `.agents/` — it is shared by every
> platform adapter, not owned by any one of them. Paths written as
> `lib/...`, `templates/...`, `adapters/...` below are relative to this
> directory; shell commands are written as `python3 spec-master/lib/cli.py
> ...` because the agent's shell working directory is the repository root,
> not this directory.

> **Lane flow (opt-in).** `/spec-master --lane [<lane>] <request>` does not use
> this file: it follows `cards/router.md`, where a deterministic triage decides
> — before any artifact exists — whether a change is a *patch* (implemented in
> the session, closed by `step end` on evidence) or needs the full cycle
> described here. This file remains the default flow.

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
only report `FAILED — Spec Kit unavailable` (final statuses in Step 8) if the user
declines or no `specify`/`uvx` is reachable — never simulate Spec Kit's
output as a substitute.

Spec Master also supports **Team Mode**: a deterministic multi-agent delivery
model layered around the same Spec Kit workflow. Team Mode never replaces the
canonical `constitution -> specify -> clarify -> plan -> tasks -> analyze ->
implement -> validate` spine; it adds role-specific discovery, technical
work-package ownership, parallel workstream opportunities, UI/UX + brand
direction, and peer review by another dev agent before tech-lead integration.

## Global installation

`init.sh` installs this engine once per machine (`~/.spec-master-engine`) and
registers the global entrypoints; `init.sh link <project>` adds per-project
pointers. Details: `docs/protocol-reference.md#global-installation`.

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
  server, see §5) for every structural decision — never re-derive these by hand.
- **Agent (you, running this skill)**: reading and semantically understanding
  the user's context file and the repository, writing the normalized context
  documents, generating each `speckit.*` prompt from the templates in
  `templates/prompts/`, executing the actual Spec Kit commands (by following
  whatever command/skill file the target repository's Spec Kit installation
  uses for that phase and platform — see the relevant `adapters/*.md` for the
  exact path convention) with that prompt as input, resolving ambiguity, and
  writing the final report.

## 1. Anti-hallucination rule

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
2. `python3 spec-master/lib/cli.py state show --summary --path
   .spec-master/state.json` (if it fails because the file doesn't exist, this
   is a fresh run — go to Step 1). The summary is enough to resume; load the
   full record (`state show`) only for a feature you are about to work on.
3. If state exists: recompute the fingerprint of the context file + any
   `.spec-master/context/*.md` already generated
   (`fingerprint compute --files ...`) and compare against
   `state["fingerprint"]` (`fingerprint compare --previous ... --current ...`).
   - Identical → resume automatically (safe default), continue from the
     first phase that isn't `PASSED`/`COMPLETED`. Say so in one line.
   - Different → `AskUserQuestion`: **Resume existing workflow** vs
     **Restart workflow**. Only the phases marked stale by `fingerprint
     compare` need to be redone if the user resumes; never blindly redo
     everything, and never treat `implement` as auto-invalidated — assess
     impact instead (§3).
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

### Step 1 — Discovery (read-only)

`python3 spec-master/lib/cli.py discovery scan --path .` and read the manifests it found
directly if you need more than command detection (README.md, CLAUDE.md,
AGENTS.md, CONTRIBUTING.md, .github/, docs/, specs/, .specify/). Never modify
anything in this step. Write `.spec-master/reports/discovery.md` summarizing
what was found (language/framework, build/test/lint commands, CI, existing
Spec Kit / constitution / specs, branching model hints).

### Step 2 — Spec Kit availability + Git strategy (mandatory once, batched)

Two independent decisions are gated here. Per the batching rule (§4), ask
both **in a single `AskUserQuestion` call** (it supports multiple questions
per call) whenever both are pending — never two separate prompts back to
back.

1. **Spec Kit not initialized** (`discovery.spec_kit_present == false`, i.e.
   no `.specify/` in this repo): this blocks every downstream phase, so
   resolve it before anything else. If a `specify` CLI is reachable
   (`which specify`, or `uvx` as a fallback via
   `uvx --from git+https://github.com/github/spec-kit.git@v0.16.4 specify ...`
   — always a tagged release, never the moving default branch; the supported
   range is `>=0.16.4,<1.1`), ask whether to run `specify init --here` now. If declined, or if no
   `specify`/`uvx` is reachable at all, this is a `FAILED — Spec Kit
   unavailable` condition (Step 8) — say so plainly and stop; don't keep
   generating normalized docs against a repo that can't execute any
   `speckit.*` phase.
   - This same check ships as a **non-interactive installer path** too:
     `init.sh` (at the engine's repo root) runs it as a shell prompt when
     bootstrapping a new project — see "Global installation" above. Either
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

### Step 3 — Normalized context layer

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

### Step 4 — Constitution

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
   potentially blocking decision (changing governance is never
   auto-approved).

Never state "constitution approved" — use `GENERATED`/`VALIDATED` internally;
"approved" requires the user's explicit word.

### Step 5 — Feature discovery & ordering

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

`state upsert-feature --feature-json '{...}'` for each. Upsert records
metadata only: it refuses to change `phases`, `evidence`, `risk` or to mark a
feature `COMPLETED` while a phase is open — phases move only through `state
transition` (Step 6). History that never ran through Spec Master can be
imported with `--import-unverified --reason "..."`, which marks every promoted
phase as unverified evidence. Then `features order --file <features.json>`
for the execution sequence. A cycle is a hard stop — report it, don't guess
an order.

`spec_directory` is the directory Spec Kit will create for the feature. Pass
its number and short name to the specify script (`--number NNN --short-name
<slug>`) so both agree; if Spec Kit still creates a different directory,
record the real one with `state upsert-feature` before promoting `specify`.

### Step 6 — Per-feature workflow

**Team Mode** applies only when the user asked for it, when guided intake
created the context, or when the project adopted it (`team adopt`). In that
case, read `docs/team-mode.md` once before the first feature and follow it —
roles, playbooks, workstreams, peer review and escalation routing live there,
not here.

At the end of every meaningful round (a phase, a workstream package, a
review, a gate run), record it from the host's own accounting — never from
memory:

- **Claude Code**: `python3 spec-master/lib/cli.py telemetry ingest --path .
  --latest --since <round start> --round-id <id> --phase <phase> --feature-id
  <id> [--tier <tier>] --append` reads only `usage` and timestamps (never
  message content) from the session transcript and appends a
  `source: host-transcript` row to `.spec-master/metrics/rounds.json`.
- **Headless runs** (`claude -p --output-format json`): `telemetry ingest
  --headless-json <result file> ...` records the measured cost
  (`source: host-headless`).
- **A host with no accounting**: `metrics record-round ... --source manual
  --append` with the observed timestamps. Token fields stay 0 and the row is
  stored as `manual-unverified`; cost reports and calibration ignore it.

Never invent token counts or timestamps, and never edit `rounds.json` by
hand. Before the final report, run `metrics validate --path .` (it exits 1 on
errors such as a host-sourced row with zero tokens or an impossible
timestamp; fix the rows it names instead of deleting them) and `metrics
summarize --file .spec-master/metrics/rounds.json`, and include total tokens,
tokens/minute, packages/hour and features/hour in
`.spec-master/reports/final-report.md`, saying which rows are unverified.
Every row must match `spec-master/schemas/metrics-round.schema.json`.

Exporting the rounds to an observability stack (`metrics export`) is a
separate action the user confirms — see
`docs/protocol-reference.md#metrics-export-otlp`.

For each feature id in the resolved order, drive:

```
specify -> clarify -> plan -> tasks -> analyze(+repair, max 3) -> implement -> validate
```

using `state transition --feature <id> --phase <phase> --status <status>`
before/after each step (the core rejects starting phase N before phase N-1
`PASSED` — trust that guard, don't bypass it). `--status PASSED` also needs
evidence (constitution Principle IV): the phase's artifact in the feature's
`spec_directory`, non-empty and without template placeholders; for
`implement`, every task in `tasks.md` checked; for `validate`, at least one
traceability row for the feature. The core checks it and refuses the
promotion otherwise — fix the artifact, don't work around the check. `state
evidence --feature <id> --phase <phase>` runs the same check without changing
anything. Promoting `validate` marks the feature `COMPLETED`. The command
answers with a short ack (`--full` prints the whole record). Prompts come from
`templates/prompts/<phase>.md`, filled with the normalized docs, constitution,
discovered conventions, and this feature's `source_requirements`/
`acceptance_criteria`/`dependencies` — never copy another project's prompt
verbatim. Execute the actual Spec Kit phase by following the installed
command or skill for the platform you're running on — `discovery scan`
reports it per phase under `speckit_phase_entrypoints` (e.g.
`.claude/skills/speckit-<phase>/SKILL.md`, invoked as `/speckit-<phase>`, for
Claude Code with a current Spec Kit; `.claude/commands/speckit.<phase>.md`
for older installs; `.github/skills/speckit-<phase>/SKILL.md` for Copilot;
`.agents/skills/speckit-<phase>/SKILL.md` for Codex) — with the generated
prompt as its effective input; if that command/skill doesn't exist, this is
a `FAILED` condition (Step 8). Where an installed skill asks the user
something, the batching rule (§4) takes precedence over the skill's own
turn-taking, as detailed per phase below.

- **risk tier**: classify each feature at intake (before `clarify`) and again
  before `implement`, and apply the resulting ceremony profile. See
  "Risk-adaptive ceremony" below.
- **clarify**: batch every `USER_DECISION_REQUIRED` question into one message
  (§4); never ask one at a time; resume automatically after the answer. The
  installed clarify skill asks its (up to 5) questions one by one — collect
  them and ask them all in a single `AskUserQuestion` call instead, then
  encode every answer into the spec as the skill describes. Skip clarify only
  when the feature's profile says `clarify: skippable`, and record the skip
  with `--status SKIPPED`.
- **analyze**: never skip it, never go straight from `tasks` to `implement`.
  The installed analyze skill ends by offering remediation to the user; don't
  ask — the repair loop here is automatic. On findings, don't implement —
  repair the responsible artifact
  (spec/plan/tasks) and re-run analyze. Track cycles with
  `state analyze-cycle --feature <id> --action increment|check`; at 3
  exhausted cycles, transition the feature to `BLOCKED` and escalate to the
  user — never mask remaining issues by editing the report instead of the
  artifact. MEDIUM findings may proceed only if they don't touch behavior,
  security, integrity, acceptance criteria, or normative architecture —
  record that decision.
- **implement**: execute only analyzed/approved tasks, checking each one off
  in `tasks.md` as it is done (the `implement` evidence requires it). If the
  implement skill stops on unchecked checklist items, report the checklist
  table and continue without asking when the unchecked items are
  reviewer-owned quality notes; ask (in the phase's single question batch)
  only when an unchecked item is a requirement of this feature. On
  `SPEC_DRIFT`, stop the affected task, reassess, update plan/spec only when
  justified, redo tasks + analyze, then resume — never improvise around a
  mismatch.
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

- **Scope** is measured against `.spec-master/risk/thresholds.json`. If that file is absent, the built-in defaults apply. A feature's scope tier is the first tier whose limits hold every signal; `scope.binding` shows which signals pushed it higher.
  - **At intake** the signals are estimates: acceptance criteria, words in the description, files and architectural layers from the spec text plus any `--paths` hints.
  - **At `pre_implement`** the signals are the files and layers cited in `<spec_directory>/tasks.md`. The task count is reported but does not set the tier (the Spec Kit template splits a small module into 20+ tasks). Files count production code only: tests and docs are part of the work, not of its risk, and a bare file name in the task prose counts only when it exists at the project root.
- **Sensitivity** comes from the hook events `feature.intake` and `feature.pre_implement`, matched against the feature's own text (name, description, acceptance criteria) and the concrete paths — never against the generated task prose, whose Spec Kit vocabulary (`data-model`, `contracts/`) would raise every feature. The default `sensitivity-*` hooks use `raise_tier` with these floors:
  - auth, payment, secrets: floor **L**
  - schema, public_contract, external_provider: floor **M**
  - irreversible (push, pull/merge request, package publish, deploy to a shared environment): floor **M** — and the action itself still needs the user's explicit confirmation (Principle X)
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

Calibration adjusts the tier thresholds from measured rounds. Rows recorded
without host telemetry (`source` missing or `manual-unverified`) never feed
it, and `--apply` runs only with the user's agreement, at a retrospective or
a milestone. Details: `docs/protocol-reference.md#calibration`.

#### Optional EARS acceptance criteria

`ears check --path . [--feature <id>]` (or `ears check --text "<criterion>"`
for drafts) lints acceptance criteria against EARS patterns (EN/PT). It is
advisory unless the constitution or the user requires EARS (`--strict`).
Never rewrite a criterion silently — propose the rewrite and keep the user's
meaning. Patterns and hints: `docs/protocol-reference.md#ears`.

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

### Step 7 — Quality gates

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
It returns only ids and estimated tokens (`selected_ids`, `omitted_ids`) —
read the selected files yourself, once. If relevant context is omitted, list
the omitted IDs/files in the phase notes instead of silently exceeding
budget.

### Step 8 — Report & traceability

`traceability render --path .spec-master/state.json --output
.spec-master/reports/traceability.md` (add `--feature <id>` for a single
feature's matrix). The report is always a render of the per-feature store —
never the source of truth, never edited by hand. Fill
`templates/final-report.md` → `.spec-master/reports/final-report.md`.
Before printing the final status, check the evidence behind every
feature's promotions with `state evidence --feature <id>`: `verified` phases
passed the core's check, `unverified` ones were imported with a reason, and
`missing` ones were promoted before evidence existed. Report the last two
per feature — they are not proof that the phase happened. The harness's own
self-checks (graph validation, harness evals, runtime contract) belong to the
project's CI (`doctor`), not to every workflow run. Determine the final
status:

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

`dashboard render --path .` writes `.spec-master/reports/dashboard.html`, a
static render of the state (never a source of truth); the default
`dashboard-refresh` hook keeps it current. Details:
`docs/protocol-reference.md#local-dashboard`.

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

## 3. Idempotency & staleness

Before any mutating action, prefer the idempotent check: Spec Kit already
installed → don't reinstall; git extension already present → don't add
again; context files unchanged (fingerprint match) → don't regenerate;
constitution already compatible (`constitution diff` returns only
`UNCHANGED`) → don't rewrite; feature already `PASSED` through `validate` →
don't reimplement. When a normalized doc changes, use
`fingerprint compare` to see exactly which phases go stale and re-run only
those — never assume `implement` is invalid without assessing impact first.

## 4. Progress messaging and questions

Emit short status lines as you move through phases
(`[Spec Master] 3 features identified.`,
`[Spec Master] Feature 1/3: specification generated.`), not raw internal
Spec Kit output. Present decisions, blockers, results, and phase changes —
nothing else.

**Batching rule.** Ask the user only at a phase boundary, with every pending
question in a single batch (`AskUserQuestion` takes several questions per
call) — never one question per turn, and never in the middle of a phase
unless the phase cannot continue at all. A wait longer than a few minutes
also expires the prompt cache, so every extra stop costs a full context
rewrite. When a question has a safe default and the answer changes neither
scope, security, data nor a public contract, take the default instead of
asking and record it in the phase notes as `SAFE_DEFAULT: <decision>`. The
gates that always need the user's word stay unchanged: Spec Kit
initialization and Git strategy (Step 2), constitutional conflicts (Step 4),
unresolved `USER_DECISION_REQUIRED` items, and anything irreversible
(Principle X).

## 5. Portability

Nothing in this file or in `lib/` references a specific project, stack, org,
or prior feature name. Every adapter must:

1. Resolve the context-file argument from its own invocation mechanism.
2. Follow this file's protocol.
3. Call `spec-master/lib/cli.py` for every structural decision.
4. Use its own platform's way of asking the user (`AskUserQuestion` here;
   see `adapters/copilot.md` and `adapters/codex.md` for their equivalents).

Hand-written adapters exist for Claude Code, GitHub Copilot, OpenAI Codex and
Qwen-compatible shells; every other Spec Kit agent gets a generated
entrypoint (`init.sh link`). None of them contains protocol content of its
own. List and layout: `docs/protocol-reference.md#adapters`.

### MCP server and web bundle

Agents that speak MCP can call the core through
`spec-master/mcp/spec_master_mcp.py` (every CLI command as a tool, same JSON
and exit codes); chat UIs without tools can use `bundle build`. Neither
changes the rules above. Details: `docs/protocol-reference.md#mcp-server` and
`docs/protocol-reference.md#web-bundle`.
