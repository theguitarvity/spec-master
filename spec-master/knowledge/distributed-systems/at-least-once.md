---
id: distributed.at-least-once
type: Principle
name: At-Least-Once Delivery
category: distributed-systems
applicable_roles:
  - architect
  - tech-lead
  - backend-dev
tags:
  - distributed
  - messaging
depth:
  architect: L4
---

# At-Least-Once Delivery

## Definition
Message delivery guarantee, retry + deduplication pattern.

## Problem it addresses
Guaranteeing a message is delivered at least once (rather than risking it being lost) requires the sender to retry until it gets acknowledgment — but that retry mechanism inherently risks delivering the same message more than once if the acknowledgment itself is lost.

## Core principles
- The sender retries a message until it receives an acknowledgment; because the ack itself can be lost even after successful processing, the sender cannot always distinguish 'never delivered' from 'delivered but ack lost' — so it retries, accepting possible duplication.
- This is the delivery guarantee most message brokers (Kafka, SQS, RabbitMQ with acks) provide by default, because guaranteeing exactly-once end-to-end is far harder and often unnecessary if the consumer is idempotent.
- At-least-once delivery combined with an idempotent consumer achieves the practical effect of exactly-once processing without needing distributed transaction coordination.

## Appropriate use
Design for at-least-once as the default assumption for any message broker integration — build consumers to be idempotent from the start rather than retrofitting deduplication after a production duplicate-processing incident.

## Inappropriate use
Don't build a consumer that assumes single delivery per message and skips deduplication, unless the broker and configuration genuinely provide exactly-once semantics end-to-end (rare, and worth confirming explicitly rather than assuming).

## Trade-offs
Retry-until-ack is simple to implement and robust against transient failures, at the cost of guaranteed possible duplicates that the consumer must be designed to tolerate via idempotency keys or natural idempotent operations.

## Typical violations
A payment consumer that processes a charge on every delivery without a dedup key, double-charging a customer after a broker redelivers a message whose earlier processing succeeded but whose ack was lost.

## Anti-patterns
Assuming 'the broker will only deliver once' without verifying the specific delivery guarantee configured is a frequent, expensive misconception.

## Related concepts
- [[distributed.idempotency]]
- [[pattern.transactional-outbox]]
