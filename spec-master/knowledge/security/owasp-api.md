---
id: security.owasp-api
type: Principle
name: OWASP API Security Top 10
category: security
applicable_roles:
  - architect
  - backend-dev
  - security
tags:
  - security
  - owasp
  - api
depth:
  security: L4
  architect: L3
  backend-dev: L2
---

# OWASP API Security Top 10

## Definition
A ranking, maintained separately from the general OWASP Top 10, of the most critical security risks specific to APIs — reflecting that APIs have distinct risk patterns (object-level authorization, excessive data exposure, rate limiting) not always centered in the general web app list.

## Problem it addresses
APIs are frequently the actual attack surface in modern applications (mobile apps, SPAs, and service-to-service calls all go through APIs), but general web-application security guidance doesn't always highlight API-specific risks like object-level authorization or unrestricted resource consumption clearly enough.

## Core principles
- **Broken Object Level Authorization (BOLA)**: the most common and highest-impact API risk — checking that a user is authenticated, but not that they're authorized for the *specific object* they're requesting (e.g. `/orders/12345` returning any user's order if they simply guess the ID).
- **Excessive Data Exposure**: returning a full internal object from an endpoint and relying on the client to filter fields, instead of the API only ever returning what's actually needed.
- **Lack of Resources & Rate Limiting**: no limits on request size, pagination, or request rate, letting a single client exhaust server resources.
- These risks are distinct from, and often not fully covered by, the general OWASP Top 10 — a system can pass a general web app review and still have serious API-specific gaps.

## Appropriate use
Review every API endpoint specifically for object-level authorization (does this check ownership of the specific resource ID, not just that the caller is logged in) and for data minimization in responses — do this as a distinct pass from general OWASP Top 10 review.

## Inappropriate use
Don't assume general authentication middleware or a general OWASP Top 10 review already covers object-level authorization — BOLA is specifically about per-object checks that generic middleware typically doesn't perform.

## Trade-offs
Object-level authorization checks and response field minimization add per-endpoint implementation and review overhead, in exchange for closing the single most commonly exploited class of real-world API vulnerabilities.

## Typical violations
An endpoint like `GET /invoices/{id}` that checks the caller is authenticated but never checks that the requested invoice actually belongs to the caller — any authenticated user can read any invoice by guessing or incrementing the ID.

## Anti-patterns
Relying solely on 'security through obscurity' of resource IDs (assuming they're unguessable) instead of an explicit per-object authorization check is the direct root cause of most BOLA findings.

## Related concepts
- [[security.owasp-top10]]
- [[security.auth]]
- [[security.rbac]]
