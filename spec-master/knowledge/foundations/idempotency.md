---
id: principle.idempotency
type: Principle
name: Idempotency
category: foundations
applicable_roles:
  - architect
  - tech-lead
  - backend-dev
  - devops
tags:
  - distributed
  - resilience
depth:
  architect: L4
  tech-lead: L3
---

# Idempotency

## Definition
HTTP idempotency, at-least-once delivery idempotency, deduplication keys.

## Problem it addresses
Networks retry. Clients double-click. Message brokers redeliver. Any operation without idempotency turns a routine retry into a duplicate charge, a duplicate email, or a corrupted counter.

## Core principles
- An operation is idempotent if performing it multiple times has the same effect as performing it once.
- HTTP idempotency by spec: GET, PUT, DELETE are idempotent; POST is not — this is why clients safely auto-retry GET/PUT but not POST.
- At-least-once delivery (the norm for most message brokers) requires idempotent consumers, since the broker may redeliver a message the consumer already processed.
- The standard mechanism is a deduplication/idempotency key: the caller supplies a unique key per logical operation, and the server records which keys it has already applied.

## Appropriate use
Design idempotency into any operation that can be retried by a client, a load balancer, or a message broker — payments, order creation, webhook handlers, and any consumer of an at-least-once queue.

## Inappropriate use
Don't force idempotency onto operations with no retry path and no shared external effect (e.g. a pure read with no side effect already is idempotent by construction) — the design cost of dedup keys and storage isn't worth it there.

## Trade-offs
Idempotency requires tracking applied operation keys (storage, TTL, cleanup) and disciplined API design (clients must supply stable keys) in exchange for safety against duplicate side effects under retry.

## Typical violations
A `POST /charge` endpoint with no idempotency key: a client timeout followed by an automatic retry double-charges the customer even though the first request actually succeeded server-side.

## Anti-patterns
Relying on 'the network will probably be fine' instead of designing for at-least-once semantics is a common instance of premature optimization / optimistic-path-only design.

## Related concepts
- [[distributed.at-least-once]]
- [[pattern.transactional-outbox]]
