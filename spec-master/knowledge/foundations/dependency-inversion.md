---
id: principle.dependency-inversion
type: Principle
name: Dependency Inversion
category: foundations
applicable_roles:
  - architect
  - tech-lead
  - backend-dev
tags:
  - design
  - solid
depth:
  architect: L4
  tech-lead: L3
---

# Dependency Inversion

## Definition
Abstractions, not concretions; DIP vs DI vs IoC distinctions.

## Problem it addresses
When high-level policy code directly imports and calls low-level implementation details (a specific database driver, a specific HTTP client), that policy becomes impossible to test or reuse without dragging the concrete infrastructure along with it.

## Core principles
- High-level modules should not depend on low-level modules; both should depend on abstractions.
- Abstractions should not depend on details; details should depend on abstractions — the interface is owned by the consumer (the domain), not the implementer (the infrastructure).
- Distinguish three related but different terms: **DIP** (the design principle above), **Dependency Injection** (the mechanical technique of passing dependencies in rather than constructing them internally), and **Inversion of Control** (the broader pattern where a framework/container calls your code rather than your code calling the framework).

## Appropriate use
Apply DIP at the boundary between domain/business logic and infrastructure (databases, external APIs, filesystems) so the domain can be tested and evolved without a live database or network call.

## Inappropriate use
Do not invert every dependency reflexively — a pure utility function calling another pure utility function needs no interface between them; DIP earns its keep specifically at volatile, swappable, or hard-to-test boundaries.

## Trade-offs
Introducing an interface plus a concrete adapter costs an extra file and a layer of indirection to navigate, in exchange for the domain layer being unit-testable in isolation and the infrastructure being swappable without touching business logic.

## Typical violations
A domain service that imports a specific ORM model or calls `requests.get()` directly instead of depending on a repository/gateway interface, making it impossible to unit test without a live database or network.

## Anti-patterns
Big Ball of Mud results when DIP is ignored system-wide; a lighter-weight symptom is a 'God Config' object threaded everywhere instead of narrow, purpose-specific abstractions.

## Related concepts
- [[principle.solid]]
- [[architecture.hexagonal]]
