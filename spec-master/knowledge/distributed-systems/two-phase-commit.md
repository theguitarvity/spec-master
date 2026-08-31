---
id: distributed.2pc
type: Principle
name: Two-Phase Commit
category: distributed-systems
applicable_roles:
  - architect
  - tech-lead
tags:
  - distributed
  - transactions
depth:
  architect: L3
---

# Two-Phase Commit

## Definition
A distributed transaction protocol where a coordinator asks all participants to 'prepare' (vote to commit or abort), then, only if everyone votes to commit, tells them all to actually commit — giving atomicity across multiple resources at the cost of blocking.

## Problem it addresses
A business transaction spanning multiple resources (databases, services) needs all-or-nothing semantics, but there's no single database transaction that can span them — 2PC was the classical answer, coordinating commit across independent resources.

## Core principles
- **Phase 1 (prepare)**: the coordinator asks every participant to prepare and vote; each participant locks its resources and votes commit or abort.
- **Phase 2 (commit/abort)**: if all participants voted commit, the coordinator tells everyone to commit; if any voted abort, it tells everyone to roll back.
- The protocol is **blocking**: participants hold their locks from the moment they vote 'commit' until the coordinator's final decision arrives — if the coordinator crashes mid-protocol, participants can be stuck holding locks indefinitely.

## Appropriate use
2PC fits tightly coupled, low-latency environments where all participants are reliably reachable and brief lock-holding during coordination is acceptable — it is rarely chosen for modern distributed/microservices systems for this reason.

## Inappropriate use
Avoid 2PC across service boundaries in a microservices architecture — the blocking behavior under coordinator or participant failure makes it a poor fit for systems that value availability and independent service failure domains; a Saga is the typical modern alternative.

## Trade-offs
2PC gives strong atomicity guarantees across resources, at the cost of blocking (locks held during the coordination window) and reduced availability if the coordinator or any participant is slow or unreachable — exactly the availability cost Sagas are designed to avoid by trading away strict atomicity for compensating actions.

## Typical violations
Using 2PC across services owned by different teams with independent uptime targets, where one team's outage now blocks every other participant's resource locks from releasing.

## Anti-patterns
Reaching for 2PC by default for any multi-service transaction, without considering that its blocking nature directly undermines the independent availability microservices are usually adopted to gain.

## Related concepts
- [[pattern.saga]]
- [[distributed.consensus]]
