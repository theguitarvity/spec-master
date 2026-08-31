---
id: architecture.onion
type: Pattern
name: Onion Architecture
category: architecture
applicable_roles:
  - architect
  - tech-lead
tags:
  - architecture
depth:
  architect: L3
  tech-lead: L3
---

# Onion Architecture

## Definition
Concentric layers around a domain model core, with dependencies pointing only inward — the domain model at the center knows nothing about the application services, infrastructure, or UI layered around it.

## Problem it addresses
Domain logic entangled with infrastructure and application-layer concerns can't be tested, reused, or evolved independently of the technical layers wrapped around it.

## Core principles
- The domain model sits at the very center, with no outward dependencies at all — not even on application services.
- Surrounding rings (domain services, application services, infrastructure/UI) each depend only inward, never outward — the same Dependency Rule Clean Architecture and Hexagonal Architecture also enforce.
- Onion Architecture, Hexagonal Architecture, and Clean Architecture are largely the same underlying idea (isolate the domain, invert dependencies toward it) expressed with slightly different diagrams and terminology — teams usually pick one vocabulary and use it consistently rather than treating them as meaningfully different choices.

## Appropriate use
Use it (or an equivalent — Hexagonal/Clean) wherever the domain model has real, non-trivial business logic that should remain independent of frameworks, UI, and infrastructure choices.

## Inappropriate use
Skip the layering ceremony for services with a thin or absent domain model (pure data pass-through, simple CRUD) where there's no real domain logic to isolate.

## Trade-offs
Same as Hexagonal/Clean Architecture: more files and indirection to maintain the layering discipline, in exchange for a domain core that's framework-independent and fast to unit test.

## Typical violations
A domain entity that references an application service or an infrastructure interface, inverting the onion's inward-only dependency rule.

## Anti-patterns
Distributed Monolith and Big Ball of Mud are the eventual results of skipping this boundary entirely, same as with Hexagonal and Clean Architecture.

## Related concepts
- [[architecture.hexagonal]]
- [[architecture.clean]]
- [[principle.dependency-inversion]]
