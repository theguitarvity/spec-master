---
id: distributed.consistency
type: Principle
name: Consistency Models
category: distributed-systems
applicable_roles:
  - architect
  - tech-lead
  - spec-master
tags:
  - distributed
  - data
depth:
  architect: L4
---

# Consistency Models

## Definition
Strong consistency, eventual consistency, causal consistency, linearizability, serializability. Hierarchy and trade-offs.

## Problem it addresses
Different parts of a system need different guarantees about how quickly and in what order writes become visible to reads — using the wrong consistency model either wastes performance on unneeded guarantees or introduces bugs from guarantees that were silently assumed but never actually provided.

## Core principles
- **Strong consistency / linearizability**: every read reflects the most recent write, as if there were only one copy of the data — the strongest, most expensive guarantee.
- **Serializability**: transactions appear to execute in some sequential order, even if actually interleaved — a transactional guarantee, related to but distinct from linearizability (about ordering within a value's history).
- **Causal consistency**: operations that are causally related are seen in the same order by everyone; unrelated operations may be seen in different orders — weaker than strong consistency but stronger than eventual.
- **Eventual consistency**: given no new writes, all replicas will *eventually* converge to the same value — the weakest common guarantee, cheapest to provide at scale.

## Appropriate use
Match the model to the actual business requirement: strong consistency for financial balances and inventory counts where staleness causes real harm; eventual consistency for data like view counts, recommendation caches, or social feeds where brief staleness is harmless.

## Inappropriate use
Don't default to eventual consistency for data where staleness produces a wrong business outcome (double-selling the last item in stock) just because it's cheaper — nor pay for strong consistency everywhere by default when most reads would tolerate staleness fine.

## Trade-offs
Stronger consistency models cost more coordination (and thus latency and reduced availability under partition); weaker models are cheaper and more available but push the burden of handling staleness or conflicting writes onto the application.

## Typical violations
Assuming a distributed cache or read replica is always up to date (implicitly assuming strong consistency) when the actual system only provides eventual consistency, leading to intermittent, hard-to-reproduce bugs.

## Anti-patterns
Silently relying on an unstated consistency assumption instead of explicitly documenting which model a given data path actually provides — a frequent root cause of 'it worked in testing but not in production under load' bugs.

## Related concepts
- [[distributed.cap]]
- [[distributed.replication]]
