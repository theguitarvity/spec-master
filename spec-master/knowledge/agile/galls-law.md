---
id: agile.galls-law
type: Principle
name: Gall's Law
category: agile
applicable_roles:
  - architect
  - tech-lead
tags:
  - agile
  - laws
depth:
  architect: L3
---

# Gall's Law

## Definition
Every complex system that works evolved from a simpler system that worked. Don't design complex systems from scratch.

## Problem it addresses
Teams that try to design a complete, complex system from scratch before anything simple has been proven to work tend to produce systems that don't actually work, because the complexity was never validated incrementally against reality.

## Core principles
- 'A complex system that works is invariably found to have evolved from a simple system that worked. A complex system designed from scratch never works and cannot be patched up to make it work. You have to start over, beginning with a working simple system' (John Gall).
- Directly supports incremental delivery and evolutionary design: build the smallest working version first, then grow complexity only where real usage demonstrates it's needed.
- Explains why greenfield 'big design up front' rewrites of complex systems fail at a much higher rate than incrementally evolved ones — there's no simple, validated core to build the complexity on top of.

## Appropriate use
Apply Gall's Law when starting any new, ambitious system — deliberately scope the first version down to the smallest thing that works end-to-end, then let complexity grow from there as real requirements confirm it's needed.

## Inappropriate use
Don't use Gall's Law to justify skipping necessary upfront design entirely for a system with well-understood, complex requirements from day one (e.g. known regulatory constraints) — 'start simple' still means the simple version must satisfy the non-negotiable constraints, not ignore them.

## Trade-offs
Starting simple means shipping something with deliberately less capability first, and accepting that the path to the full system runs through several working intermediate versions rather than one big-bang delivery — a real trade against teams or stakeholders who want the complete vision on day one.

## Typical violations
Designing a fully general, complex plugin/extension architecture before a single concrete use case exists to validate the design against, betting the whole architecture on assumptions no working system has tested.

## Anti-patterns
Big Design Up Front for a complex system is close to the direct anti-pattern Gall's Law describes as reliably failing.

## Related concepts
- [[principle.yagni]]
- [[architecture.modular-monolith]]
