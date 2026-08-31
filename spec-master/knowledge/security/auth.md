---
id: security.auth
type: Principle
name: Authentication & Authorization
category: security
applicable_roles:
  - architect
  - tech-lead
  - backend-dev
  - frontend-dev
  - security
tags:
  - security
  - auth
depth:
  security: L4
  architect: L3
---

# Authentication & Authorization

## Definition
OAuth2 flows (Authorization Code + PKCE recommended). OIDC for identity, JWT pitfalls (algorithm confusion, expiry). RBAC vs ABAC.

## Problem it addresses
Authentication (who are you) and authorization (what are you allowed to do) are frequently conflated or implemented ad hoc, leading to systems that correctly identify a user but fail to correctly restrict what that identified user can access.

## Core principles
- **OAuth2** is an authorization framework, not an authentication protocol by itself — the **Authorization Code flow with PKCE** is the recommended flow for both web and mobile/native clients today (the older Implicit flow is deprecated due to token-leakage risk).
- **OIDC (OpenID Connect)** layers identity/authentication on top of OAuth2, providing the actual 'who is this user' answer that OAuth2 alone doesn't guarantee.
- **JWT pitfalls**: algorithm confusion attacks (accepting `alg: none` or letting an attacker choose a weak/symmetric algorithm when the verifier expected asymmetric), and forgetting to enforce token expiry/revocation — a JWT is self-contained and hard to revoke early without an additional deny-list mechanism.
- **RBAC** (Role-Based Access Control) assigns permissions via roles, simple to reason about but coarse; **ABAC** (Attribute-Based Access Control) evaluates permissions from attributes of the user/resource/context, more flexible but more complex to audit.

## Appropriate use
Use OAuth2 Authorization Code + PKCE with OIDC for any real user-facing authentication rather than a bespoke scheme; choose RBAC by default for straightforward permission models, moving to ABAC only when access rules genuinely can't be expressed as a fixed set of roles.

## Inappropriate use
Don't implement custom session/token schemes when a well-vetted OAuth2/OIDC library and provider is available — homegrown auth is one of the highest-risk areas to build from scratch.

## Trade-offs
Standard protocols (OAuth2/OIDC) cost integration complexity (redirects, token refresh, provider setup) in exchange for battle-tested security properties; ABAC's flexibility costs a harder-to-audit, harder-to-reason-about permission model compared to RBAC's simplicity.

## Typical violations
Storing long-lived JWTs with no expiry or revocation path, so a stolen token remains valid indefinitely with no way to invalidate it short of rotating the signing key for everyone.

## Anti-patterns
Rolling a custom authentication scheme instead of using OAuth2/OIDC, and checking only authentication ('is this a valid session') without a corresponding authorization check ('is this specific action allowed for this specific user') — the root cause of most Broken Access Control findings.

## Related concepts
- [[security.zero-trust]]
- [[security.least-privilege]]
