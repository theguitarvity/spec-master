---
id: security.least-privilege
type: Principle
name: Least Privilege
category: security
applicable_roles:
  - architect
  - security
  - devops
tags:
  - security
  - principles
depth:
  security: L4
  architect: L3
---

# Least Privilege

## Definition
Minimum necessary permissions.

## Problem it addresses
Granting broad permissions 'to be safe' or 'because it's easier' means that when (not if) a credential, service, or account is compromised, the attacker inherits all of that unnecessary access too — turning a contained incident into a broad one.

## Core principles
- Every identity (user, service, process) should hold the minimum set of permissions needed to do its job, and nothing more.
- Applies at every layer: IAM roles, database grants, file permissions, API scopes, network access rules.
- Least privilege should be the default and permissions added deliberately as needed, not the reverse (start broad, narrow later) — narrowing broad access later rarely actually happens in practice.

## Appropriate use
Apply least privilege by default to every new service account, IAM role, database user, and API token — scope each one to exactly the resources and actions it needs, reviewed periodically as needs change.

## Inappropriate use
Don't grant admin/root/superuser access as a shortcut during development with the intention of tightening it 'later' before production — that tightening step is one of the most commonly skipped steps under deadline pressure.

## Trade-offs
Fine-grained permissions require more upfront design (defining exact scopes per role) and occasional friction when a legitimate new need requires a permission change, in exchange for bounding the blast radius of any single compromised credential.

## Typical violations
A service's database user granted full read/write access to every table when it only ever needs to read from and write to two of them.

## Anti-patterns
'God mode' service accounts or API keys with unscoped, all-resource access are one of the most common findings in real security audits, and directly violate this principle.

## Related concepts
- [[security.zero-trust]]
- [[security.rbac]]
