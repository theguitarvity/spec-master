---
id: principle.coupling-cohesion
type: Principle
name: Coupling and Cohesion
category: foundations
applicable_roles:
  - architect
  - tech-lead
  - backend-dev
tags:
  - design
  - architecture
depth:
  architect: L4
  tech-lead: L3
---

# Coupling and Cohesion

## Definition
High cohesion, low coupling. Types of coupling: content, common, control, stamp, data. Law of Demeter connection.

## Problem it addresses
Modules that depend heavily on each other's internals (high coupling) ripple changes across the codebase; modules whose parts don't belong together (low cohesion) are hard to name, understand, or reuse as a unit. Both make change expensive, for different reasons.

## Core principles
- Aim for **high cohesion**: everything inside a module serves one clear, related purpose.
- Aim for **low coupling**: modules interact through narrow, stable interfaces rather than shared internals.
- Coupling types, roughly worst to best: content coupling (reaching into another module's internals), common coupling (shared global state), control coupling (passing flags that dictate another module's internal logic), stamp coupling (passing a large structure when only part is needed), data coupling (passing exactly the data needed).
- Law of Demeter ('talk only to your immediate friends') is a practical heuristic for keeping coupling low: avoid chains like `a.getB().getC().doThing()`.

## Appropriate use
Actively manage coupling and cohesion at module and package boundaries that are expected to be maintained by different people or evolve at different rates.

## Inappropriate use
Do not chase zero coupling everywhere — some coupling is inherent and desirable (a caller is necessarily coupled to the interface it calls); over-indexing on decoupling produces excess indirection with no corresponding benefit.

## Trade-offs
Lower coupling generally requires more explicit interfaces and more careful API design up front; higher cohesion sometimes means splitting a convenient 'utils' grab-bag into several smaller, better-named modules, costing short-term reorganization effort.

## Typical violations
A `utils.py` that accumulates unrelated helpers (low cohesion) alongside modules that read and write each other's global mutable state directly instead of through an interface (high, content-level coupling).

## Anti-patterns
Big Ball of Mud (systemic high coupling) and Shotgun Surgery — a single logical change forcing edits across many unrelated modules, a direct symptom of poor cohesion boundaries.

## Related concepts
- [[principle.solid]]
- [[principle.separation-of-concerns]]
