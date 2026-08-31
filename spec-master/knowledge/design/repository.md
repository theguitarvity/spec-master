---
id: design.repository
type: Pattern
name: Repository Pattern
category: design
applicable_roles:
  - architect
  - tech-lead
  - backend-dev
tags:
  - design
  - patterns
depth:
  architect: L3
---

# Repository Pattern

## Definition
Collection-like interface over persistence. Domain layer defines interface, infrastructure implements.

## Problem it addresses
When domain/business logic calls the database or ORM directly, it becomes impossible to unit test without a live database, and swapping persistence technology means rewriting business logic instead of just the persistence layer.

## Core principles
- A repository presents a collection-like interface (`add`, `getById`, `remove`) over persistence, hiding the actual storage mechanism (SQL, a document store, an in-memory map for tests) behind that interface.
- The domain layer defines the repository interface (what it needs); the infrastructure layer implements it (how it's actually stored) — a direct application of Dependency Inversion.
- A repository operates at the aggregate boundary — one repository per aggregate root, not one per database table.

## Appropriate use
Use a repository at the boundary between domain logic and persistence whenever the domain needs to be testable without a live database, or whenever the storage technology might reasonably change.

## Inappropriate use
Don't add a repository abstraction around a purely technical, non-domain data access path (a raw analytics query with no domain invariant to protect) — that's just needless indirection over what is essentially a query.

## Trade-offs
An extra interface plus at least two implementations (real + in-memory/test) to maintain, in exchange for domain logic that can be fully unit tested without a live database and persistence that can be swapped independently.

## Typical violations
A 'repository' that just exposes the ORM's raw query builder or SQL directly, providing an interface in name only while still coupling every caller to the specific ORM's API.

## Anti-patterns
An Anemic Repository — one that mirrors database tables 1:1 rather than aggregate boundaries — tends to leak persistence concerns straight back into the domain layer it was meant to protect.

## Related concepts
- [[design.ddd]]
- [[principle.dependency-inversion]]
- [[architecture.hexagonal]]
