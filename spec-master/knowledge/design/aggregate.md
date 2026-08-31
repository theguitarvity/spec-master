---
id: design.aggregate
type: Pattern
name: Aggregate
category: design
applicable_roles:
  - architect
  - tech-lead
  - backend-dev
tags:
  - design
  - ddd
depth:
  architect: L3
---

# Aggregate

## Definition
Transactional consistency boundary, Aggregate Root as entry point. Keep aggregates small, reference by ID across boundaries.

## Problem it addresses
Without an explicit consistency boundary, invariants that must hold across a group of related objects (e.g. 'order total must equal the sum of line items') can be violated when different parts of the code update related objects independently and inconsistently.

## Core principles
- An aggregate is a cluster of domain objects treated as a single unit for the purpose of data changes, with one designated **Aggregate Root** as its only entry point.
- The aggregate root enforces the invariants for everything inside the aggregate boundary — external code never modifies internal aggregate members directly, only through the root.
- Keep aggregates small — a large aggregate creates unnecessary contention (everyone locking the same root to change unrelated parts) and pulls unrelated data into one transactional boundary.
- Reference other aggregates by ID only, not by object reference — this keeps aggregate boundaries a true transactional boundary rather than an implicit graph of everything.

## Appropriate use
Model an aggregate around a genuine transactional invariant that must be atomically true — an `Order` aggregate enforcing that its total always matches its line items.

## Inappropriate use
Don't group unrelated entities into one aggregate just because they're related in a UI screen or a query — that inflates the transactional boundary and creates contention with no invariant actually requiring it.

## Trade-offs
Small aggregates reduce contention and keep transactions cheap, but push cross-aggregate consistency to eventual consistency (via domain events), which the application must be designed to tolerate.

## Typical violations
Loading an aggregate root and then modifying a child entity directly via a setter, bypassing the root's invariant checks entirely.

## Anti-patterns
An overly large aggregate that pulls in most of the object graph 'to be safe' recreates the God Object problem at the domain-modeling level, with the same contention and coupling costs.

## Related concepts
- [[design.ddd]]
- [[design.domain-event]]
