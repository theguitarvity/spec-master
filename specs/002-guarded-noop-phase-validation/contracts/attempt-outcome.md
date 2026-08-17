# Contract: attempt `status` vs. `outcome` vs. `reason`

Three separate fields on every `PhaseAttempt` record, each answering a
different question — kept distinct precisely so the final report can
differentiate `artifact_updated` from `no_changes_required` (§18
acceptance criterion 9) without conflating "did it pass" with "why."

| Field | Answers | Values |
|---|---|---|
| `status` | Did the controller promote this attempt? | `PASSED` \| `FAILED` |
| `outcome` | What did the phase's own structured result claim happened? | `artifact_updated` \| `no_changes_required` \| `user_decision_required` \| `failed` \| `null` (no structured result found) |
| `reason` | The controller's own, filesystem-grounded classification of why `status` is what it is. | see §10's table (`spec.md`) |

## Combinations that can occur

| status | outcome | reason | Meaning |
|---|---|---|---|
| `PASSED` | `artifact_updated` | `null` | Ordinary Feature-1-style pass: the phase changed a required artifact and every check succeeded. |
| `PASSED` | `no_changes_required` | `valid_noop` | An `inspect-or-update` phase (or a `produce-or-update` phase on a trusted retry — research.md item 3) validly concluded nothing needed changing. |
| `FAILED` | `no_changes_required` | `phase_result_invalid` | The phase *claimed* no change was needed, but the filesystem check disagrees (e.g. a `[NEEDS CLARIFICATION]` marker is still present) — Cenário B. |
| `FAILED` | `null` | `phase_result_missing` | No valid structured block was found in the transcript at all, and the attempt made no artifact change either. |
| `FAILED` | `no_changes_required` | `unchanged_artifact` | A `produce-or-update` phase ended without a change and the retry-trust conditions were **not** met. |
| `FAILED` | `*` | `forbidden_write` | Any write outside the phase's allowlist — always wins over a `no_changes_required` outcome (Cenário D), regardless of policy. |
| `FAILED` | `*` | `timeout` | Timeout always fails, regardless of `outcome` — a timed-out process's structured result (if any) is not trusted (§14 NFR, spec.md's "considerar timeout como no-op válido" non-goal). |
| — (workflow `PAUSED`) | `user_decision_required` | `user_decision_required` | The phase reports it needs a human decision. A `PhaseAttempt` record is still appended (transcript/audit trail, FR-011) and the workflow transitions to `PAUSED` immediately, but this record is excluded from the `max_attempts_per_phase` count — the next real attempt after `resume` reuses the same attempt budget (Cenário F). |

`reason` is always the authoritative field for *why* `status` is what it
is; `outcome` is preserved verbatim for the final report and for
debugging, but is never itself sufficient to promote or fail an attempt
without the corresponding filesystem-grounded checks agreeing.
