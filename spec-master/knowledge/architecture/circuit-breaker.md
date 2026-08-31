---
id: pattern.circuit-breaker
type: Pattern
name: Circuit Breaker
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
---

# Circuit Breaker

## Definition
Closed / Open / Half-Open states. Prevents cascade failures, fallback strategies.

## Problem it addresses
When a downstream dependency starts failing or timing out, callers that keep retrying it immediately pile up load on an already-struggling service and burn their own resources (threads, connections) waiting on doomed calls, often cascading the failure upstream.

## Core principles
- Three states: **Closed** (calls flow normally, failures counted), **Open** (calls fail immediately without hitting the dependency, once a failure threshold is crossed), **Half-Open** (after a cooldown, a limited number of trial calls test whether the dependency has recovered).
- The breaker protects the caller (freeing it from waiting on a doomed call) and the callee (giving it room to recover instead of being hit with more load while struggling).
- Pairs naturally with a fallback: when Open, return a cached value, a default, or a graceful degradation instead of just an error.

## Appropriate use
Use circuit breakers around any call to an external dependency (another service, a third-party API, a database) whose failure shouldn't cascade into the caller becoming unavailable too.

## Inappropriate use
Skip it for calls with no meaningful fallback and no risk of pile-up (a single, low-volume internal call already protected by a tight timeout) — the added state machine is overhead without payoff there.

## Trade-offs
Added complexity (state, thresholds, cooldown tuning) and an explicit fallback strategy to design, in exchange for containing failure instead of letting it cascade upstream.

## Typical violations
Setting the failure threshold so high, or the cooldown so short, that the breaker never actually opens before the caller's own resources are already exhausted — a circuit breaker that never trips provides no protection.

## Anti-patterns
Cascading Failures is the exact failure mode circuit breakers exist to contain; using unlimited retries with no breaker and no backoff is the anti-pattern that produces cascading failures and retry storms.

## Related concepts
- [[pattern.bulkhead]]
- [[distributed.cascading-failures]]
