---
id: distributed.idempotency
type: Principle
name: Distributed Idempotency
category: distributed-systems
applicable_roles:
  - architect
  - tech-lead
  - backend-dev
tags:
  - distributed
  - resilience
depth:
  architect: L4
---

# Distributed Idempotency

## Definition
At-most-once, at-least-once, exactly-once semantics. Idempotency keys, deduplication.

## Problem it addresses
In a distributed system, a caller often cannot tell whether a request that appeared to fail (timeout, dropped response) actually succeeded server-side — retrying blindly risks double effects unless the operation and the delivery semantics are designed for it together.

## Core principles
- **At-most-once**: delivered zero or one times — simple, but messages can be silently lost.
- **At-least-once**: delivered one or more times — the common default for message brokers, since it's easier to guarantee than exactly-once; requires idempotent consumers.
- **Exactly-once**: delivered precisely once — extremely hard to guarantee end-to-end across a real network; most systems that claim it actually provide at-least-once delivery plus idempotent processing, which achieves the same observable effect.
- **Idempotency keys**: a caller-supplied unique identifier per logical operation lets the receiver detect and ignore a duplicate delivery or retry, achieving effectively-once processing on top of at-least-once delivery.

## Appropriate use
Design idempotency keys and deduplication explicitly into any consumer of an at-least-once channel (which is most message brokers) and into any client-facing API a client might legitimately retry.

## Inappropriate use
Don't market a system as providing 'exactly-once delivery' without qualifying that it's really at-least-once-delivery-plus-idempotent-processing — the distinction matters for what the consumer must actually implement.

## Trade-offs
Idempotent processing requires storing seen-operation keys (with a retention/TTL policy) and disciplined key generation on the client side, in exchange for safety against duplicate effects under retries or redelivery.

## Typical violations
A message consumer that assumes 'my broker guarantees exactly-once' and skips deduplication logic entirely, then double-processes a message after a broker-side redelivery following a consumer crash mid-processing.

## Anti-patterns
Treating delivery-semantics marketing claims as sufficient without designing consumer-side idempotency is a common, costly instance of the broader 'trusting the network' anti-pattern.

## Related concepts
- [[principle.idempotency]]
- [[distributed.at-least-once]]
