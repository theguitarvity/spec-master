---
id: principle.separation-of-concerns
type: Principle
name: Separation of Concerns
category: foundations
applicable_roles:
  - architect
  - tech-lead
  - backend-dev
  - frontend-dev
tags:
  - design
  - architecture
depth:
  architect: L4
  tech-lead: L3
---

# Separation of Concerns

## Definition
Horizontal (layers) vs vertical (features) separation.

## Problem it addresses
When a single unit of code mixes unrelated responsibilities — parsing, business rules, persistence, presentation — a change to one concern risks breaking the others, and no one part can be tested or reused in isolation.

## Core principles
- Horizontal separation: layers such as presentation, business logic, and data access, each depending only on the layer(s) below.
- Vertical separation: feature/module slices, where each slice owns its own logic across concerns instead of sharing a layer with unrelated features.
- A concern is separated correctly when it can be understood, tested, and changed without reading or touching the others.

## Appropriate use
Use horizontal separation when concerns are genuinely shared and stable across features (e.g. a common persistence layer). Use vertical separation when features evolve independently and horizontal layers would force unrelated features to coordinate changes.

## Inappropriate use
Do not force strict horizontal layering onto a small, single-purpose service where the extra indirection buys no real isolation — nor mix both styles inconsistently within the same codebase without a stated convention.

## Trade-offs
Cleaner separation costs more files, more interfaces to cross, and sometimes more boilerplate to shuttle data between layers — in exchange for each concern being independently testable and replaceable.

## Typical violations
A controller/handler function that also runs SQL queries and formats the HTML response inline, so a UI copy change requires touching the same function as a query optimization.

## Anti-patterns
Big Ball of Mud — the terminal state of ignored separation of concerns, where every part of the system depends on every other part.

## Related concepts
- [[principle.solid]]
- [[architecture.layered]]
