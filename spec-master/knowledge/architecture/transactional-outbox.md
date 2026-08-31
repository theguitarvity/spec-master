---
id: pattern.transactional-outbox
type: Pattern
name: Transactional Outbox
category: architecture
applicable_roles:
  - architect
  - tech-lead
  - backend-dev
tags:
  - distributed
  - patterns
depth:
  architect: L4
  tech-lead: L3
---

# Transactional Outbox

## Definition
Atomic write to DB + outbox table, CDC or polling relay. Solves dual-write problem.

## Problem it addresses
Writing to a database and then publishing a message to a broker are two separate operations; if the process crashes between them (or the broker publish silently fails), the database and the message stream disagree about what happened — the 'dual write' problem.

## Core principles
- Write the business change and a row describing the event to be published into the **same local database transaction**, in an outbox table.
- A separate relay process — polling the outbox table or reading the database's change-data-capture (CDC) stream — reads new outbox rows and publishes them to the broker, then marks them sent.
- Because the business write and the outbox write are atomic together, the event is never lost even if the publish step crashes — it just retries.

## Appropriate use
Use it whenever a service must atomically update its own database and reliably notify other services/consumers of that change — order creation that must also emit an `OrderCreated` event.

## Inappropriate use
Skip it when the downstream notification isn't required to be reliable (a best-effort analytics ping) — the outbox/relay machinery isn't worth building for a notification nobody depends on for correctness.

## Trade-offs
An extra table, a relay process (or CDC pipeline) to operate, and at-least-once delivery to downstream consumers (so they must be idempotent) — in exchange for guaranteed, atomic delivery of the event alongside the state change.

## Typical violations
Publishing directly to the broker inside the same code path as the database write without a shared transaction — a crash or broker outage between the two steps silently drops the event.

## Anti-patterns
The 'dual write' anti-pattern this pattern exists specifically to eliminate: writing to two systems (DB and broker) with no shared atomicity guarantee.

## Related concepts
- [[pattern.saga]]
- [[distributed.at-least-once]]
- [[principle.idempotency]]
