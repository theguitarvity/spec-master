---
id: architecture.cqrs
type: Pattern
name: CQRS
category: architecture
applicable_roles:
  - architect
  - tech-lead
tags:
  - architecture
  - patterns
depth:
  architect: L4
  tech-lead: L3
---

# CQRS

## Definition
Read model / write model separation. CRITICAL: CQRS does NOT require Event Sourcing (common misconception).

## Problem it addresses
A single model used for both reading and writing forces compromises: the shape that's efficient to write is rarely the shape that's efficient or convenient to query, especially as read and write load patterns diverge.

## Core principles
- Command Query Responsibility Segregation: separate models for writes (commands, enforcing invariants) and reads (queries, optimized for display/reporting).
- The write model can stay normalized and invariant-focused; the read model can be denormalized, cached, or even a different data store entirely.
- **CQRS does NOT require Event Sourcing** — this is the most common misconception. CQRS is about model separation; Event Sourcing is about how state is persisted. They compose well together but are independent decisions.

## Appropriate use
Apply CQRS when read and write workloads have genuinely different shapes, scaling needs, or consistency requirements — e.g. a write-heavy order system with a reporting dashboard that needs a very different, denormalized query shape.

## Inappropriate use
Skip CQRS for straightforward CRUD screens where reads and writes use essentially the same shape — the dual-model overhead buys nothing there.

## Trade-offs
Two models to keep in sync (via events, a sync job, or CDC) and more moving parts, in exchange for each side being independently optimized and independently scalable.

## Typical violations
Adopting CQRS and reflexively bolting on Event Sourcing 'because they go together', when the actual problem was only read/write model shape mismatch and a synchronization job would have sufficed.

## Anti-patterns
Cargo Cult application of CQRS+ES to a low-complexity CRUD app is the textbook example cited whenever this pattern is discussed as over-applied.

## Related concepts
- [[architecture.eda]]
- [[architecture.event-sourcing]]
