# Research: Guarded No-op Phase Validation

## 1. `contract_version` semantics (NPV-010, §11-12)

**Decision**: `phase_contracts.py` exposes a single module-level constant
`PHASE_CONTRACT_VERSION = 2` (an integer, matching the spec's own JSON
example `"contract_version": 2` literally). Every new attempt record
written by `controller.py` stores this constant's current value as
`contract_version`. `resume`'s revalidation trigger ("a versão do
contrato de fase mudou", §11) compares the last attempt's stored
`contract_version` against the current `PHASE_CONTRACT_VERSION`: if the
stored value is missing (attempts written before this feature shipped,
i.e. "version 1" implicitly — Feature 1 never persisted a version at
all) or lower than the current constant, the contract is considered
changed.

**Rationale**: The spec's own worked example already shows a plain
integer (`2`), strongly implying a manually-maintained constant bumped by
whoever changes the phase-contract semantics — not a computed hash
(which the spec never mentions and which would be harder to reason about
for a human reading a diff). "2" lines up naturally with this being the
second phase-contract shape (1 = Feature 1's original
always-require-a-change contract, implicit; 2 = this feature's
policy-aware contract).

**Alternatives considered**: A hash of `phase_contracts.py`'s source or
of the policy/artifact tables — rejected as over-engineered for a signal
that only needs to answer "did the contract change since this attempt,
yes or no" and that a human bumps deliberately, not automatically.

## 2. "Evidence of a rejected attempt" for producer-phase artifact trust (§9 item 4)

**Decision**: Existing artifacts are trusted for a producer-phase
no-change PASS only if **every** prior attempt recorded for that phase
(across the whole attempt history, including attempts from before a
resume) has an empty `forbidden_writes` list and does not contain
`out_of_project_write` in its `events` list. A single historical
rejection for either reason permanently disqualifies trusting that
phase's existing artifacts until a fresh, clean attempt actually
(re)writes them.

**Rationale**: Both fields already exist in every `PhaseAttempt` record
(`forbidden_writes`, `events` — Feature 1, `data-model.md`). Reusing them
avoids inventing a new signal, and choosing an "any single violation ever
disqualifies" (rather than "only the immediately preceding attempt")
policy is the conservative, safer reading of "não houver evidência" —
an attacker or a badly-behaving model could otherwise game the trust
check by making one bad write, then one clean no-op attempt, expecting
the earlier tampering to be forgotten.

**Alternatives considered**: Checking only the single most recent
attempt — rejected as strictly weaker security-wise, and not clearly
what "não houver evidência" implies (it says "evidência", not "a
tentativa imediatamente anterior").

## 3. `reason`/`outcome` for a producer phase's retry-trust success

**Decision**: When a `produce-or-update` phase (e.g. `tasks`) passes on a
retry without changing its artifact this attempt — because an earlier,
not-yet-promoted attempt already produced it and the trust check in
item 2 above holds — the attempt record uses the same
`reason: "valid_noop"` / `outcome: "no_changes_required"` pair the spec
defines for `clarify`/`analyze` (§5, §8), not a new, unlisted term.

**Rationale**: §10 states its table is meant to standardize "os motivos
retornados por `phase_runner`" — introducing a term not in that table
would contradict the spec's own intent to have one closed vocabulary
(and the anti-hallucination rule against inventing facts not supported
by the source). The observable shape of the outcome is identical to the
inspection case (`PASSED`, no filesystem change this attempt, no new
content produced) even though the *reason* the check exists differs
(trusting a previous attempt vs. an inspection concluding nothing needs
fixing) — reusing the term is the reading most consistent with the
spec providing exactly one non-`unchanged_artifact` success path for a
no-change attempt. `unchanged_artifact` (§10) remains reserved for the
**failure** case: a producer phase ending without a change when the
trust conditions are *not* met.

**Alternatives considered**: A new term such as
`prior_attempt_validated` — rejected: §10's table is explicitly
presented as the complete, standardized vocabulary, and the anti-
hallucination rule (never invent facts/terms not supported by the
source) weighs against adding one un-sourced value. If this
choice proves confusing in practice, a future increment can extend the
vocabulary explicitly, as its own scoped change.

## 4. Active-feature resolution scope (§7, §8)

**Decision**: `resolve_active_feature_dir(project)` (new, in
`phase_contracts.py`) is used only for the two no-op decision paths this
feature adds — `clarify`'s (§7, explicit hard requirement) and
`analyze`'s (§8, "da feature ativa" wording) — not for the general
"does this phase's required artifact exist/is it non-empty" checks used
by every other phase, which continue to use the existing
`specs/*/...` glob patterns in `PHASE_ARTIFACTS`.

**Rationale**: The spec scopes the active-feature-resolution requirement
explicitly to `clarify` (§7) and implies it for `analyze` via "da feature
ativa"; broadening it to `plan`/`tasks`/`implement`/`validate` as well
is not requested anywhere and would be scope creep beyond this bug fix
("não amplie escopo além desta feature"). This repository is itself a
live example of why the distinction matters — it now has two real
`specs/*/` directories (`001-guarded-mode-controller`,
`002-guarded-noop-phase-validation`), so an ambiguous glob is not a
hypothetical risk here.

## 5. `phase_result` structured-block parsing (§6, NPV-004)

**Decision**: New module `spec-master/lib/phase_result.py` scans the
transcript text for every syntactically balanced `{...}` span (matching
braces, not regex-guessing the internal shape), attempts
`json.loads()` on each, and keeps the **last** one that parses to a
`dict` containing a `"phase_result"` key whose value is one of
`artifact_updated | no_changes_required | user_decision_required |
failed`. Everything else (unparsable JSON, objects without a
`phase_result` key, or an unrecognized value) is ignored — never
evaluated or executed, per the NFR "O parser do resultado estruturado
não deve executar conteúdo do transcript" and "JSON inválido deve ser
rejeitado com segurança."

**Rationale**: A brace-matching scan is the only reliable way to extract
a `{"phase_result": ..., "checks": {...}}` object correctly when it
contains nested objects (like `checks`) — a naive non-nested regex like
`\{[^{}]*"phase_result"[^{}]*\}` would fail to capture the `checks`
sub-object present in every example in the spec. `json.loads` never
executes code (unlike `eval`), satisfying the safety NFR directly.

**Alternatives considered**: A single "find last `{` to last `}`"
heuristic — rejected, it would misparse a transcript containing any
other JSON-shaped text after the real result block (e.g. a quoted
example in the agent's own explanation).

## 6. How `resume`'s contract-revalidation actually re-evaluates (§11, NPV-010)

**Decision**: `resume` performs a cheap, no-subprocess check per phase
*before* entering the normal attempt loop, only when all four §11
conditions hold (contract version outdated on the last attempt, its
`reason` was `missing_artifact`/`unchanged_artifact`, the required
artifact exists, the context fingerprint is unchanged). The check:

1. Re-reads the last attempt's preserved transcript file (FR-011 already
   guarantees it still exists) and re-parses it with the *current*
   `phase_result.py`.
2. If a valid structured result is found and the phase's no-op predicate
   (`clarify_result_ok`/`analyze_result_ok`) accepts it against the
   filesystem *as it stands right now*, append a new `PASSED` attempt
   record (`reason: "valid_noop"`, `source: "contract_revalidation"`) —
   no subprocess is spawned.
3. If the old transcript has no parseable structured result (the common
   case for any attempt made *before* this feature shipped, like the
   real `qwen-greeting-api` regression — the agent was never asked to
   emit one), the cheap check does not apply, and the phase falls
   through to the **normal** attempt loop, spawning a real new attempt
   under the new contract.

**Rationale**: §11's own wording offers both paths — "a fase pode passar
somente se... [a] a tentativa atual produzir um resultado estruturado"
(§9) describes evaluating an existing artifact, while spec.md's Cenário
G says the blocked attempt "deve ser reavaliada **ou repetida**" under
the new contract. A pre-check that tries the cheap path first and falls
back to a genuine retry covers both without guessing which one always
applies — and correctly handles the real regression case, whose old
transcript predates this feature and therefore has no structured result
to reinterpret.

**Alternatives considered**: Always re-running the phase on `resume`
(dropping the cheap path entirely) — rejected: it would spend a new,
potentially slow/expensive real-model attempt even when the existing
artifact is already provably valid under the new rules, defeating the
whole point of "reavaliar" as distinct from "repetir." Always trying to
reinterpret the old transcript and erroring if it lacks a structured
block — rejected: it would leave the real regression case (Cenário G)
unfixable, since that transcript can never retroactively gain a
structured block it was never asked to produce.

## 7. Decision priority order (fixed during `analyze`, finding C1)

**Decision**: `phase_runner.run_phase`'s pass/fail decision evaluates, in
this fixed order, stopping at the first branch that applies:

1. Hard-fail checks (`timed_out`, `exit_code != 0`, `fake_tool_markers`,
   `forbidden_writes`, `artifact_wrong_location`, `blocking_gate_failed`)
   — unchanged from Feature 1, always win.
2. `outcome == "user_decision_required"` — always `FAILED`/
   `reason: "user_decision_required"`, **even if `required_changed` is
   `True`** (the phase may have touched a minor file and still need a
   human decision; the pause signal must never be silently skipped just
   because *something* changed).
3. `required_changed == True` — Feature 1's existing formula
   (still AND'd with `missing_artifacts`/`placeholder_artifacts` being
   empty), unchanged.
4. `PHASE_POLICY[phase] == "inspect-or-update"` and `required_changed ==
   False` — the no-op decision path (research.md items 3-5).
5. `PHASE_POLICY[phase] == "produce-or-update"` and `required_changed ==
   False` — the retry-trust path (research.md item 2).

**Rationale**: A structured `user_decision_required` claim is the
agent's most explicit, most important signal — it means the phase
cannot self-resolve at all, regardless of what else happened to the
filesystem this attempt. Checking it right after the hard-fail tier
(before any success path) is the only ordering that can't accidentally
mask it.

## 8. Where the no-op decision logic lives

**Decision**: The per-phase no-op eligibility checks (§5's 11 conditions
for `clarify`, §8's 7 conditions for `analyze`) live in `phase_runner.py`
as two dedicated functions
(`_clarify_noop_eligible`/`_analyze_noop_eligible`), called from
`run_phase` only when `PHASE_POLICY[phase] == "inspect-or-update"` and
`required_changed` is `False` this attempt. `phase_contracts.py` gains
only the static data these functions need
(`PHASE_POLICY`, `resolve_active_feature_dir`,
`clarify_result_ok`/`analyze_result_ok` pure predicates over an already-
parsed `phase_result` dict) — it stays free of I/O beyond path
resolution and file reads, matching its existing "deterministic,
unit-testable, no subprocess" character (Constitution Principle I).

**Rationale**: Keeps the module boundary Feature 1 already established:
`phase_contracts.py` = static contract + structural predicates,
`phase_runner.py` = the attempt-level decision that combines them with
the actual subprocess/transcript output. Splitting the *predicates* into
`phase_contracts.py` (testable in isolation, per `test_phase_contracts.py`
§16 items 5-6) while keeping the *policy-branching decision* in
`phase_runner.py` avoids duplicating the existing `PASSED`/`FAILED`
computation that already lives there.
