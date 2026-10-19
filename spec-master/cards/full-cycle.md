# Spec Master: full-cycle router

This is the whole of what you need to start. `PROTOCOL.md` is the source of
truth, but you do **not** read it in full: for the step you are on, print only
its section with `python3 spec-master/lib/cli.py protocol show --section <heading>`
(add `--tree` for the subsections; `protocol sections` lists every heading with
its size). Paths starting with `spec-master/` mean the engine directory.

## Rules that always apply

- The context file is the source of truth. Never invent requirements,
  criteria, files or integrations; tag facts `EXPLICIT`, `INFERRED`,
  `DISCOVERED_FROM_CODEBASE` or `UNRESOLVED`
  (`protocol show --section "1. Anti-hallucination rule"`).
- The core (`python3 spec-master/lib/cli.py ...`) decides state, order, gates,
  fingerprints, risk tiers and traceability; you read the repository, write the
  documents, run the Spec Kit phase skills and report. Never re-derive what the
  core answers (`protocol show --section "0. Division"`).
- Ask the user only at the gates the protocol names, every question of a gate
  in one message (`protocol show --section "4. Progress messaging"`).
- Print short `[Spec Master] ...` progress lines between phases, never raw
  internal output.
- Irreversible actions (push, PR, publish, deploy) need the user's explicit
  yes. Never edit `state.json`, `rounds.json` or traceability files by hand.

## Steps: read the section for the current one

| Step | When | Section to print |
|---|---|---|
| -1 | no context file given | `protocol show --section "Step -1"` |
| 0 | always first: resolve input, resume or restart | `protocol show --section "Step 0"` |
| 1 | discovery (read-only) | `protocol show --section "Step 1"` |
| 1, 4 | existing code / empty repo | `cards/brownfield.md` / `cards/greenfield.md` (proposals only) |
| 2 | Spec Kit available, Git strategy (once, batched) | `protocol show --section "Step 2"` |
| 3 | normalized context layer | `protocol show --section "Step 3"` |
| 4 | constitution | `protocol show --section "Step 4"` |
| 5 | feature discovery and order | `protocol show --section "Step 5"` |
| 6 | per feature: the phase loop below | `protocol show --section "Step 6"` |
| 6 | risk tier and ceremony | `protocol show --section "Risk-adaptive ceremony" --tree` |
| 6 | event hooks | `protocol show --section "Event hooks"` |
| 7 | quality gates | `protocol show --section "Step 7"` |
| 8 | report and traceability | `protocol show --section "Step 8"` |
| 8 | optional PR step | `protocol show --section "Optional PR step"` |
| any | idempotency, staleness | `protocol show --section "3. Idempotency"` |
| any | Team Mode (only when asked or adopted) | read `docs/team-mode.md` once |

## The phase loop (Step 6), one call per boundary

For each feature in the resolved order, phases are
`specify -> clarify -> plan -> tasks -> analyze -> implement -> validate`.

1. Open the phase:
   `python3 spec-master/lib/cli.py state advance --path .spec-master/state.json --feature <id> --phase <phase> --status RUNNING`.
   The answer's `next` block gives the phase, the ceremony tier and a
   model/effort `hint`: use it to pick the cheapest model class that fits.
2. Fill `templates/prompts/<phase>.md` and run the installed Spec Kit phase
   skill (`discovery scan` reports it under `speckit_phase_entrypoints`) with
   that prompt. A missing skill is `FAILED`, never simulated.
3. Close the phase in ONE call, with the round and the traceability rows:
   `python3 spec-master/lib/cli.py state advance --path .spec-master/state.json --feature <id> --phase <phase> --status PASSED --round-json '{"round_id":"...","started_at":"...","ended_at":"..."}' --trace-json '[{...}]'`.
   `PASSED` needs the phase artifact in the feature's `spec_directory`; the core
   refuses otherwise. The answer says what comes next; `next: null` means the
   feature is `COMPLETED`.
4. `clarify` may be `SKIPPED` only when the tier's profile says `skippable`.
   `analyze` is never skipped: on findings repair the artifact and re-run,
   counting with `state analyze-cycle --feature <id> --action increment|check`
   (3 cycles, then `BLOCKED` and escalate). On XS/S, `next.light_analyze` is a
   deterministic pre-check: fix what it flags first, then run `/speckit.analyze`.
5. Round numbers come from the host (`telemetry ingest ... --append`) or are
   typed with 0 tokens; never invent them.

Resume after a compaction or a restart: `state show --summary` and continue
with the `next` block of the last `state advance`.
