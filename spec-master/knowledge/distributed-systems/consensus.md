---
id: distributed.consensus
type: Principle
name: Consensus Algorithms
category: distributed-systems
applicable_roles:
  - architect
  - tech-lead
tags:
  - distributed
  - theory
depth:
  architect: L3
---

# Consensus Algorithms

## Definition
Paxos, Raft basics — leader election, quorum. Why it's hard: FLP impossibility.

## Problem it addresses
Multiple nodes in a distributed system often need to agree on a single value or ordering (who's the leader, what's the next committed log entry) even though messages can be delayed, dropped, or reordered, and nodes themselves can crash at any point.

## Core principles
- Consensus algorithms (Paxos, Raft) let a cluster of nodes agree on a value despite failures, using leader election and a quorum (majority) requirement for any decision to be considered committed.
- Raft was designed specifically to be more understandable than Paxos while providing equivalent guarantees, which is why most modern systems (etcd, Consul) implement Raft rather than classic Paxos.
- **FLP impossibility** is why this is fundamentally hard: in a fully asynchronous network with even one faulty node, no algorithm can guarantee consensus in bounded time — practical algorithms sidestep this with timeouts and randomization, trading a small chance of extra delay for a working system.

## Appropriate use
Reach for a consensus-based system (or a managed one like etcd/ZooKeeper/Consul) when you need strongly consistent leader election, distributed locking, or a small amount of strongly consistent configuration/coordination state.

## Inappropriate use
Don't roll your own consensus protocol for a business problem — it's an extremely easy thing to get subtly wrong; use a battle-tested implementation (Raft-based store) instead of implementing leader election or distributed locking from scratch.

## Trade-offs
Consensus provides strong agreement guarantees at the cost of requiring a majority quorum to be reachable for any decision — the cluster becomes unavailable for writes if too many nodes are partitioned away, a direct manifestation of the CP choice in CAP.

## Typical violations
Implementing 'leader election' via a simple heartbeat/timeout scheme without quorum guarantees, which is vulnerable to split-brain under partition — exactly the class of bug real consensus protocols are designed to avoid.

## Anti-patterns
Hand-rolled distributed locking or leader election without quorum semantics is a frequent source of subtle, hard-to-reproduce production incidents — a case where reinventing a well-solved wheel is a genuine anti-pattern.

## Related concepts
- [[distributed.replication]]
- [[distributed.cap]]
