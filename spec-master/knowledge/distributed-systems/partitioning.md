---
id: distributed.partitioning
type: Principle
name: Data Partitioning
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

# Data Partitioning

## Definition
Hash partitioning, range partitioning, consistent hashing. Hot partitions anti-pattern.

## Problem it addresses
A dataset that grows beyond what a single node can store or serve must be split across multiple nodes — but the way it's split determines whether load stays balanced or concentrates dangerously on a few nodes.

## Core principles
- **Hash partitioning**: distribute records by a hash of the key across nodes — gives even distribution for most workloads but destroys range-query locality (adjacent keys land on unrelated nodes).
- **Range partitioning**: keep contiguous key ranges together on a node — supports efficient range scans, but is vulnerable to uneven access patterns (e.g. all writes going to the most recent timestamp range).
- **Consistent hashing**: a hashing scheme designed so that adding or removing a node only reshuffles a small fraction of keys, instead of the near-total reshuffle a naive `hash(key) % N` scheme would require.

## Appropriate use
Choose hash partitioning by default for workloads without a real range-query need; choose range partitioning when range scans (e.g. 'all events between two timestamps') are a core access pattern; use consistent hashing whenever the number of nodes is expected to change over the system's lifetime.

## Inappropriate use
Don't use naive `hash(key) % N` partitioning in a system where nodes are added or removed dynamically — the near-total key reshuffle on every topology change makes rebalancing prohibitively expensive.

## Trade-offs
Hash partitioning sacrifices range-query locality for balance; range partitioning sacrifices balance-under-skew for range-query efficiency — the right choice depends entirely on the dominant access pattern, and getting it wrong shows up as uneven load, not a functional bug.

## Typical violations
Partitioning event data by a monotonically increasing timestamp key with naive range partitioning, so all new writes land on the single node owning the current time range — a classic hot partition.

## Anti-patterns
The 'hot partition' anti-pattern — a partitioning scheme that looks balanced in aggregate but concentrates the actual access pattern (writes, in particular) on one node — is one of the most common distributed data-store production issues.

## Related concepts
- [[distributed.replication]]
- [[distributed.cap]]
