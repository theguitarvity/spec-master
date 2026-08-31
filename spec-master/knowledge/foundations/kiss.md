---
id: principle.kiss
type: Principle
name: Keep It Simple, Stupid
category: foundations
applicable_roles:
  - architect
  - tech-lead
  - backend-dev
  - frontend-dev
  - ux
tags:
  - simplicity
  - design
depth:
  architect: L3
  tech-lead: L3
---

# Keep It Simple, Stupid

## Definition
Simplicity vs. simplism, unnecessary complexity detection.

## Problem it addresses
Systems accrue complexity faster than anyone notices in the moment — each individually reasonable abstraction, config flag, or layer adds up to something no one can hold in their head. KISS is the discipline of resisting complexity that isn't paying for itself yet.

## Core principles
- Prefer the simplest design that satisfies the current, known requirements — not the most general one.
- Simplicity is measured by how easily a newcomer can predict the system's behavior, not by line count alone.
- Simplicity and simplism differ: KISS is not an excuse to skip necessary error handling, tests, or a real data model — that is simplism, trading correctness for less typing.

## Appropriate use
Favor KISS by default for internal tools, early-stage features, and any code path where requirements are still being learned — a simple, direct implementation is also the cheapest one to change once real requirements arrive.

## Inappropriate use
Do not use KISS to justify skipping legitimate complexity a problem actually requires — e.g. a payments system genuinely needs idempotency keys and retries, and removing them 'to keep it simple' just moves the complexity into an incident.

## Trade-offs
A simple solution is cheap to build and easy to reason about now, but may need a larger rewrite later if requirements grow past what it can express — KISS optimizes for today's clarity, sometimes at the cost of tomorrow's extension.

## Typical violations
Introducing a plugin architecture, a generic rules engine, or a microservice split for a feature with one known consumer and no stated scaling requirement.

## Anti-patterns
Golden Hammer (reaching for one familiar heavy tool for every problem) and Architecture Astronautics — designing for abstract flexibility that no concrete requirement has asked for.

## Related concepts
- [[principle.yagni]]
- [[principle.dry]]
