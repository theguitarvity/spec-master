---
id: design.acl
type: Pattern
name: Anti-Corruption Layer
category: design
applicable_roles:
  - architect
  - tech-lead
tags:
  - design
  - patterns
depth:
  architect: L4
---

# Anti-Corruption Layer

## Definition
Translate between foreign context models and local ubiquitous language.

## Problem it addresses
Integrating directly with a foreign system's model (a legacy system, a third-party API, another bounded context with a different vocabulary) lets that foreign model's concepts and quirks leak into your own domain, corrupting its clarity and coupling your model to something you don't control.

## Core principles
- An anti-corruption layer (ACL) sits at the integration boundary and translates between the foreign model's language/shape and your own bounded context's ubiquitous language and model.
- The ACL is intentionally the *only* place that knows about the foreign system's specific representation — everything on your side of it speaks your own domain's language.
- Especially valuable when integrating with a legacy system you don't control and don't want your new domain model shaped by.

## Appropriate use
Add an ACL whenever integrating with an external or legacy system whose model doesn't match your bounded context's ubiquitous language — especially during a Strangler Fig migration away from a legacy system.

## Inappropriate use
Don't add an ACL between two contexts that already share a clean, well-aligned model (a Shared Kernel relationship) — the translation layer would just add overhead for boundaries that don't actually need translating.

## Trade-offs
An ACL costs a translation layer to build and maintain (and keep in sync as either side evolves), in exchange for keeping your own domain model clean and insulated from a foreign system's quirks, naming, and change schedule.

## Typical violations
Deserializing a legacy system's API response directly into your own domain entities, letting its field names, nullability quirks, and implicit assumptions bleed straight into your model.

## Anti-patterns
Skipping the ACL and directly coupling a clean domain model to a legacy system's shape is a common way a Big Ball of Mud starts forming at an integration boundary.

## Related concepts
- [[design.bounded-context]]
- [[architecture.strangler-fig]]
