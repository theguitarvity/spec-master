---
id: antipattern.distributed-monolith
type: AntiPattern
name: Distributed Monolith
category: anti-patterns
applicable_roles:
  - architect
  - tech-lead
tags:
  - anti-pattern
  - architecture
depth:
  architect: L4
---

# Distributed Monolith

## Definition
Microservices boundaries without real independence. Symptoms: shared databases, synchronous chains, deployment coupling.

## Problem it addresses
Teams split a monolith into services expecting to gain independent deployability and fault isolation, but if the services still share a database, call each other synchronously in long chains, or must be deployed together, none of the actual benefits of microservices materialize — only the costs do.

## Core principles
- Symptoms: a shared database multiple services read/write directly, long synchronous call chains where service A must call B must call C to complete one request, and coordinated deployments where services must ship together despite being separate codebases.
- The result is worse than a monolith on both axes at once: all the operational complexity of a distributed system (network calls, partial failure, service discovery) with none of the independence a monolith's simplicity would have given up for it.
- Genuine service independence requires each service to own its own data and be deployable and testable without coordinating with the others — boundaries drawn without those properties don't actually decouple anything.

## Appropriate use
Recognize this pattern during architecture review whenever proposed 'services' share a database or require synchronized deploys — that's the signal to either merge them back into a modular monolith or redesign the boundary around true independence.

## Inappropriate use
Don't conclude from this anti-pattern that microservices are always wrong — the failure is specifically services split without the independence properties (data ownership, async boundaries, independent deploy) that justify the split in the first place.

## Trade-offs
There is no trade-off benefit here — this is a pure-cost failure mode: all of microservices' operational tax, none of its benefit.

## Typical violations
Two 'independent' services both reading and writing the same Postgres database directly, so a schema change in one silently breaks the other.

## Anti-patterns
This entry is itself the anti-pattern; its usual root causes are drawing service boundaries around [[architecture.microservices]] without a matching [[design.bounded-context]], and ignoring [[agile.conways-law]] when the org structure doesn't actually support independent teams per service.

## Related concepts
- [[architecture.microservices]]
- [[design.bounded-context]]
