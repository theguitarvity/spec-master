# Feature Specification: Spec Kit Tracker Orchestration

**Feature Branch**: `005-speckit-tracker-orchestration` (trunk-based: no dedicated branch created, isolated logically under this directory)

**Created**: 2026-09-26

**Status**: Draft

**Input**: User description: "Orquestrar as integrações de tracker já existentes no ecossistema Spec Kit (Jira, Azure DevOps, Linear, GitHub Issues) em vez de construir integrações próprias do zero, reaproveitando/estendendo a skill speckit-taskstoissues já existente." (docs/market-benchmark-roadmap.md, Tier 1, item 3)

## Grounding (constitution Principle VI)

- `.claude/skills/speckit-taskstoissues/SKILL.md` already exists in this repository and is a fully
  working GitHub Issues integration: it converts `tasks.md` lines into GitHub issues titled
  `T001: <description>`, dedupes against existing issues by matching `\bT\d{3,}\b` in issue titles,
  refuses to run unless `git config --get remote.origin.url` is a GitHub URL, and honors
  `.specify/extensions.yml` `before_taskstoissues`/`after_taskstoissues` hooks. This is the only
  tracker extension actually installed in this repository today.
- `spec-master/lib/discovery.py::scan()` already establishes the exact detection precedent this
  feature must follow: every signal it reports (`stacks`, `ci_present`, `speckit_commands`,
  `speckit_command_paths`, ...) is backed by a manifest file that actually exists on disk — nothing
  is inferred or assumed present. It already walks three parallel integration directories
  (`.claude/commands/`, `.opencode/commands/`, `.qwen/commands/`) looking for `speckit.*.md` files,
  which is the same multi-integration directory pattern a tracker-skill scan needs.
- Constitution **Principle VII (Reuse the Ecosystem Before Reimplementing It)**: before adding a new
  integration (Jira, Azure DevOps, Linear, GitHub Issues), an existing Spec Kit extension/skill that
  already provides it MUST be reused or extended instead of building a parallel implementation.
  Because only `speckit-taskstoissues` (GitHub Issues) is actually installed anywhere this codebase
  has visibility into, this feature's own test/acceptance evidence can only demonstrate detection and
  orchestration of that one real extension — the Jira/Azure DevOps/Linear paths are exercised through
  the same generic, evidence-based detection mechanism, not through invented fixtures claiming those
  trackers are installed when they are not (this would itself violate the "never invents presence"
  acceptance criterion).
- Constitution **Principle VIII (Auto-Detected Quality Gates, Never Hardcoded)**: `quality_gates.py`
  is the existing precedent for "detect from the target repository's own configuration, promote to a
  first-class capability, never hardcode" — this feature applies the same detect-then-surface shape
  to tracker skills instead of build/test/lint commands.
- `spec-master/lib/traceability.py` has a fixed 8-column row schema
  (`requirement, source, feature, spec, plan, task, test, status`); `add_row()` normalizes any input
  dict to exactly those columns, silently dropping anything else. There is currently no column to
  carry a synced issue's link or id.
- Constitution **Principle I** (deterministic core vs. agent semantic responsibility): pure Python in
  `spec-master/lib/` cannot itself invoke a Claude Skill (e.g. `/speckit-taskstoissues`) — only the
  orchestrating agent can. This mirrors the existing `gates detect` → `policy preflight` →
  agent-executes-only-`allowed:true` shape already used for quality gates in PROTOCOL.md Step 7: the
  core's job is to detect and produce an unambiguous invocation instruction, not to perform the
  invocation itself.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Detect installed tracker extensions without inventing presence (Priority: P1)

Spec Master's `discovery scan` gains the ability to notice that a Spec Kit tracker-orchestration
skill (one that converts tasks into tracker issues/tickets) is installed in the target repository,
by reading the actual `SKILL.md` manifests already on disk under the same integration directories
`discovery.py` already knows about (`.claude/skills/`, `.opencode/skill/`, `.qwen/skill/`). A skill
is only reported when its manifest file exists and its declared metadata indicates tracker/issue-sync
behavior — nothing is assumed present without a file backing it.

**Why this priority**: Every other part of this feature depends on knowing, deterministically, what
is actually installed; acceptance criterion 1 in `.spec-master/context/app-features.md` requires this
detection to "never invent presence."

**Independent Test**: Point `discovery.scan()` at this very repository (which has
`.claude/skills/speckit-taskstoissues/SKILL.md`) and assert it reports exactly one tracker extension
of type `github_issues`; point it at a directory with no `.claude/skills/` at all and assert it
reports an empty list, not an error.

**Acceptance Scenarios**:

1. **Given** a target repository with `.claude/skills/speckit-taskstoissues/SKILL.md` present,
   **When** `discovery scan` runs, **Then** the result includes one tracker extension entry with
   `tracker_type: "github_issues"`, the skill's name, and its path.
2. **Given** a target repository with no tracker-skill manifests anywhere, **When** `discovery scan`
   runs, **Then** the result's tracker extension list is empty and no exception is raised.
3. **Given** a target repository with a skill directory whose `SKILL.md` exists but whose metadata
   contains no tracker/issue-sync keywords, **When** `discovery scan` runs, **Then** that skill is
   NOT reported as a tracker extension (no false positive from directory presence alone).

---

### User Story 2 - Orchestrate a detected extension instead of reimplementing sync (Priority: P1)

Once at least one tracker extension is detected, Spec Master surfaces exactly what the orchestrating
agent needs to actually run it (the skill/command identifier and, once the agent has run it and
captured results, a way to record the resulting issue links). Spec Master itself never talks to
Jira/Azure DevOps/Linear/GitHub's APIs and never reimplements `speckit-taskstoissues`'s dedup-by-task-
id sync logic — it only detects and instructs, then records the outcome.

**Why this priority**: This is the actual "orchestrate, don't reimplement" claim from the roadmap
item and constitution Principle VII; without it this feature would either do nothing useful or
regress into building a parallel tracker integration, which Principle VII explicitly forbids.

**Independent Test**: Given one detected `github_issues` extension, call the orchestration function
and assert its result names the exact skill to invoke and includes no tracker-API call of its own;
record a resulting issue link against a traceability row and assert it renders in the matrix.

**Acceptance Scenarios**:

1. **Given** one detected tracker extension, **When** orchestration runs, **Then** the result
   identifies the skill to invoke (name + path + tracker_type) without Spec Master itself creating,
   updating, or reading any issue over the network.
2. **Given** more than one tracker extension detected (e.g. two different skills both matching
   tracker keywords), **When** orchestration runs, **Then** the result lists all of them rather than
   silently picking one, leaving the choice to the orchestrating agent/user.
3. **Given** an issue link/id the agent obtained after actually running the detected skill,
   **When** it is recorded against a requirement's traceability row, **Then** `traceability render`
   includes that link/id in the rendered matrix without altering any other row's existing columns.

---

### User Story 3 - Absence of any tracker extension never blocks the workflow (Priority: P1)

A target repository with no tracker extension installed at all (the common case, and this
repository's own state for Jira/Azure DevOps/Linear specifically) continues through the full Spec
Master pipeline exactly as it does today — orchestration reports that nothing was found and the rest
of specify/plan/tasks/analyze/implement/validate proceeds unaffected.

**Why this priority**: Acceptance criterion 4 in `.spec-master/context/app-features.md` is explicit:
absence must never block the workflow. This is also the regression-safety guarantee mirroring
feature 2's SC-004 story — a no-op path must stay byte-for-byte a no-op.

**Independent Test**: Run orchestration against a directory with zero tracker skills and assert the
result is `{"orchestrated": false, ...}` with no exception, and that `discovery scan`'s and
`traceability render`'s existing output for every other field is unchanged from before this feature.

**Acceptance Scenarios**:

1. **Given** no tracker extension is detected, **When** orchestration runs, **Then** it returns a
   result with `orchestrated: false` and a human-readable reason, and raises no exception.
2. **Given** no tracker extension is detected, **When** the rest of the pipeline runs, **Then** no
   phase blocks, fails, or is skipped because of the absent integration.

### Edge Cases

- What happens if a detected skill's `SKILL.md` cannot be parsed (malformed YAML front-matter)? It is
  silently excluded from the tracker-extension list (same "skip silently on parse failure" behavior
  `speckit-taskstoissues`'s own hook-checking logic already uses for `.specify/extensions.yml`) —
  never raises, never counts as a false positive.
- What happens if the same tracker skill is installed under more than one integration directory
  (e.g. both `.claude/skills/` and `.opencode/skill/`)? Both are reported as separate entries (they
  are genuinely separate installed files); deduplication across integrations is out of scope, mirroring
  `discovery.py::speckit_commands`'s existing per-integration reporting.
- What happens once the agent actually runs the detected skill and it fails or is skipped (e.g. remote
  isn't a GitHub URL, per `speckit-taskstoissues`'s own guard)? Orchestration recorded only that the
  extension was identified and instructed; the skill's own success/failure is outside this feature's
  boundary, consistent with Principle VII (never reimplement the extension's own logic or its error
  handling).
- What happens to existing traceability rows that never get an issue link? The new `issue` column
  renders as an empty string for them, identical to how every other optional column already renders
  today for rows that don't populate it.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `discovery.scan()` MUST detect installed Spec Kit tracker-orchestration skills by
  reading actual `SKILL.md` files under the known Spec Kit skill directories
  (`.claude/skills/`, `.opencode/skill/`, `.qwen/skill/`) — an extension MUST be reported only when
  its manifest file exists on disk; the system MUST NOT report an extension for a tracker with no
  matching manifest.
- **FR-002**: Detection MUST classify a detected skill's `tracker_type`
  (`jira` | `azure_devops` | `linear` | `github_issues`) from keyword matches against its own
  declared `description`/`name` front-matter only — never inferred from guessing at the target
  repository's other tooling. A skill matching none of these keywords MUST NOT be reported at all
  (Acceptance Scenario 3, data-model.md) — there is no `unknown` value that could be silently
  treated as a real tracker.
- **FR-003**: Detected tracker extensions MUST be exposed as a new, additive `tracker_extensions`
  field in `discovery.scan()`'s return value — MUST NOT change the value or shape of any existing
  field (`stacks`, `ci_present`, `speckit_commands`, etc.), per Principle VI.
- **FR-004**: An orchestration function MUST, given the list of detected extensions, produce an
  invocation instruction per extension (skill name, path, tracker_type, and the literal command the
  agent should run) — MUST NOT itself perform any tracker network/API call and MUST NOT reimplement
  any extension's own task-to-issue sync logic, per Principle VII.
- **FR-005**: When zero tracker extensions are detected, orchestration MUST return a result with
  `orchestrated: false` and a reason, MUST NOT raise, and MUST NOT cause any other phase of the
  pipeline to block, fail, or be skipped.
- **FR-006**: `speckit-taskstoissues` MUST be detected as a `github_issues` tracker extension against
  this repository's own real installed state, with zero modification to
  `.claude/skills/speckit-taskstoissues/SKILL.md` itself (Principle VI: reuse unmodified).
- **FR-007**: `traceability.py`'s row schema MUST gain one new, optional `issue` column (an issue
  link or id) — additive to the existing 8 columns; a row with no `issue` value MUST render exactly
  as it did before this feature (empty cell, no other column affected).
- **FR-008**: All new detection/orchestration logic MUST live in `spec-master/lib/` as pure, testable
  Python exposed via `spec-master/lib/cli.py`, per Principle I, and MUST reuse `discovery.py`'s
  existing manifest-scan pattern (iterate known integration directories, only report what is found)
  rather than building a parallel detection mechanism.

### Key Entities

- **Tracker Extension**: An evidence-backed record `{skill, path, tracker_type, description}` of one
  installed Spec Kit skill whose declared metadata indicates tracker/issue-sync behavior.
- **Orchestration Result**: `{orchestrated: bool, extensions: [Tracker Extension], reason: str|None}`
  — the detect-then-surface-instruction record the agent acts on; never itself the result of a
  tracker API call.
- **Traceability Issue Link**: The new optional `issue` field on a traceability row, populated by the
  orchestrating agent after it runs a detected extension and obtains a resulting issue url/id.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Given this repository's own real state (`.claude/skills/speckit-taskstoissues/SKILL.md`
  present), `discovery scan` reports it as a `github_issues` tracker extension 100% of the time in
  the deterministic test suite.
- **SC-002**: Given a directory with zero tracker-skill manifests, orchestration returns
  `orchestrated: false` with no exception 100% of the time in the deterministic test suite.
- **SC-003**: Zero tracker-sync/HTTP/API logic exists anywhere in `spec-master/lib/` after this
  feature (verified by code inspection — no `requests`/`urllib`/`http.client` usage, no
  reimplementation of `speckit-taskstoissues`'s dedup-by-task-id or issue-creation flow) —
  orchestration only ever detects and instructs.
- **SC-004**: `test_discovery.py` and `test_traceability.py`'s existing tests continue to pass
  unmodified, and `traceability render`'s output for any row without an `issue` value is
  byte-for-byte identical to its pre-feature output (regression coverage; this feature MUST NOT
  modify either existing test file).

## Assumptions

- Only `speckit-taskstoissues` (GitHub Issues) can be demonstrated as an actually-installed tracker
  extension in this codebase's own environment; Jira/Azure DevOps/Linear support is delivered as the
  same generic, evidence-based detection + orchestration mechanism, not as per-tracker special-cased
  code — consistent with "never invents presence" and Principle VII.
  See [[speckit-tracker-orchestration]] for the roadmap item this closes.
- Actually invoking a detected skill (e.g. running `/speckit-taskstoissues`) and capturing its
  resulting issue links is an agent-layer action outside `spec-master/lib/`'s deterministic core,
  per Principle I — this feature's core deliverable is detection + instruction + the traceability
  column to record the outcome, not the invocation itself.
- The exact keyword list used to classify `tracker_type` from a skill's metadata is a Technical
  Context detail resolved during `/speckit-plan` (research.md), not fixed here.
