# Research: Guarded Mode Controller

All items below resolve a "NEEDS CLARIFICATION" left open by
`.spec-master/context/tech-stack.md` or a design choice not pinned down by
`docs/spec-master/guarded-mode-spec.md` at the literal-requirement level.

## 1. Scope boundary: what does THIS increment build vs. defer

**Decision**: This increment delivers the deterministic core (`execution_mode.py`,
`phase_contracts.py`, `phase_runner.py`, `controller.py`) and the OpenCode
adapter as a **standalone, fully-tested, opt-in tool** — invokable directly
via `python3 spec-master/lib/controller.py run|resume|status`. It does
**not** wire `--mode` parsing into the `/spec-master` agent-level command,
`PROTOCOL.md` Step 0, or any adapter file, and does **not** change the
default behavior of `/spec-master` (still fully agentic/native today).

**Rationale**: `docs/spec-master/guarded-mode-spec.md` §19 ("Migração")
specifies exactly this sequencing: (1) preserve the protocol/native mode
as-is, (2) incorporate the OpenCode runner into the new phase contract,
(3) add `guarded` without changing the default, (4) validate with fake
agents and the real `qwen-todo-api` case, and only *after* — as a separate,
later step — (5) change the default to `auto` and (6) update
README/adapters/installer. Steps 5-6 explicitly happen "depois dos
testes" (after the tests), i.e. as a follow-up once this deterministic
core is proven. Building the agent-level wiring in the same pass as the
core would violate Constitution Principle VI (native must not change
behavior) unless done with equal rigor, which is out of proportion to one
increment, and would silently expand scope beyond what
`.spec-master/context/app-features.md` scoped as this feature's Feature 1
non-goals ("suportar inicialmente todos os agentes... apenas OpenCode").

**Alternatives considered**: Wiring `--mode` into `PROTOCOL.md`/adapters in
the same pass — rejected because it multiplies surface area (every
adapter file, README, global installer) for a change the source spec
itself sequences as a distinct, later step, and because GM-001/GM-002 are
satisfiable and independently testable at the `controller.py` CLI layer
alone (see item 2).

**Consequence for GM-001/GM-002**: satisfied at the `controller.py run`/
`resume` CLI surface, which is itself a documented, testable entrypoint
per `docs/spec-master/guarded-mode-spec.md` §4 ("CLI determinística").

## 2. `controller.py` and `--mode native`

**Decision**: `controller.py run`/`resume` accept `--mode` with choices
`native`, `guarded`, `auto` (so the flag itself is never rejected as
invalid — satisfying GM-001's "aceitar native, guarded e auto" literally),
but `--mode native` makes the controller print a clear message ("native
mode does not use this controller; run the agent-driven /spec-master
protocol directly") and exit non-zero instead of pretending to guard
anything.

**Rationale**: `native` means "the agent drives everything per
`PROTOCOL.md`, no controller involved" — that is the whole point of the
mode. A controller command that silently no-ops for `native` would be
dead code with no test value, and would risk drifting from the real native
behavior defined in `PROTOCOL.md` (violates Principle I: the core must not
re-derive/duplicate what already exists elsewhere).

**Alternatives considered**: Rejecting `native` as an invalid choice for
`controller.py` — rejected because GM-001 says the three modes must be
*accepted*, and a `choices=` accept + explicit informative exit is a
stronger, more literal reading than narrowing the CLI's vocabulary.

## 3. Session isolation for the OpenCode adapter

**Decision**: "Sessão nova, sem histórico de fases anteriores" (§5 step 5)
is achieved by construction: every phase attempt is a **new
`opencode run` subprocess invocation** (already true of the existing,
uncommitted `opencode_runner.py`), with no `--session`/`--continue` flag
and no session id reused across phases or attempts. `opencode run` is a
one-shot, non-interactive invocation; process boundary == session
boundary.

**Rationale**: Matches the already-written `opencode_runner.py` exactly
(one `subprocess.run(["opencode", "run", ...])` per invocation, one
transcript file per invocation) — no new mechanism needed, and this
resolves the "Open Technical Question" flagged in
`.spec-master/context/tech-stack.md`.

**Alternatives considered**: An explicit OpenCode session-reset API call —
rejected as unnecessary; not finding such an API referenced anywhere in
the source spec, and process-per-phase already gives clean isolation.

## 4. Detecting "implementation before `implement`" (GM-006)

**Decision**: No separate content-sniffing heuristic. A write is
classified as the critical `early_implementation` event when: the phase is
one of `constitution|specify|clarify|plan|tasks|analyze` (i.e. before
`implement`) **and** the write falls outside that phase's allowlist **and**
the changed path's extension is not a documentation/spec/config extension
already implied by the phase's own allowlist (i.e., it looks like it could
be application source rather than a spec/doc/config artifact) — otherwise
it is the weaker `wrong_path` recoverable event.

**Rationale**: The already-written `opencode_runner.py` allowlist table
(`PHASE_ALLOWED_WRITES`) already excludes general source directories from
every pre-`implement` phase, so *any* write of a new source-looking file
before `implement` is already structurally impossible to reconcile with
those allowlists — reusing the same forbidden-write check for GM-005 and
GM-006 avoids a second, independent (and potentially inconsistent)
heuristic, per Constitution Principle I.

**Alternatives considered**: A dedicated file-extension denylist scanned
independently of the allowlist — rejected as redundant; the allowlist
already encodes the same information more precisely (per-phase, not
global).

## 5. Placeholder detection (GM-004, §7)

**Decision**: Reuse the exact mechanism already in `opencode_runner.py`
(`"[PROJECT_NAME]" in text`), extended to an explicit list of the known
unfilled-template markers actually present in this repository's own
`.specify/templates/*.md` (`[PROJECT_NAME]`, `[PRINCIPLE_1_NAME]`,
`[GOVERNANCE_RULES]`, `[FEATURE NAME]`, `[###-feature-name]`, `[DATE]`,
`NEEDS CLARIFICATION`, etc. — DISCOVERED_FROM_CODEBASE), rather than a
generic "any `[BRACKETED]` text" regex.

**Rationale**: A first implementation attempt used a generic bracket
regex and was caught by `test_phase_contracts.py` false-positiving on
this very feature's own `tasks.md`, which legitimately uses `[US1]`,
`[P]`, `[X]` as Spec Kit task-story-label syntax — a correctly-completed
`tasks.md` would have been wrongly rejected as "still containing
placeholders." An explicit list, grounded in the actual templates read
from this repository, avoids that collision entirely while still
covering every real placeholder token, and also matching ordinary
Markdown links (`[text](url)`) safely since it never treats "any bracket"
as suspect.

## 6. Simulated tool-call detection (GM-007)

**Decision**: Reuse `opencode_runner.py`'s existing
`FAKE_TOOL_MARKERS = ("<function=", "<tool_call>", "</tool_call>")`
substring scan over the raw transcript text, unchanged.

**Rationale**: Already implemented, already matches the exact markers
named in `docs/spec-master/guarded-mode-spec.md` §7
("`<function=`, `<tool_call>` ou equivalentes").

## 7. Snapshot scope (NFR: ignore `.venv`, caches, dependencies, own logs)

**Decision**: Extend the existing `snapshot()` ignore list (currently only
`.opencode/node_modules/` and `.spec-master/logs/`) to also skip: `.git/`,
`__pycache__/`, `.venv/`, `venv/`, `node_modules/` (any depth, not just
under `.opencode/`), `.spec-master/failed-attempts/`, and
`.spec-master/state.json` itself (state is never a "changed artifact" from
the model's perspective — the controller, not the model, owns it).

**Rationale**: Directly required by the NFR in
`docs/spec-master/guarded-mode-spec.md` §15 ("Snapshots devem ignorar
`.venv`, caches, dependências instaladas e logs do próprio controlador").

## 8. `run.lock` name, location, and staleness

**Decision**: `.spec-master/run.lock`, a small JSON file
`{"phase": ..., "pid": ..., "started_at": ...}`. A lock is stale when
`now - started_at > phase_timeout_seconds`; `resume`/`run` remove a stale
lock automatically and proceed (logging that it did so), matching the
already-existing (uncommitted) `lock_path.write_text(...)` behavior in
`opencode_runner.py`, extended with a staleness check that file did not
yet have.

**Rationale**: `docs/spec-master/guarded-mode-spec.md` §12 says an
abandoned `run.lock` must be recognized as stale "after the configured
timeout" without naming a separate value — reusing
`phase_timeout_seconds` is the only timeout already defined in scope
(§8), consistent with the Assumption already recorded in
`.spec-master/context/app-features.md`.

## 9. Attempts/state bookkeeping ownership

**Decision**: `controller.py` owns `state["execution"]` and
`state["attempts"][<phase>]` (a flat, phase-keyed list of attempt
records) exactly as shown in the worked example in
`docs/spec-master/guarded-mode-spec.md` §10 — it does not attempt to
also drive the existing per-feature `state["features"][*]["phases"]`
machinery in `state.py`. It calls `state_mod.transition_phase()` for the
*active feature* only when a controller-run phase corresponds 1:1 to that
feature's current phase (i.e. when the controller is invoked as part of a
`/spec-master` per-feature loop) — for a standalone controller run (no
active feature context), only the top-level `attempts`/`execution` slices
are written.

**Rationale**: Matches the literal state schema shown in the source spec
(§10) without inventing a parallel structure; keeps `controller.py`
usable both standalone (this increment's test surface) and, in a future
increment, wired into the existing per-feature loop, without a rewrite.

## 10. Language/runtime baseline

**Decision**: Python 3.14 (matches this repository's interpreter,
`python3 --version` → 3.14.7), stdlib only; tests via `unittest`
(`python3 -m unittest discover -s spec-master/tests -v`), matching every
existing module in `spec-master/lib/`.
