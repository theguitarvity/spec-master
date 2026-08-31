---
id: architecture.eda
type: Pattern
name: Event-Driven Architecture
category: architecture
applicable_roles:
  - architect
  - tech-lead
  - backend-dev
tags:
  - architecture
  - events
depth:
  architect: L4
  tech-lead: L3
---

# Event-Driven Architecture

## Definition
Events as first-class citizens, loose coupling via broker. Event notification vs. event-carried state vs. event sourcing.

## Problem it addresses
Tight, synchronous request/response chains between services couple their availability together — if one downstream service is slow or down, every upstream caller in the chain is affected immediately.

## Core principles
- Events are first-class: something that happened, published once, consumed by zero or more interested parties, decoupling producer from consumer.
- Three flavors, increasing in coupling to the event payload: **event notification** (a thin 'something happened, go fetch details' ping), **event-carried state transfer** (the event carries the data consumers need, avoiding a callback), and **event sourcing** (the event log itself is the source of truth, not just a notification mechanism).
- Producers do not know or care who consumes their events — new consumers can be added without changing the producer.

## Appropriate use
Use EDA where producers and consumers should scale, deploy, and fail independently, and where 'eventually consistent, but decoupled' is an acceptable trade for the domain (order placed → inventory reserved → shipment scheduled).

## Inappropriate use
Avoid it where the caller genuinely needs an immediate, consistent answer (checking real-time available balance before authorizing a debit) — synchronous calls or a different consistency strategy fit better there.

## Trade-offs
Loose coupling and independent scaling, in exchange for eventual consistency, harder end-to-end debugging (a single business transaction now spans multiple async hops), and the need for tooling like distributed tracing to follow a request across events.

## Typical violations
Publishing a bare event id and requiring every consumer to call back into the producer's API for details, effectively recreating synchronous coupling with the added latency and failure modes of a message broker.

## Anti-patterns
Distributed Monolith can also emerge from EDA when events are used but every consumer still requires the same tight ordering and delivery timing as a synchronous call, defeating the point of the async design.

## Related concepts
- [[architecture.cqrs]]
- [[architecture.event-sourcing]]
- [[pattern.transactional-outbox]]
