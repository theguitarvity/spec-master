---
id: pattern.saga
type: Pattern
name: Distributed Saga
category: architecture
applicable_roles:
  - architect
  - tech-lead
tags:
  - distributed
  - patterns
depth:
  architect: L4
---

# Distributed Saga

## Definition
Choreography vs. Orchestration sagas. Compensating transactions, failure handling.

## Problem it addresses
A business transaction that spans multiple services can't use a single ACID database transaction to guarantee all-or-nothing — some steps may succeed while later steps fail, and there's no built-in rollback across service boundaries.

## Core principles
- A saga is a sequence of local transactions, each in a different service, coordinated to reach eventual consistency across the whole business transaction.
- **Choreography**: each service publishes events and reacts to others' events, with no central coordinator — simple for a few steps, hard to trace as steps grow.
- **Orchestration**: a central saga orchestrator explicitly calls each step and tracks progress — easier to reason about and monitor, but introduces a central coordinating component.
- Failure is handled with **compensating transactions** — explicit steps that semantically undo a prior step's effect (e.g. `CancelReservation` compensates `ReserveInventory`), since there is no automatic rollback.

## Appropriate use
Use sagas for multi-step business transactions that cross service/database boundaries where eventual, compensatable consistency is acceptable — order → payment → inventory → shipping workflows.

## Inappropriate use
Don't reach for a saga when all the steps fit inside a single service and database — a normal ACID transaction is simpler and stronger.

## Trade-offs
Eventual consistency and a genuinely more complex failure model (every step needs a compensating action) in exchange for transactions that can span independently deployed services without a distributed 2PC coordinator.

## Typical violations
Designing forward steps without designing the corresponding compensating transaction, leaving no defined recovery path when step 3 of 5 fails.

## Anti-patterns
A saga that requires every step to succeed synchronously before returning to the caller effectively recreates Two-Phase Commit's blocking behavior without its atomicity guarantees — worst of both worlds.

## Related concepts
- [[distributed.2pc]]
- [[pattern.transactional-outbox]]
