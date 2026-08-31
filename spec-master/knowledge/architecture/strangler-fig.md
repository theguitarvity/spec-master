---
id: architecture.strangler-fig
type: Pattern
name: Strangler Fig Pattern
category: architecture
applicable_roles:
  - architect
  - tech-lead
tags:
  - migration
  - patterns
depth:
  architect: L4
---

# Strangler Fig Pattern

## Definition
Incremental migration from monolith to target architecture. Facade pattern, traffic routing.

## Problem it addresses
Rewriting a large legacy system in one big-bang cutover is high-risk: it freezes feature work for the duration, and any bug in the rewrite affects the entire system at once on cutover day.

## Core principles
- Named after the strangler fig vine, which grows around a host tree and gradually replaces it: build the new system incrementally alongside the old one.
- A routing facade sits in front of both systems and progressively redirects traffic, feature by feature or route by route, from the old system to the new one.
- The old system is only decommissioned once nothing routes to it anymore — there's no single cutover moment carrying all the risk.

## Appropriate use
Use it for migrating a monolith to microservices, replacing a legacy system with a rewrite, or any large migration where a big-bang cutover's risk is unacceptable and functionality can be moved incrementally.

## Inappropriate use
Skip the ceremony for small systems or components where a direct rewrite-and-swap is genuinely low-risk — running two systems in parallel with a routing facade adds overhead that isn't justified at small scale.

## Trade-offs
Running two systems (and a routing layer) in parallel for the migration period costs operational overhead and requires careful data-sync strategy for shared state, in exchange for a migration with no single high-risk cutover event and the ability to roll back per-route.

## Typical violations
Migrating routes at the facade layer but leaving both old and new systems writing to the same tables without a clear ownership boundary, causing data races during the transition period.

## Anti-patterns
A 'migration' that quietly turns into a permanent Distributed Monolith because the old system is never actually decommissioned once the easy 80% of routes are moved.

## Related concepts
- [[architecture.modular-monolith]]
- [[architecture.microservices]]
