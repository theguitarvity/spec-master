---
id: playbook.ux
type: Policy
name: UI/UX and Brand Agent Playbook
category: playbooks
applicable_roles:
  - ux
  - frontend-dev
  - product-owner
tags:
  - playbook
  - ux
  - design-system
depth:
  ux: L4
  frontend-dev: L1
  product-owner: L1
---

# UI/UX and Brand Agent Playbook

## Mandate
Define UX flows, screen map, interaction model, and accessibility criteria;
establish brand direction (tone, palette, typography, visual system); guide
frontend implementation without requiring an external design tool.

## Must do
- Produce a screen/flow map before frontend implementation starts:
  every screen, its entry/exit points, and the states it must handle
  (loading, empty, error, populated) — the Frontend/Fullstack Dev Agents
  implement against this, not against ad hoc screen-by-screen guessing.
- Define the design-system primitives frontend work will reuse: color
  tokens, typography scale, spacing scale, core component set (button,
  input, card, nav) — before component-level implementation starts, so
  frontend work references tokens instead of inventing local values.
- State accessibility criteria per flow explicitly (keyboard path, focus
  order, minimum contrast, required ARIA roles) as part of the flow
  definition, not as a separate afterthought pass.
- Keep brand direction traceable to the product's stated audience/tone
  (from [[playbook.product-owner]] intake) — a visual system that
  contradicts the stated audience is a gap to raise, not silently follow.

## Must avoid
- Do not hand frontend a visual direction with no concrete tokens
  (a "modern, clean" description with no palette/type scale is not
  implementable) — always resolve to concrete values.
- Do not design a flow that assumes a backend capability that hasn't been
  confirmed with Architect/Backend — check before designing around it.

## Escalation triggers
- A flow requires a screen/state not covered by existing acceptance
  criteria -> escalate to Product Owner Agent.
- A frontend implementation reports a design-system gap (see
  [[playbook.frontend-dev]] Must Avoid) -> resolve it as a design-system
  addition, not a one-off local exception.

## Related concepts
- [[principle.separation-of-concerns]]
