---
id: architecture.microservices
type: Pattern
name: Microservices
category: architecture
applicable_roles:
  - architect
  - tech-lead
tags:
  - architecture
  - distributed
depth:
  architect: L4
---

# Microservices

## Definition
Independent deployability, bounded contexts, distributed tradeoffs. NOT a silver bullet: operational complexity cost. Anti-patterns: distributed monolith, nano-services, chatty services.

## Problem it addresses
A single large monolith forces every team to deploy together, share one codebase's blast radius, and scale the whole application even when only one part is under load.

## Core principles
- Independent deployability: each service ships on its own schedule, without coordinating a release train with other services.
- Services are organized around bounded contexts (business capabilities), not technical layers.
- Decentralized data: each service owns its own data store; no shared database across service boundaries.
- Microservices are not a silver bullet — they trade in-process complexity for distributed-systems complexity (network calls, partial failure, eventual consistency).

## Appropriate use
Adopt microservices when independent team scaling, independent deployment cadence, or independent technology choice per service is a real, current need — not a hypothetical future one.

## Inappropriate use
Avoid microservices for a new product with one small team and unclear domain boundaries — splitting boundaries wrong before the domain is understood is expensive to undo across network calls, unlike undoing a wrong module boundary in a monolith.

## Trade-offs
Independent deployability and scaling in exchange for operational complexity: service discovery, distributed tracing, network latency, partial failure handling, and eventual consistency across service boundaries.

## Typical violations
Splitting services along technical layers (a 'database service', a 'business logic service') instead of business capabilities, forcing every feature to touch multiple services for one logical change.

## Anti-patterns
Distributed Monolith (services split without independence — shared database, synchronous call chains, coupled deploys) and Nano-services (splitting so finely that network overhead dwarfs any benefit).

## Related concepts
- [[architecture.eda]]
- [[architecture.api-gateway]]
- [[distributed.cap]]
