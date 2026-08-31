---
id: principle.solid
type: Principle
name: Solid Principles
category: foundations
applicable_roles:
  - architect
  - tech-lead
  - backend-dev
tags:
  - solid
  - design
depth:
  architect: L4
  tech-lead: L3
  backend-dev: L2
---

# Solid Principles

## Definition
S: Single Responsibility, O: Open/Closed, L: Liskov Substitution, I: Interface Segregation, D: Dependency Inversion. Each sub-principle explained with violation examples.

## Problem it addresses
Object-oriented codebases tend to rot into classes that know too much, break when unrelated code changes, and can't be extended without hacking their internals. SOLID names the five specific failure modes that cause this rot so they can be recognized and fixed independently.

## Core principles
- **S**ingle Responsibility: a class should have one reason to change, i.e. one axis of stakeholder concern.
- **O**pen/Closed: extend behavior via new code (new classes, strategies), not by editing tested code paths.
- **L**iskov Substitution: a subtype must be usable anywhere its base type is expected without surprising the caller (no strengthened preconditions, no weakened postconditions).
- **I**nterface Segregation: many small, role-specific interfaces beat one fat interface clients are forced to depend on in full.
- **D**ependency Inversion: high-level policy depends on abstractions, and low-level details implement those abstractions — not the reverse.

## Appropriate use
Apply SOLID where a module is expected to change repeatedly (core domain logic, anything with more than one plausible reason to be edited) or where multiple teams touch the same code. It pays for itself when the abstraction boundary matches a real, recurring axis of change.

## Inappropriate use
Do not pre-emptively split a 40-line script into five SRP-compliant classes, or introduce an interface for a class with exactly one implementation and no planned second one — that is speculative generality, not SRP. Small CLIs, one-off scripts, and stable leaf utilities rarely benefit.

## Trade-offs
Each principle trades short-term simplicity for long-term changeability: more files, more indirection, more interfaces to navigate, in exchange for isolated blast radius when requirements shift. Over-applied, SOLID produces the same maintenance burden it was meant to prevent, just spread across more files.

## Typical violations
- A `UserService` that also formats emails, validates input, and writes audit logs (SRP violation).
- A `switch`/`if-else` on type that must be edited every time a new type is added, instead of polymorphic dispatch (OCP violation).
- A subclass that throws `NotImplementedError` on a method the base class guarantees (LSP violation — the classic `Square extends Rectangle` example).
- A `Worker` interface with 15 methods where most implementers stub out 10 of them (ISP violation).

## Anti-patterns
God Object (SRP taken to its failure extreme) and Cargo Cult SOLID — wrapping every class in an interface and a factory 'because SOLID says so' without a second implementation ever existing.

## Related concepts
- [[principle.coupling-cohesion]]
- [[principle.dependency-inversion]]
