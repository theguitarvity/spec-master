---
id: distributed.cap
type: Principle
name: CAP Theorem
category: distributed-systems
applicable_roles:
  - architect
  - tech-lead
  - devops
  - spec-master
tags:
  - distributed
  - theory
depth:
  architect: L4
---

# CAP Theorem

## Definition
Consistency, Availability, Partition Tolerance — pick 2. Real world: network partitions always happen → CP vs AP choice. PACELC extension. Common misconception: "we don't need consistency" = we chose AP.

## Problem it addresses
Distributed data stores must decide what to do when a network partition splits nodes from each other — and that decision is forced, not optional, because partitions happen in real networks regardless of design intent.

## Core principles
- Consistency (every read sees the latest write), Availability (every request gets a non-error response), Partition tolerance (the system keeps functioning despite dropped/delayed messages between nodes) — under a real partition, pick at most 2.
- Partition tolerance is not optional in practice — real networks partition — so the actual choice CAP forces is between Consistency and Availability during a partition: **CP** (reject requests rather than serve stale/conflicting data) or **AP** (keep serving, accept temporary inconsistency).
- The common misconception 'we don't need consistency' is really 'we chose AP' — a specific, consequential trade-off, not the absence of one.

## Appropriate use
Use CAP explicitly when choosing or evaluating a distributed data store or designing a service's own replication/consistency strategy — it should drive a stated, deliberate CP-vs-AP decision, not be left implicit.

## Inappropriate use
Don't invoke CAP to justify skipping consistency guarantees a business process actually needs (e.g. account balances) just because 'CAP says pick 2' — for those flows, choose CP or design explicit compensation for AP's temporary inconsistency; CAP doesn't excuse an unconsidered choice.

## Trade-offs
CP systems reject requests during a partition to preserve correctness, harming availability; AP systems keep serving but risk stale or conflicting reads that must be reconciled later — there is no configuration that avoids this trade-off during an actual partition.

## Typical violations
Choosing a database advertised as 'highly available' without checking what it does to consistency during a partition, then being surprised by conflicting writes after a network blip.

## Anti-patterns
Treating CAP as a marketing checkbox ('our system is available AND consistent') rather than as a forced trade-off that only manifests during partitions is a common, costly misunderstanding.

## Related concepts
- [[distributed.consistency]]
- [[distributed.pacelc]]
