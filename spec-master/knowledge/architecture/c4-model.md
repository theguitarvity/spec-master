---
id: architecture.c4
type: Principle
name: C4 Model
category: architecture
applicable_roles:
  - architect
  - tech-lead
tags:
  - documentation
  - architecture
depth:
  architect: L3
---

# C4 Model

## Definition
Context, Containers, Components, Code levels. When to use each level.

## Problem it addresses
A single architecture diagram trying to show everything from deployment topology down to individual classes is either too abstract to be useful for implementation or too detailed to communicate the big picture to a stakeholder.

## Core principles
- Four zoom levels, each for a different audience: **Context** (the system and its users/external systems, for anyone), **Containers** (deployable/runnable units — services, databases, apps, for technical stakeholders), **Components** (major structural building blocks inside one container, for developers), **Code** (classes/interfaces, usually left to the IDE rather than hand-drawn).
- Each level zooms into one element of the level above it — Components diagrams only make sense in the context of one specific Container.

## Appropriate use
Use Context and Container diagrams for onboarding, stakeholder communication, and architecture decision records. Use Component diagrams for the specific containers with real internal structure worth documenting.

## Inappropriate use
Don't hand-maintain a Code-level diagram — it goes stale immediately and the IDE/tooling already shows this level on demand; investing manual effort there is wasted.

## Trade-offs
A small amount of upfront diagramming discipline and the need to keep diagrams in sync with reality, in exchange for architecture documentation that scales to its audience instead of one overloaded diagram trying to serve everyone.

## Typical violations
A single diagram mixing deployment infrastructure, service boundaries, and internal class relationships all at once, which is unreadable to any single audience.

## Anti-patterns
Stale, unmaintained diagrams that no longer match the system are worse than no diagram — they actively mislead; C4's leveled scope is partly a defense against this by keeping each diagram small enough to actually maintain.

## Related concepts
- [[architecture.hexagonal]]
