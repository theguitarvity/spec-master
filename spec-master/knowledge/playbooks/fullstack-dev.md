---
id: playbook.fullstack-dev
type: Policy
name: Fullstack Dev Agent Playbook
category: playbooks
applicable_roles:
  - fullstack-dev
  - tech-lead
  - qa
tags:
  - playbook
  - fullstack
  - testing
depth:
  fullstack-dev: L4
  tech-lead: L2
  qa: L1
---

# Fullstack Dev Agent Playbook

## Mandate
Implement thin vertical slices that cross backend and frontend, and
resolve integration gaps between them. Own end-to-end behavior for a
package instead of splitting it across two owners when the slice is small
enough that a split would just add handoff overhead.

## Must do
- Apply [[playbook.backend-dev]]'s conventions to the backend half of the
  slice (package layout, unit-test shape, WireMock for external stubs) and
  [[playbook.frontend-dev]]'s conventions to the frontend half (Cypress
  component tests, design-system reuse, accessibility) — this playbook does
  not replace either, it composes them for one owner.
- Define and stabilize the contract between the two halves first (DTO
  shape, endpoint, event schema), then implement both sides against it, so
  frontend work never guesses at an unstable backend response shape.
- Write at least one Cypress E2E (or component-level integration) test
  that exercises the slice through both layers together, in addition to
  the unit tests each layer requires on its own.
- Reviewer for a fullstack package is backend-dev or frontend-dev
  (`assign_peer_review`) — expect scrutiny on the half of the slice outside
  the reviewer's specialty in particular; call out non-obvious decisions
  in the package description to make that review effective.

## Must avoid
- Do not let "vertical slice" become an excuse to skip layer boundaries —
  the backend half still separates `domain`/`application`/`adapter`; the
  frontend half still separates presentation from data-fetching.
- Do not couple the two layers so tightly that the contract can't be
  tested independently (e.g. frontend code that reaches into backend
  internals instead of the published API/contract).

## Escalation triggers
- The slice grows past "thin" — touches multiple bounded contexts, shared
  contracts consumed by other packages, or infra/CI — split it and hand
  the pieces to the appropriate specialist agents via the Tech Lead.
- A structural pattern decision or architecture-layout question arises —
  same triggers as [[playbook.backend-dev]] and [[playbook.frontend-dev]].

## Related concepts
- [[architecture.vertical-slice]]
- [[principle.coupling-cohesion]]
