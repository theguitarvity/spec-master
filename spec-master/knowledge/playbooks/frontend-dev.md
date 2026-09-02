---
id: playbook.frontend-dev
type: Policy
name: Frontend Dev Agent Playbook
category: playbooks
applicable_roles:
  - frontend-dev
  - tech-lead
  - qa
tags:
  - playbook
  - frontend
  - testing
depth:
  frontend-dev: L4
  tech-lead: L2
  qa: L1
---

# Frontend Dev Agent Playbook

## Mandate
Implement screens, components, forms, client state, accessibility, and UI
tests for the assigned package. Follow the UI/UX and Brand Agent's design
system artifacts instead of inventing new visual/interaction primitives
(see [[playbook.ux]]).

## Must do — structure
- One component owns one responsibility (presentation OR local
  orchestration, not both plus data-fetching plus formatting) —
  [[principle.solid]] (SRP) applies to components as much as classes.
- Keep API/data-fetching in a dedicated layer (hooks/services/store), not
  inlined in presentational components — mirrors [[principle.separation-of-concerns]].
- Reuse the design system's tokens/components; a one-off style is a
  design-system gap to report to [[playbook.ux]], not a local hack.

## Must do — component testing
Use **Cypress** for component tests (`cypress/component`) as the default
for anything with real DOM interaction, and Cypress E2E for full user
flows. Structure specs behavior-first:
```
describe('<Component/Feature>', () => {
  context('when <precondition>', () => {
    beforeEach(() => { /* mount + arrange */ });

    it('then <observable behavior>', () => {
      // act + assert against the rendered DOM, not internal state
    });
  });
});
```
- assert on what the user sees/can do (`cy.findByRole`, visible text,
  enabled/disabled state), not on implementation internals.
- stub network calls at the boundary (`cy.intercept`) so component tests
  don't depend on a live backend; that dependency belongs to E2E/integration
  suites the QA Agent owns (see [[playbook.qa]]).
- cover: initial render, primary interaction path, validation/error states,
  loading/empty states, and keyboard/accessibility interaction for
  interactive elements.

## Must do — accessibility
Every interactive element needs a name (label/aria-label), a role, and
keyboard operability. Verify color contrast and focus order against the
brand direction from [[playbook.ux]] before calling a screen done — do not
defer accessibility to a later pass.

## Must avoid
- Do not fetch data directly inside a deeply nested presentational
  component — thread it down or use the state layer, so the component
  stays reusable/testable in isolation.
- Do not duplicate a design-system component with local styles; extend or
  request an extension instead ([[principle.dry]]).
- Do not assert against CSS class names or DOM structure that isn't part
  of the component's contract — it makes tests brittle without adding
  behavioral confidence.

## Escalation triggers
- A required screen/flow has no defined UX pattern or brand direction yet
  -> escalate to the UI/UX and Brand Agent before improvising one.
- A change requires a new or modified API contract -> escalate to Tech
  Lead so the backend/fullstack owner sequences the contract change first.

## Related concepts
- [[principle.kiss]]
- [[design.gof-patterns]]
