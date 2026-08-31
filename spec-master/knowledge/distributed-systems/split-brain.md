---
id: distributed.split-brain
type: Principle
name: Split Brain
category: distributed-systems
applicable_roles:
  - architect
  - devops
tags:
  - distributed
  - replication
depth:
  architect: L3
  devops: L3
---

# Split Brain

## Definition
A failure mode where a network partition leaves two (or more) nodes each believing they are the sole leader/primary, and each independently accepting writes — producing divergent, conflicting state that must be reconciled once the partition heals.

## Problem it addresses
A leader-follower or primary-replica system that relies only on heartbeat timeouts to detect leader failure can be fooled by a network partition: the old leader is still alive and serving writes, but a follower, unable to reach it, elects a new leader — now two nodes both think they're in charge.

## Core principles
- Split brain requires two conditions together: a system with a single-writer assumption (a designated leader/primary), and a failure-detection mechanism that can be fooled by a partition into believing a reachable node is dead.
- **Fencing** (e.g. a fencing token that increases monotonically with each new leader term, which downstream resources reject if stale) prevents an old, partitioned-away leader from continuing to write once a new leader has been elected.
- Consensus protocols (Raft, Paxos) prevent split brain by requiring a quorum (majority) for leader election — a partition can produce at most one side with a majority, so at most one leader can ever be legitimately elected at a time.

## Appropriate use
Guard against split brain explicitly in any leader-election or primary-replica design — use quorum-based election and fencing tokens rather than simple heartbeat timeouts alone.

## Inappropriate use
Don't assume a naive heartbeat-timeout failover scheme is 'good enough' for a system with real correctness requirements on write ownership — it is precisely this design that produces split brain under partition.

## Trade-offs
Quorum-based leader election requires a majority of nodes to be reachable for the system to make progress at all (an availability cost during a partition), in exchange for the strong guarantee that at most one leader is ever active — the same CP-leaning trade-off CAP theorem describes.

## Typical violations
A primary-replica database failover script that promotes a replica to primary purely based on 'can't reach the old primary', with no fencing to stop the old primary from continuing to accept writes if it's actually still alive on the other side of the partition.

## Anti-patterns
Heartbeat-only failover without quorum or fencing is the specific anti-pattern that produces split brain; it is a common, costly gap in hand-rolled high-availability setups.

## Related concepts
- [[distributed.replication]]
- [[distributed.consensus]]
