---
id: architecture.clean
type: Pattern
name: Clean Architecture
category: architecture
applicable_roles:
  - architect
  - tech-lead
tags:
  - architecture
depth:
  architect: L4
  tech-lead: L3
---

# Clean Architecture

## Definition
Entities, Use Cases, Interface Adapters, Frameworks & Drivers. Dependency Rule: inward only.

## Problem it addresses
Without an explicit rule about which layer may depend on which, dependencies tend to point wherever is convenient in the moment, and business rules end up entangled with UI frameworks, databases, and other volatile details.

## Core principles
- Concentric layers: Entities (enterprise-wide business rules) → Use Cases (application-specific business rules) → Interface Adapters (controllers, presenters, gateways) → Frameworks & Drivers (web framework, DB, UI).
- The **Dependency Rule**: source code dependencies point only inward. Nothing in an inner circle can know anything about an outer circle.
- Data crossing a boundary is a simple data structure, not an entity of the outer layer's framework, to keep inner layers framework-agnostic.

## Appropriate use
Use it for systems expected to outlive a specific framework or delivery mechanism, or where business rules are complex enough to need isolated, framework-free testing.

## Inappropriate use
Skip the full four-ring ceremony for a small service or prototype where the framework is not expected to change and the business logic is thin — the layering overhead won't be recovered.

## Trade-offs
More indirection and boilerplate for mapping data across layer boundaries, in exchange for business rules that survive a framework or database swap untouched.

## Typical violations
A use case class that directly returns a Django/ActiveRecord model instead of a plain data structure, silently coupling the application layer to the ORM.

## Anti-patterns
Distributed Monolith and Big Ball of Mud, same as Hexagonal — Clean Architecture and Hexagonal are largely interchangeable expressions of the same Dependency Inversion idea at the architectural scale.

## Related concepts
- [[architecture.hexagonal]]
- [[architecture.onion]]
