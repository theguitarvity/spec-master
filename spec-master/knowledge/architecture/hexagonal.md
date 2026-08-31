---
id: architecture.hexagonal
type: Pattern
name: Hexagonal Architecture
category: architecture
applicable_roles:
  - architect
  - tech-lead
  - backend-dev
  - fullstack-dev
tags:
  - architecture
  - ports-and-adapters
depth:
  architect: L4
  tech-lead: L3
  backend-dev: L3
---

# Hexagonal Architecture

## Definition
Ports and Adapters, driving vs driven sides. Primary/secondary adapters, domain isolation. When to use: when core domain logic must be independent of delivery and infrastructure. Typical violations: domain code importing Spring/Express/etc., repositories in domain layer.

## Problem it addresses
Business logic that directly calls a database driver, an HTTP framework, or a message broker SDK cannot be unit tested without those dependencies running, and cannot be reused if the delivery mechanism changes (REST today, gRPC tomorrow).

## Core principles
- The domain core sits in the center and defines **ports** (interfaces) for everything it needs from the outside world.
- **Driving/primary adapters** (a REST controller, a CLI, a test) call INTO the core through an inbound port.
- **Driven/secondary adapters** (a Postgres repository, an S3 client) are called BY the core through an outbound port the core defines and owns.
- The core never imports a framework or infrastructure library directly — only its own ports.

## Appropriate use
Use hexagonal architecture when core domain logic must remain independent of delivery mechanism and infrastructure — services with real business rules, multiple entry points (API + CLI + scheduled job), or a need for fast, infrastructure-free unit tests.

## Inappropriate use
Skip it for thin CRUD services with no real domain logic to protect — a hexagon around a service that just maps HTTP requests to database rows adds ceremony with no corresponding benefit.

## Trade-offs
More files (port interface + adapter + implementation per external dependency) and an upfront design cost, in exchange for a domain core that is fast to test and portable across delivery mechanisms and infrastructure choices.

## Typical violations
Domain code that imports `express`, `django.db.models`, or a specific ORM's session object directly, or a repository interface defined inside the infrastructure layer instead of owned by the domain.

## Anti-patterns
Distributed Monolith and Big Ball of Mud both often trace back to skipping this boundary; a lighter local symptom is an 'Anemic Domain Model' wrapped by services that reach straight into infrastructure.

## Related concepts
- [[architecture.clean]]
- [[architecture.onion]]
- [[principle.dependency-inversion]]
