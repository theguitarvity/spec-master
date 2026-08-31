---
id: security.zero-trust
type: Principle
name: Zero Trust Architecture
category: security
applicable_roles:
  - architect
  - security
  - devops
tags:
  - security
  - architecture
depth:
  security: L4
  architect: L3
---

# Zero Trust Architecture

## Definition
Never trust, always verify. Least privilege, microsegmentation, continuous validation.

## Problem it addresses
Traditional perimeter security assumes anything inside the corporate network is trustworthy — but that assumption fails the moment an attacker compromises any single internal system or credential, since nothing else inside the perimeter is checking them.

## Core principles
- 'Never trust, always verify' — no request is implicitly trusted based on network location (being 'inside the VPN' grants nothing by itself); every request is authenticated and authorized on its own merits.
- **Least privilege** (see [[security.least-privilege]]) as the enforcement mechanism: every identity, service, and request gets only the access it specifically needs.
- **Microsegmentation**: network access is restricted to narrow, specific paths between services rather than broad subnet-level trust, limiting how far a compromise can spread.
- **Continuous validation**: trust is re-evaluated per-request (or per-session with short expiry), not granted once and assumed to hold indefinitely.

## Appropriate use
Apply zero trust principles to any system where a single compromised credential or internal host should not translate into broad access — which is effectively every modern production system, especially multi-service and cloud-hosted ones.

## Inappropriate use
Don't treat 'we have zero trust' as a checkbox achieved by adding an identity provider — it requires the underlying access model (service-to-service auth, microsegmented network policy) to actually enforce per-request verification, not just per-perimeter.

## Trade-offs
Verifying every request individually (mutual TLS between services, short-lived tokens, per-request authorization checks) costs implementation and operational complexity, in exchange for containing a compromise to exactly what that one compromised identity/host can reach, instead of the whole internal network.

## Typical violations
A service that trusts any request coming from inside the VPC without independently authenticating and authorizing it, so a single compromised internal service can call any other internal service unchecked.

## Anti-patterns
The 'castle-and-moat' model — hard perimeter, soft interior — is the specific model zero trust replaces, and remains a common anti-pattern in systems that add strong perimeter auth but nothing internally.

## Related concepts
- [[security.least-privilege]]
- [[security.owasp-top10]]
