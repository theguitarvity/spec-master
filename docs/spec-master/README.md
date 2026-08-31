# Spec Master

Agentic orchestrator for the GitHub Spec Kit workflow. One invocation drives
`constitution → specify → clarify → plan → tasks → analyze (+repair) →
implement → validate` across one or more features, with a tested,
model-agnostic core underneath. Team Mode adds guided intake, multi-agent
roles, technical workstreams, peer review, and delivery metrics without
replacing the Spec Kit spine.

## Usage

```text
/spec-master <context-file>
```

```text
/spec-master new
```

Works out of the box only inside *this* repo (project-local entrypoints), or
in **any** Claude Code project once you've run `./init.sh` once — see
[Global installation](#global-installation).

## Example

```text
/spec-master CLAUDE.md
```

```text
/spec-master docs/architecture-context.md
```

The context file can be any Markdown document — `CLAUDE.md`, `AGENTS.md`, an
ADR, an RFC, a discovery doc, a preliminary spec. Spec Master interprets it
semantically; it does not require specific headings, and it never invents a
requirement, acceptance criterion, dependency, or technology that isn't
supported by that file or by the existing codebase (every generated fact is
classified `EXPLICIT` / `INFERRED` / `DISCOVERED_FROM_CODEBASE` /
`UNRESOLVED`).

## Workflow

```text
Context
  → Guided intake when no context exists
  → Discovery (read-only repo scan)
  → Spec Kit check + Git strategy question (once, batched into one prompt)
  → Normalize (app-features.md / project-goals.md / tech-stack.md)
  → Constitution
  → Feature discovery + dependency ordering
  → Team Mode workstreams (optional/adopted)
  → per feature: Specify → Clarify → Plan → Tasks → Analyze (+repair, max 3) → Implement → Validate
  → Quality gates
  → Metrics summary
  → Traceability matrix
  → Final report (SUCCESS | PARTIAL | BLOCKED | FAILED)
```

Two questions are guaranteed on a fresh run, asked **together in one
prompt**, never one after another: whether to initialize the Spec Kit now if
it isn't already (`.specify/` missing), and **Git Flow / Feature Branches**
vs **Trunk-Based Development** (recorded once, never asked again for that
workflow). Every other question is asked only when a decision changes
behavior, a public contract, architecture, or acceptance criteria, or is
destructive/unsafe to infer — and every `USER_DECISION_REQUIRED` item found
during `clarify` is batched into a single message, never one at a time.

## Git Strategies

- **Git Flow / Feature Branches**: each feature gets its own branch. Spec
  Master prefers the Spec Kit's own git extension when present
  (`specify extension add git`, only if missing — idempotent) instead of
  managing branches in parallel. An explicit identifier in the feature name
  or context (`APP-1234`, `PROJ-847`, `issue-123`) is preserved verbatim;
  otherwise a slug is derived from the feature name
  (`feature/session-renewal-bypass`).
- **Trunk-Based Development**: no branch is ever created automatically. Work
  stays on the current branch; features are separated logically via
  `specs/<feature>/` directories.

## Resume

```text
/spec-master CLAUDE.md
```

If `.spec-master/state.json` exists, Spec Master compares a fingerprint of
the context/normalized documents against the one stored at the last run:

- **Unchanged** → resumes automatically from the first phase that isn't
  `PASSED`/`COMPLETED` (safe default, no question asked).
- **Changed** → asks **Resume existing workflow** vs **Restart workflow**,
  and — if resuming — only re-runs the phases the change actually made stale
  (e.g. an `app-features.md` edit stales `specify → clarify → plan → tasks →
  analyze` downstream of the changed feature, never silently invalidates
  `implement`; a `tech-stack.md`-only edit never stales `specify`).

## Generated artifacts

> Note the leading dot: `.spec-master/` below (generated at runtime — state,
> reports, logs) is a different directory from `spec-master/` (this
> package's source, checked into the repo). They're intentionally named
> alike — one is the tool, the other is its output — but never confuse them.

```text
.spec-master/
├── context/{app-features,project-goals,tech-stack}.md   # normalized context layer
├── context.generated.md                                  # created by guided intake when needed
├── workstreams.json                                      # Team Mode packages, owners, reviewers
├── team/{roles,adoption-report}.json|md
├── metrics/rounds.json
├── state.json                                            # persistent checkpoint
├── reports/{discovery,traceability,final-report}.md
└── logs/workflow.md

.specify/memory/constitution.md   # produced by the real Spec Kit, not reimplemented
specs/<NNN-feature>/{spec,plan,tasks}.md
```

## Architecture

```text
spec-master/                         neutral, top-level package — NOT inside .claude/, .github/ or
│                                     .agents/, because it's shared by every adapter, owned by none
├── PROTOCOL.md                      model-agnostic protocol (source of truth for all 4 adapters)
├── adapters/{claude-code,copilot,codex,qwen,generic}.md
├── templates/                       normalized-doc templates + per-phase prompt skeletons
├── lib/                             deterministic core, Python 3 stdlib, zero dependencies
│   ├── cli.py                       state | fingerprint | discovery | features | git-strategy | gates | constitution | traceability | team | metrics
│   ├── adapters_gen.py              generates entrypoints for every non-bespoke Spec Kit agent
│   ├── team_model.py                Team Mode roles, guided intake, adoption plan, workstreams, peer review
│   ├── metrics.py                   round token usage and delivery-speed calculations
│   ├── state.py, fingerprint.py, discovery.py, feature_model.py,
│   │   git_strategy.py, quality_gates.py, constitution_diff.py, traceability.py
└── tests/                           unittest suite, no LLM required

.claude/commands/spec-master.md      Claude Code entrypoint ($ARGUMENTS, AskUserQuestion) — pointer only
.claude/skills/spec-master/SKILL.md  Claude Code skill auto-discovery pointer — same, no logic
.github/skills/spec-master/SKILL.md  GitHub Copilot entrypoint (/spec-master) — pointer only
.agents/skills/spec-master/SKILL.md  OpenAI Codex CLI entrypoint ($spec-master)
.agents/agents/spec-master/agent.md  Antigravity (agy) custom agent, selected through /agents
.qwen/commands/spec-master.md        Qwen-compatible adapter pointer — pointer only
```

None of the platform directories contain Python, templates, or
protocol content — each is a short file that says "read `spec-master/PROTOCOL.md`,
call `spec-master/lib/cli.py`, and here's how *this* platform asks the user /
resolves its invocation argument." The Copilot and Codex entrypoints are
real, working files (not placeholders): they follow the exact
`speckit-<command>/SKILL.md`-style skills layout Spec Kit itself installs
for each of those agents. Antigravity (`agy`) also gets a dedicated custom
agent at `.agents/agents/spec-master/agent.md`, because Antigravity can
route that through `/agents` even when it ignores a slash-command-style
skill. The 30+ long-tail entrypoints are not kept in the source repo root
anymore; they are rendered directly from Spec Kit's own integration registry
(see `spec-master/adapters/generic.md`) when `init.sh link <project>` or
`adapters_gen.py generate` targets a project. That's what "model-agnostic
core" (CLAUDE.md §2) means in practice here: one tested Python core living
outside every platform's own directory, thin platform pointers where the
target agent actually needs them.

The split matters: everything **structural** (state transitions, staleness,
dependency ordering, git-strategy idempotency, which build/test/lint command
actually exists in this repo, constitution heading diff, traceability
rendering, team roles/workstreams/adoption, and delivery metrics) lives in
`spec-master/lib/` and is unit-tested. Everything
**semantic** (reading the user's context, writing spec/plan/tasks content,
resolving business ambiguity) stays in the agent's prompt, driven by
`spec-master/PROTOCOL.md` and the `spec-master/templates/prompts/*.md`
skeletons. Every adapter (Claude Code, Copilot, Codex, Qwen-compatible
shells — see
`spec-master/adapters/`) reuses the exact same `spec-master/lib/cli.py`.

Call the core directly for any structural question, from the repo root:

```bash
python3 spec-master/lib/cli.py discovery scan --path .
python3 spec-master/lib/cli.py gates detect --path .
python3 spec-master/lib/cli.py git-strategy plan --strategy trunk --feature-name "Demo feature"
python3 spec-master/lib/cli.py team intake
python3 spec-master/lib/cli.py team adopt
python3 spec-master/lib/cli.py metrics record-round --round-id r1 --phase tasks --started-at 2026-08-31T10:00:00Z --ended-at 2026-08-31T10:10:00Z
```

## Team Mode

Team Mode models a delivery organization around the Spec Kit workflow:
Product Owner, Scrum Master, Architect, Tech Lead, UI/UX + Brand, Backend
Dev, Frontend Dev, Fullstack Dev, QA, DevOps, Infrastructure, and Security.
Spec Master remains the orchestrator. The Tech Lead owns technical
decomposition, file/package ownership, code-conflict resolution, and final
integration approval. Dev agents implement assigned packages only, and every
package requires review by a different dev agent before QA validation.

For a project that already has `.spec-master/state.json`, Team Mode adoption
is state-preserving and additive. `team adopt` produces the checklist for
mapping existing specs/tasks into `.spec-master/workstreams.json` without
restarting, rewriting constitution, or invalidating completed phases unless
normal fingerprint comparison proves a concrete artifact stale.

## Metrics

Each significant round can be recorded with `metrics record-round`: intake
batches, Spec Kit phases, workstream packages, peer reviews, QA validation,
and quality gates. The row stores timestamps, token counts when the adapter
exposes them, completed packages/features, tokens per minute, packages per
hour, and features per hour. If the platform does not expose exact token
counts, adapters must record `0` and note that limitation instead of
guessing. `metrics summarize` feeds the final report.

## Global installation

By default the engine only exists inside this repo (`spec-master/`), and the
project-local entrypoints (`.claude/`, `.github/`, `.agents/`) only work
here. `./init.sh` makes it available everywhere:

```bash
./init.sh                    # mirror the engine to ~/.spec-master-engine,
                              # register GLOBAL entrypoints for the documented agents,
                              # then link + check Spec Kit for $PWD
./init.sh --project <path>   # same, targeting <path> instead of $PWD
./init.sh --engine-only      # only (re)install the global engine + the 3
                              # global entrypoints, skip the per-project steps
./init.sh link <path>        # only run the per-project steps (Copilot/Codex
                              # pointers + Spec Kit check) for <path>
```

What it does:

- Mirrors `spec-master/` to `~/.spec-master-engine` (idempotent — a marker
  file lets re-runs update in place without prompting; if a *different*,
  pre-existing `~/.spec-master-engine` is found, it asks before overwriting).
- Writes a **global** entrypoint for every adapter, each in that agent's own
  documented personal/user-level skill directory:

  | Agent | Global entrypoint |
  |---|---|
  | Claude Code | `~/.claude/commands/spec-master.md`, `~/.claude/skills/spec-master/SKILL.md` |
  | GitHub Copilot CLI | `~/.copilot/skills/spec-master/SKILL.md`, `~/.copilot/agents/spec-master.agent.md` |
  | OpenAI Codex CLI | `~/.codex/skills/spec-master/SKILL.md` |
  | shared fallback (both Copilot CLI and Codex CLI also scan this) | `~/.agents/skills/spec-master/SKILL.md` |
  | Qwen-compatible environments | adapter-local pointer only; no global install path is assumed |

  From then on, `/spec-master <context-file>` (or `$spec-master`, depending
  on the agent) works in **every** project on the machine, for every one of
  the documented agents, the same way any other user-level skill does for that
  tool. No per-project copy needed, and no unrelated files are touched (e.g.
  `~/.agents/.skill-lock.json`, if some other tool manages skills there, is
  left alone — Spec Master only adds its own subdirectory next to it).
- `init.sh link <project>` additionally generates a small **per-project**
  pointer (`.github/skills/spec-master/SKILL.md`,
  `.agents/skills/spec-master/SKILL.md`) — useful for teammates who haven't
  run `init.sh` themselves, or a repo that wants the pointer committed
  instead of relying on every contributor's global install.
- Checks whether the target project has Spec Kit initialized (`.specify/`);
  if not, and `specify` (or `uvx`) is on `PATH`, offers to run
  `specify init --here` right there. Non-interactively (no TTY/stdin), it
  degrades to skipping the init and printing the manual command instead of
  hanging or crashing.

If you run `/spec-master` directly (no `init.sh` beforehand) in a project
that hasn't been Spec-Kit-initialized, the agent asks the same question
itself (`PROTOCOL.md` Step 2) — `init.sh` and the agent-driven protocol
cover the same check on two different paths (shell-time vs. run-time).

## Analyze repair loop

`/speckit.analyze` never gets skipped. On findings, Spec Master repairs the
artifact responsible (spec/plan/tasks — never just the report) and re-runs
analyze, up to 3 cycles (`spec-master/lib/cli.py state analyze-cycle`). If
still failing after 3 cycles, the feature transitions to `BLOCKED` and is
escalated to the user instead of looping forever or masking the problem.

## Stopping conditions

- **SUCCESS**: constitution valid, all selected features implemented, every
  acceptance criterion traced, analyze has no blocking findings, all
  blocking quality gates pass, no unresolved `SPEC_DRIFT`.
- **BLOCKED**: unresolvable ambiguity, constitutional conflict, a destructive
  architectural decision needing approval, a missing dependency/credential/
  service, a quality gate repeatedly failing without a safe fix, or spec
  drift needing a product decision.
- **FAILED**: Spec Kit unavailable (not installed, and the user declined the
  offer to initialize it, or no `specify`/`uvx` was reachable at all),
  repository inconsistent beyond safe repair, implementation can't satisfy
  acceptance criteria, or critical tests remain failing.

## Tests

```bash
python3 -m unittest discover -s spec-master/tests -v
```

The tests cover state transitions (including the 3-cycle repair cap and the
rule that a phase can't start before its predecessor `PASSED`), fingerprint
staleness propagation, repo discovery (never inventing a command for a stack
that has no manifest present), dependency ordering (including cycle
detection), git-strategy idempotency and identifier preservation, quality
gate detection per stack, constitution structural diffing, and traceability
rendering, plus Team Mode and metrics primitives.

## Example walkthrough

`spec-master/tests/fixtures/demo-context.md` is a small, stack-agnostic
context describing a "notification preferences" feature set with two
features, one depending on the other. Running the deterministic core
against it:

```bash
python3 spec-master/lib/cli.py features order --file features.json
# {"order": ["notification-preferences-center", "digest-fallback"]}

python3 spec-master/lib/cli.py git-strategy plan \
  --strategy git-flow --feature-name "Notification preferences center"
# {"strategy": "git-flow", "create_branch": true,
#  "branch": "feature/notification-preferences-center", ...}
```

`/spec-master spec-master/tests/fixtures/demo-context.md` run for real
would continue through discovery → Spec Kit check + git-strategy question →
normalized docs → constitution → the two features in that order → quality
gates → final report. This repo itself has the `specify` CLI available but
hasn't run `specify init --here` (no `.specify/` here — it's a skill source
repo, not a Spec-Kit-managed project), so a real end-to-end run against it
would hit Step 2's Spec Kit check first and either initialize it (if
confirmed) or correctly stop at `FAILED — Spec Kit unavailable` (if
declined) per the stopping conditions above — that's the intended behavior,
not a bug.

## Limitations (this increment)

- Features execute sequentially even when independent; the dependency graph
  already supports future parallelization but nothing parallel is wired up.
- No Jira/Azure DevOps/GitHub Issues integration, no dashboard/UI, no
  dedicated MCP — out of scope per the CLAUDE.md FUTURE list.
- `constitution diff` and the analyze/repair loop give structural signals
  (heading-level diff, cycle counting); the semantic judgment of whether a
  MODIFICATION is actually safe still belongs to the agent, not the core.
- Not validated end-to-end against a real Spec Kit-initialized project (this
  source repo itself is intentionally left un-initialized); validated at the
  core-logic level via the unit test suite, manual CLI smoke tests, and
  `init.sh` runs against scratch directories with a fake `$HOME` instead.
- `init.sh`'s global install is real for the documented agents: Claude Code
  (`~/.claude/commands`, `~/.claude/skills`), GitHub Copilot CLI
  (`~/.copilot/skills`, `~/.copilot/agents/*.agent.md`), and OpenAI Codex CLI
  (`~/.codex/skills`), plus a shared `~/.agents/skills` fallback both
  Copilot CLI and Codex CLI also scan. Confirmed by inspecting an actual
  machine with all three tools installed (existing sibling skills/agents in
  those directories), not just vendor docs. `init.sh link` on top of that is
  for teammates without a global install, or a repo that wants the pointer
  committed.
- The Copilot (`.github/skills/spec-master/SKILL.md`) and Codex
  (`.agents/skills/spec-master/SKILL.md`) entrypoints were built against
  Spec Kit's current documented install conventions for those agents
  (`.github/skills/<name>/SKILL.md` / `.agents/skills/<name>/SKILL.md`,
  skills-mode invocation) rather than exercised inside an actual Copilot or
  Codex session — only the Claude Code entrypoint has been run in this
  conversation. If either agent's real skill-loading behavior differs from
  the documented convention, only the thin entrypoint file needs to change;
  the shared core and protocol do not.
