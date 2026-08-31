---
id: pattern.bulkhead
type: Pattern
name: Bulkhead Pattern
category: architecture
applicable_roles:
  - architect
  - tech-lead
  - backend-dev
tags:
  - resilience
  - patterns
depth:
  architect: L3
  tech-lead: L3
---

# Bulkhead Pattern

## Definition
Named after ship bulkheads that seal off flooding to one compartment: isolate resource pools (threads, connections, memory) per dependency so exhaustion in one doesn't starve the others.

## Problem it addresses
Without isolation, a slow or failing dependency can exhaust a shared resource pool (e.g. a shared thread or connection pool) that every other dependency also relies on — one struggling downstream service takes down calls to every unrelated, healthy service too.

## Core principles
- Allocate separate resource pools (thread pools, connection pools, semaphores) per dependency or per class of dependency, instead of one shared pool for everything.
- A failure that exhausts one bulkhead's pool is contained to calls through that pool — calls to other dependencies through their own pools continue unaffected.
- Pairs naturally with Circuit Breaker: the bulkhead limits concurrent exposure to a struggling dependency, while the breaker stops calling it altogether once it's clearly failing.

## Appropriate use
Apply bulkheads whenever a service calls multiple independent downstream dependencies and a failure in one should not be able to exhaust resources needed to call the others.

## Inappropriate use
Skip it for a service with only one downstream dependency, or where all downstream calls are already isolated by process/container boundaries — the pattern's value is specifically in-process isolation between multiple shared-process dependencies.

## Trade-offs
More resource pools to size and tune (each needs its own capacity planning) and potentially lower peak utilization of any single pool, in exchange for a failure in one dependency being unable to starve calls to the others.

## Typical violations
All outbound HTTP calls sharing one global thread pool, so a hung call to a slow third-party API exhausts the threads needed to call a completely unrelated, healthy internal service.

## Anti-patterns
A single shared connection/thread pool across all dependencies is the specific setup that turns one dependency's failure into a full cascading failure across unrelated call paths.

## Related concepts
- [[pattern.circuit-breaker]]
- [[distributed.cascading-failures]]
