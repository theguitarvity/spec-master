---
id: distributed.replication
type: Principle
name: Replication
category: distributed-systems
applicable_roles:
  - architect
  - devops
tags:
  - distributed
  - data
depth:
  architect: L3
---

# Replication

## Definition
Leader-follower, multi-leader, leaderless. Replication lag, split brain.

## Problem it addresses
A single copy of data is a single point of failure and a scaling bottleneck for reads — replication solves both, but introduces the problem of keeping copies in agreement with each other.

## Core principles
- **Leader-follower (single-leader)**: all writes go to one leader, which propagates changes to followers; simple, but the leader is a bottleneck and a failover event.
- **Multi-leader**: multiple nodes accept writes and propagate to each other; better write availability across regions, but conflicting concurrent writes must be resolved.
- **Leaderless**: any replica can accept a write (e.g. Dynamo-style, using quorum reads/writes); high availability, with conflict resolution pushed to read time (e.g. via vector clocks) or a last-write-wins policy.
- **Replication lag**: followers trail the leader by some delay — the source of most 'read your own write doesn't show up immediately' bugs.
- **Split brain**: a failure mode where a network partition leaves two nodes both believing they are the leader, each accepting writes independently — a serious correctness hazard for leader-follower systems if not guarded against.

## Appropriate use
Choose leader-follower for simplicity when write conflicts must never happen; choose multi-leader or leaderless when write availability across regions or during node failure matters more than avoiding conflict resolution complexity.

## Inappropriate use
Don't pick leaderless/multi-leader replication for data with strict invariants (e.g. a unique username) without a real conflict-resolution strategy — concurrent writes will produce conflicts that silent last-write-wins can corrupt.

## Trade-offs
More replicas and more replication topology sophistication buy availability and read scalability, at the cost of either write bottlenecking (single-leader) or conflict-resolution complexity (multi-leader/leaderless) and, in all cases, some degree of replication lag to reason about.

## Typical violations
Reading from a follower immediately after writing to the leader and treating a stale (pre-replication) result as authoritative, without a read-your-writes strategy.

## Anti-patterns
Ignoring split-brain risk in a leader-follower setup — no fencing token or quorum-based leader election — can let two nodes accept conflicting writes simultaneously after a partition heals.

## Related concepts
- [[distributed.consistency]]
- [[distributed.split-brain]]
