---
id: distributed.cascading-failures
type: Principle
name: Cascading Failures
category: distributed-systems
applicable_roles:
  - architect
  - tech-lead
  - devops
tags:
  - distributed
  - resilience
depth:
  architect: L3
---

# Cascading Failures

## Definition
Timeout, circuit breaker, bulkhead patterns to prevent cascade. Thundering herd, retry storms.

## Problem it addresses
One overloaded or slow service can, through the caller chain that depends on it, drag down services that were themselves perfectly healthy — a localized failure becomes a system-wide outage because callers keep hammering the struggling dependency and exhausting their own resources waiting on it.

## Core principles
- **Timeouts**: bound how long a caller waits for a dependency, so a slow dependency can't exhaust the caller's own thread/connection pool indefinitely.
- **Circuit breakers**: stop calling a failing dependency once a failure threshold is crossed, giving both caller and callee relief.
- **Bulkheads**: isolate resource pools (threads, connections) per dependency, so exhaustion calling one dependency can't starve calls to a different, healthy one.
- **Thundering herd**: many clients retrying simultaneously (e.g. right after a service recovers, or all at once on a shared cache expiry) can re-overwhelm a service that just came back up.
- **Retry storms**: naive, synchronized retries without backoff amplify load on an already-struggling dependency instead of giving it room to recover.

## Appropriate use
Apply timeouts, circuit breakers, and bulkheads at every external dependency boundary in a service that has multiple downstream dependencies, so failure in one doesn't starve calls to the others.

## Inappropriate use
Don't rely on default/unbounded timeouts and unlimited synchronous retries as the failure-handling strategy for any dependency whose outage should not become the caller's outage.

## Trade-offs
These protections add configuration surface (thresholds, timeout values, pool sizes) that must be tuned and can themselves cause false-positive failures if set too aggressively, in exchange for containing failure to its actual source instead of letting it propagate.

## Typical violations
No timeout set on an HTTP client call to a downstream service, so a hung dependency slowly exhausts every calling service's thread pool until they all become unresponsive too.

## Anti-patterns
Retry storms and thundering herds are themselves the anti-patterns cascading-failure defenses (circuit breakers, jittered backoff) exist to prevent.

## Related concepts
- [[pattern.circuit-breaker]]
- [[pattern.bulkhead]]
