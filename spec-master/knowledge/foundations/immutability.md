---
id: principle.immutability
type: Principle
name: Immutability
category: foundations
applicable_roles:
  - architect
  - tech-lead
  - backend-dev
tags:
  - design
  - functional
depth:
  architect: L3
  tech-lead: L3
---

# Immutability

## Definition
Value objects, event sourcing connection, thread safety.

## Problem it addresses
Mutable shared state is a primary source of bugs that are hard to reproduce: a value changes underneath a caller that didn't expect it to, especially across threads, async callbacks, or long-lived object references.

## Core principles
- An immutable object cannot change after construction; any 'modification' produces a new object instead.
- Value Objects (e.g. `Money`, `DateRange`) are the canonical immutable building block: equality by value, no identity, safe to share freely.
- Immutability underlies event sourcing: the event log is an append-only sequence of immutable facts, never edited in place.
- Immutable data is inherently thread-safe to read — no synchronization is needed for concurrent readers, since nothing can change out from under them.

## Appropriate use
Prefer immutability for value objects, domain events, configuration snapshots, and any data shared across threads/async boundaries or passed through multiple layers where accidental mutation would be hard to trace.

## Inappropriate use
Immutability is a poor fit for large, frequently-mutated in-memory structures on a hot path (e.g. a game engine's per-frame buffer) where allocation churn from copy-on-write would dominate performance.

## Trade-offs
Immutable data eliminates a whole class of aliasing bugs and makes reasoning about state trivial, at the cost of extra allocations for every 'change' and sometimes awkward APIs for building up complex nested structures incrementally (mitigated by builders or persistent data structures).

## Typical violations
A shared config object with public mutable fields that one module tweaks at runtime, silently changing behavior for every other module holding the same reference.

## Anti-patterns
Mutable global/shared state accessed from multiple threads without synchronization — a direct enabler of race conditions immutability is designed to prevent.

## Related concepts
- [[design.value-object]]
- [[architecture.event-sourcing]]
