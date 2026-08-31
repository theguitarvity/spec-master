---
id: architecture.bff
type: Pattern
name: Backend for Frontend
category: architecture
applicable_roles:
  - architect
  - tech-lead
  - frontend-dev
tags:
  - architecture
  - api
depth:
  architect: L3
---

# Backend for Frontend

## Definition
Client-specific aggregation layer. One BFF per client type, not one per team.

## Problem it addresses
A single generic API serving a rich web app, a mobile app, and a third-party integration ends up either over-fetching data for lightweight clients or under-fetching for data-hungry ones, and every client-specific quirk pollutes the shared API.

## Core principles
- One backend tailored per client type (web BFF, mobile BFF), each aggregating and shaping data specifically for that client's UI needs.
- The BFF owns client-specific aggregation and transformation logic, keeping the underlying domain services generic and client-agnostic.
- Rule of thumb: one BFF per client *type*, not one BFF per team or one per screen — over-splitting recreates the fragmentation problem at a finer grain.

## Appropriate use
Use a BFF when different client types have meaningfully different data shape or aggregation needs from the same underlying services — a mobile app needing a lean payload versus a web dashboard needing a richer, joined view.

## Inappropriate use
Skip it when there's only one client type, or when the different clients' needs are close enough that one well-designed generic API serves them all without contortion.

## Trade-offs
Extra services to own and deploy (one per client type) and some duplicated aggregation logic across BFFs, in exchange for each client getting an API precisely shaped for its needs without compromising the others.

## Typical violations
A 'mobile BFF' that ends up serving the web client too, quietly turning back into the single generic API the pattern was meant to avoid.

## Anti-patterns
Over-fragmentation — a BFF per screen or per feature team rather than per client type — reproduces Nano-services' overhead at the BFF layer.

## Related concepts
- [[architecture.api-gateway]]
