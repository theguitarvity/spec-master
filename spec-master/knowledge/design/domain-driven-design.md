---
id: design.ddd
type: Principle
name: Domain-Driven Design
category: design
applicable_roles:
  - architect
  - tech-lead
  - backend-dev
tags:
  - design
  - ddd
depth:
  architect: L4
  tech-lead: L3
---

# Domain-Driven Design

## Definition
Strategic vs. Tactical DDD. Ubiquitous Language, Bounded Context, Context Map. Aggregate, Aggregate Root, Domain Event.

## Problem it addresses
Business logic scattered across a codebase without a shared vocabulary between developers and domain experts leads to a translation gap: code that technically works but doesn't map to how the business actually thinks about the problem, making every change a re-negotiation of meaning.

## Core principles
- **Ubiquitous Language**: a shared vocabulary between developers and domain experts, used consistently in conversation, documentation, and code — the same term means the same thing everywhere.
- **Strategic DDD**: identifying Bounded Contexts (explicit boundaries where a model and its language apply) and mapping relationships between them (Context Map).
- **Tactical DDD**: the building blocks used inside a bounded context — Aggregate, Aggregate Root, Entity, Value Object, Domain Event, Repository.
- DDD is most valuable for the **core domain** — the part of the system that is genuinely complex and differentiating; supporting/generic subdomains often don't need the same rigor.

## Appropriate use
Apply DDD's tactical patterns where business logic is genuinely complex and evolving (the core domain); apply strategic DDD (bounded contexts) whenever a system spans multiple distinct business capabilities with their own vocabulary.

## Inappropriate use
Don't apply full tactical DDD (aggregates, domain events, repositories) to a simple CRUD subdomain with no real business rules — that's ceremony without payoff; a generic subdomain is often better served by the simplest thing that works.

## Trade-offs
DDD's discipline (explicit language, bounded contexts, tactical patterns) costs upfront modeling effort and requires real access to domain experts, in exchange for a codebase whose structure actually mirrors the business it serves and stays understandable as complexity grows.

## Typical violations
Using different terms for the same concept in code versus in conversation with the business (e.g. code says 'Account', the business says 'Customer'), which quietly reintroduces the translation gap DDD exists to close.

## Anti-patterns
An Anemic Domain Model — objects with only getters/setters and no behavior, with all logic sitting in services — is the most common failure to actually apply DDD's tactical patterns even when the vocabulary is present.

## Related concepts
- [[design.aggregate]]
- [[design.bounded-context]]
- [[design.domain-event]]
