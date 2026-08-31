---
id: distributed.pacelc
type: Principle
name: PACELC Theorem
category: distributed-systems
applicable_roles:
  - architect
  - tech-lead
tags:
  - distributed
  - theory
depth:
  architect: L4
---

# PACELC Theorem

## Definition
During Partition: A vs C; Else: L(atency) vs C(onsistency). More nuanced than CAP.

## Problem it addresses
CAP theorem only describes behavior during a network partition, but partitions are rare — most of the time the system is running normally, and there's still a latency-vs-consistency trade-off to make even then. CAP alone doesn't capture that.

## Core principles
- PACELC extends CAP: **if Partitioned**, choose Availability or Consistency (as in CAP); **Else** (normal operation, no partition), choose Latency or Consistency.
- This makes explicit that even a 'CP' system under CAP still has a latency/consistency dial during normal operation — e.g. synchronous replication to all replicas (strong consistency, higher latency) versus async replication (lower latency, weaker consistency).
- PACELC is strictly more informative than CAP for choosing a database, since almost all operating time is the 'Else' branch, not the partition branch.

## Appropriate use
Use PACELC when comparing databases or replication strategies for their steady-state (non-partition) behavior, not just their partition-time behavior — most real-world tuning decisions live here.

## Inappropriate use
Don't stop the analysis at CAP alone when the actual operational question is about everyday latency under normal conditions — that's exactly the gap PACELC fills; citing CAP alone under-informs that decision.

## Trade-offs
Choosing lower latency in the Else branch (e.g. reading from the nearest replica) risks reading stale data even with no partition present; choosing consistency there costs latency on every request, not just during rare partition events.

## Typical violations
Selecting a database purely on its CAP classification (e.g. 'it's CP so it's safe') without checking its normal-operation latency/consistency trade-off, which is what actually dominates day-to-day behavior.

## Anti-patterns
Treating CAP as the complete theory of distributed consistency trade-offs, when PACELC's Else branch describes the overwhelming majority of a system's actual runtime.

## Related concepts
- [[distributed.cap]]
