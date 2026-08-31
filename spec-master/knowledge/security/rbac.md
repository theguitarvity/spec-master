---
id: security.rbac
type: Pattern
name: Role-Based Access Control
category: security
applicable_roles:
  - architect
  - backend-dev
  - security
tags:
  - security
  - auth
depth:
  security: L4
  architect: L3
  backend-dev: L2
---

# Role-Based Access Control

## Definition
An authorization model where permissions are granted to roles, and users (or services) are assigned to roles, rather than permissions being granted to individuals directly.

## Problem it addresses
Granting permissions to individual users one at a time doesn't scale and is hard to audit — as an organization grows, no one can reliably answer 'who can do X' without checking every user's permissions individually.

## Core principles
- Permissions attach to roles (e.g. `editor`, `admin`, `viewer`); users are assigned one or more roles, and inherit the union of those roles' permissions.
- Simplifies auditing (list a role's permissions once, and every assignee's access is known) and simplifies onboarding/offboarding (assign or remove a role, not a long list of individual permissions).
- RBAC is coarse-grained by design — it answers 'what can this role do' well, but struggles to express access rules that depend on the specific resource or request context (e.g. 'edit only your own team's records'), which is where ABAC becomes necessary.

## Appropriate use
Use RBAC as the default authorization model whenever access rules can be expressed as a fixed, manageable set of roles with clear permission sets — the majority of internal tools and many customer-facing products.

## Inappropriate use
Don't force RBAC to express access rules that genuinely depend on resource attributes or context ('only the record's owner can edit it', 'only during business hours') via a combinatorial explosion of narrow roles — that's the signal to move the relevant rules to ABAC or a policy layer instead.

## Trade-offs
RBAC is simple to reason about and audit, but its coarse granularity means context-dependent rules either don't fit cleanly or require a proliferation of narrow, hard-to-maintain roles as an implicit workaround.

## Typical violations
Creating a new near-duplicate role for every minor permission variation needed (`editor-team-a`, `editor-team-b`, ...), instead of recognizing that the actual rule is attribute-based and belongs in a different model.

## Anti-patterns
Role explosion — dozens of narrow, overlapping roles created to approximate context-dependent rules RBAC wasn't designed to express — is a common, hard-to-audit failure mode of over-stretched RBAC.

## Related concepts
- [[security.least-privilege]]
- [[security.auth]]
