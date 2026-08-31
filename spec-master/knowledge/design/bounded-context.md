---
id: design.bounded-context
type: Pattern
name: Bounded Context
category: design
applicable_roles:
  - architect
  - tech-lead
tags:
  - design
  - ddd
depth:
  architect: L4
---

# Bounded Context

## Definition
Explicit context boundaries, ubiquitous language per context. Context Map patterns: ACL, Shared Kernel, Open Host Service.

## Problem it addresses
A single shared model across an entire large system forces every team to agree on one meaning for every term, even when different parts of the business legitimately use the same word to mean different things (e.g. 'Product' means something different to Catalog than to Shipping).

## Core principles
- A bounded context is an explicit boundary within which a specific model and its ubiquitous language apply consistently — outside that boundary, the same term may mean something else entirely, and that's fine.
- **Context Map** patterns describe how contexts relate: **Shared Kernel** (a small shared model both contexts agree to jointly own), **Anti-Corruption Layer** (translate at the boundary instead of sharing a model), **Open Host Service** (a published, stable API a context exposes for others to integrate against), **Conformist** (downstream context just adopts upstream's model as-is).
- Bounded contexts frequently, but not always, map to service boundaries in a microservices architecture.

## Appropriate use
Draw bounded context boundaries wherever the same business term genuinely means different things to different parts of the organization, or wherever a team should be able to evolve its model independently of another team's.

## Inappropriate use
Don't split contexts finer than the organization's actual team/ownership boundaries just for theoretical purity — every extra context boundary adds a translation cost (mapping, ACLs) that must be justified by real independence needs.

## Trade-offs
Clear context boundaries prevent model conflation and let teams move independently, at the cost of explicit translation (context maps, anti-corruption layers) wherever contexts need to interoperate.

## Typical violations
Letting one context's internal model leak directly into another context's code (e.g. a downstream service deserializing an upstream service's internal database schema), collapsing the boundary that was supposed to protect both sides.

## Anti-patterns
A single shared model spanning the whole organization ('the one true Customer object everyone must use') is the anti-pattern bounded contexts specifically exist to break apart.

## Related concepts
- [[design.ddd]]
- [[architecture.microservices]]
