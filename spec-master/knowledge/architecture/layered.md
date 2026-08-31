---
id: architecture.layered
type: Pattern
name: Layered Architecture
category: architecture
applicable_roles:
  - architect
  - tech-lead
tags:
  - architecture
depth:
  architect: L3
---

# Layered Architecture

## Definition
Presentation, Business Logic, Data Access layers. Strict vs. relaxed layering. When NOT to use: when performance or vertical slicing is needed.

## Problem it addresses
Without any structure, presentation, business rules, and data access code intermingle freely, so a UI change risks breaking a query and vice versa.

## Core principles
- Classic three layers: Presentation → Business Logic → Data Access, each depending only on the layer directly below.
- **Strict layering**: a layer may only call the layer immediately beneath it. **Relaxed layering**: layers may call any layer beneath them, trading purity for pragmatism.
- Layered architecture is a horizontal cut across the whole system, unlike Vertical Slice's per-feature cut.

## Appropriate use
Good default for straightforward CRUD-heavy applications with a genuinely shared data-access layer and no strong need for per-feature independence.

## Inappropriate use
Avoid strict layering when it forces high-throughput code through unnecessary layer hops, or when features are meant to evolve and deploy independently — layered architecture couples all features to the same shared layers.

## Trade-offs
Simple to understand and onboard onto, but every layer tends to grow to serve every feature, so cross-cutting changes ripple through all three layers and the codebase can become a 'distributed monolith in one process' at scale.

## Typical violations
A presentation-layer controller calling the data-access layer directly, skipping business logic validation that lives one layer down.

## Anti-patterns
The Anemic Domain Model often emerges from strict layering, where business logic drains into service classes because entities are treated as pure data-access-layer records.

## Related concepts
- [[architecture.hexagonal]]
- [[principle.separation-of-concerns]]
