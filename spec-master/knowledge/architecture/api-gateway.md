---
id: architecture.api-gateway
type: Pattern
name: API Gateway
category: architecture
applicable_roles:
  - architect
  - tech-lead
tags:
  - architecture
  - api
depth:
  architect: L3
---

# API Gateway

## Definition
Single entry point, cross-cutting concerns, BFF variant. Anti-pattern: smart gateway (business logic in gateway).

## Problem it addresses
When every client calls every backend service directly, cross-cutting concerns (auth, rate limiting, TLS termination, request logging) must be reimplemented in every service, and clients must track every service's network location.

## Core principles
- A single entry point in front of a set of backend services, handling cross-cutting concerns once instead of per-service.
- Typical responsibilities: routing, authentication, rate limiting, request/response transformation, TLS termination.
- The **Backend for Frontend (BFF)** variant specializes the gateway per client type, rather than one generic gateway serving all clients identically.

## Appropriate use
Use an API gateway when multiple services need common cross-cutting handling and clients shouldn't need to know internal service topology — most microservices deployments benefit from one.

## Inappropriate use
Don't route through a gateway for internal service-to-service calls that don't need the client-facing concerns (auth, rate limiting) the gateway exists to centralize — that adds a network hop and a shared point of failure for no benefit.

## Trade-offs
Centralizes cross-cutting concerns and simplifies clients, at the cost of a new critical-path component that must scale with all traffic and a new single point of failure if not made highly available.

## Typical violations
Putting business logic — not just cross-cutting concerns — into the gateway, so it starts making domain decisions instead of just routing and enforcing policy.

## Anti-patterns
'Smart gateway, dumb services' — the anti-pattern where business logic accumulates in the gateway, turning it into an undocumented, hard-to-test monolith sitting in front of otherwise well-designed services.

## Related concepts
- [[architecture.microservices]]
- [[architecture.bff]]
