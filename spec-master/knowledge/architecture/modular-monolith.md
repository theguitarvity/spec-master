---
id: architecture.modular-monolith
type: Pattern
name: Modular Monolith
category: architecture
applicable_roles:
  - architect
  - tech-lead
tags:
  - architecture
depth:
  architect: L4
---

# Modular Monolith

## Definition
Strong module boundaries inside a single deployable. Often better than microservices for early-stage products. Migration path to microservices via Strangler Fig.

## Problem it addresses
Teams often jump to microservices to get module independence, but pay the full distributed-systems tax (network calls, partial failure, service discovery) before the domain boundaries are even well understood — premature distribution.

## Core principles
- A single deployable unit internally organized into modules with strong, enforced boundaries (no reaching into another module's internals, explicit public interfaces between modules).
- Gets most of microservices' organizational benefit (clear ownership, enforced boundaries) without the distributed-systems cost (network calls between modules stay in-process function calls).
- A natural stepping stone: well-bounded modules are what later get extracted into real services via Strangler Fig, once a boundary proves it needs independent scaling or deployment.

## Appropriate use
Use it for early-stage products where domain boundaries are still being learned, or for teams that want microservices' clarity of ownership without paying distributed-systems costs before they're needed.

## Inappropriate use
Don't use it as a permanent excuse to avoid ever extracting services once a module demonstrably needs independent scaling, independent deployment cadence, or a different technology — at that point the modular boundary has already done the hard job of making extraction cheap.

## Trade-offs
All modules still share one deployment (a bug in one module can still take down the process) and one scaling unit, in exchange for far simpler operations than microservices and boundaries that are cheap to get wrong and fix, since there's no network call to unwind.

## Typical violations
Modules that import each other's internal classes directly instead of going through a declared public interface, letting the 'strong boundary' erode back into a Big Ball of Mud with folder names.

## Anti-patterns
A modular monolith with unenforced boundaries is just a monolith with extra folders — Big Ball of Mud wearing a module-name costume.

## Related concepts
- [[architecture.microservices]]
- [[architecture.strangler-fig]]
