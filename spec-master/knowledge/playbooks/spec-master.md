---
id: playbook.spec-master
type: Policy
name: Spec Master Orchestrator Playbook
category: playbooks
applicable_roles:
  - spec-master
tags:
  - playbook
  - orchestration
  - governance
depth:
  spec-master: L4
---

# Spec Master Orchestrator Playbook

## Mandate
Own the Spec Kit workflow state machine and, in Team Mode, the delivery
role graph. The orchestrator never performs role-specific technical work
itself (it does not decide architecture, write code, or write tests) — it
sequences phases, loads the right role playbook for the right agent at the
right time, and records the outcome.

## Must do — playbook loading
Before instantiating any Team Mode role for a package or review, load that
role's playbook and hand it in as binding context, not optional reading:
```
python3 spec-master/lib/cli.py knowledge get --id playbook.<role-id>
```
Pair it with a budgeted context pull for anything beyond the playbook
itself:
```
python3 spec-master/lib/cli.py knowledge for-context --role <role-id> \
  --keywords "<feature/task keywords>" --tech-stacks "<detected stack>"
```
`<role-id>` uses the knowledge-base id (`backend-dev`, `architect`,
`product-owner`, `ux`, `infrastructure`, ...) — resolve team_model.py ids
(`po`, `infra`, `ui-ux-brand`) through `profiles.resolve_knowledge_role`
first (`knowledge for-role` already does this internally).

## Must do — escalation routing
The role playbooks define a consistent escalation chain; the orchestrator
enforces that agents actually follow it instead of resolving things
sideways:
1. A dev agent (backend/frontend/fullstack) finds an architecture
   inconsistency or a needed structural pattern -> Architect Agent
   (or directly to Tech Lead for pure ownership/conflict issues).
2. The Architect Agent confirms/scopes it and hands a remediation item to
   the Tech Lead.
3. The Tech Lead creates an owned, prioritized work package and assigns a
   dev agent (never leaves it unassigned).
4. The Scrum Master Agent folds the new package into the visible plan and
   flags critical-path/blocker impact from recorded metrics.
Record each hop (who raised it, who resolved it, what package it became)
so the final report can show the escalation actually closed, not just that
it was mentioned.

## Must avoid
- Do not let a role skip its own playbook's Must Avoid list "to move
  faster" — a violation recorded now is cheaper than one found in
  `analyze` or QA later.
- Do not resolve a cross-role disagreement yourself when a role playbook
  names the owner (e.g. architecture disputes belong to the Architect
  Agent, conflict/ownership disputes belong to the Tech Lead) — route it,
  don't decide it.

## Related concepts
- every `playbook.*` module in this category
