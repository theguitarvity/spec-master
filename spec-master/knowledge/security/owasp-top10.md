---
id: security.owasp-top10
type: Principle
name: OWASP Top 10
category: security
applicable_roles:
  - architect
  - tech-lead
  - backend-dev
  - frontend-dev
  - qa
  - security
tags:
  - security
  - owasp
depth:
  security: L4
  architect: L3
---

# OWASP Top 10

## Definition
A01 Broken Access Control through A10 SSRF. Each item: definition, example, mitigation.

## Problem it addresses
Most web application breaches exploit a small, recurring set of mistake categories, not exotic novel attacks — teams that don't know this list keep reinventing the same vulnerabilities the industry has already catalogued and knows how to prevent.

## Core principles
- A community-maintained ranking of the most critical web application security risks, updated periodically (categories evolve release to release, but the pattern holds): access control failures, cryptographic failures, injection, insecure design, security misconfiguration, vulnerable/outdated components, authentication failures, data integrity failures, logging/monitoring failures, and server-side request forgery (SSRF).
- Each category has known, well-documented mitigations — this list is a checklist of what to actively defend against, not a mystery.
- 'Broken Access Control' has topped the list in recent editions — checking authentication is not the same as checking authorization for the specific resource being accessed.

## Appropriate use
Use the OWASP Top 10 as a baseline review checklist for any web-facing application — during design review (insecure design, access control), code review (injection, crypto misuse), and dependency management (vulnerable components).

## Inappropriate use
Don't treat OWASP Top 10 compliance as a complete security program — it's a baseline against the most common web app risks, not a substitute for threat modeling specific to your system's actual attack surface.

## Trade-offs
Actively defending against each category costs real engineering time (parameterized queries, output encoding, dependency scanning, access-control tests) but the alternative — an unpatched category — is a well-known, actively-scanned-for hole that attackers specifically probe for.

## Typical violations
Building SQL queries via string concatenation with user input (injection), or checking only 'is this user logged in' rather than 'is this user allowed to access this specific resource' (broken access control, e.g. an insecure direct object reference).

## Anti-patterns
Rolling your own authentication/crypto instead of using vetted libraries, and 'security through obscurity' (hiding an endpoint instead of authorizing it) are recurring anti-patterns that map directly onto multiple Top 10 categories at once.

## Related concepts
- [[security.owasp-api]]
- [[security.zero-trust]]
