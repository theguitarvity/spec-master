---
id: security.secrets-management
type: Principle
name: Secrets Management
category: security
applicable_roles:
  - architect
  - tech-lead
  - backend-dev
  - devops
  - security
tags:
  - security
  - ops
depth:
  security: L4
  devops: L3
---

# Secrets Management

## Definition
Never in code/config files, Vault/KMS/environment injection. Secret rotation, SBOM.

## Problem it addresses
Secrets committed to source control, hardcoded in config files, or passed as plain environment variables in an insecure pipeline are trivially exposed the moment that repository, image, or log is accessed by anyone who shouldn't have them — and once committed to git history, a secret is compromised even if later deleted.

## Core principles
- Secrets (API keys, database credentials, signing keys) must never live in source code or committed config files — use a dedicated secrets manager (Vault, cloud KMS/Secrets Manager) or environment injection at deploy time instead.
- **Secret rotation**: secrets should be rotatable without a code change or downtime, and rotated periodically and immediately after any suspected exposure.
- **SBOM** (Software Bill of Materials): tracking exactly what dependencies (and their versions) are in a build is a prerequisite for knowing quickly whether a newly disclosed vulnerability or compromised package actually affects you.

## Appropriate use
Use a secrets manager or environment injection for every credential a running service needs, with access scoped per-service (least privilege) and rotation policies for anything long-lived.

## Inappropriate use
Don't pass secrets as plain command-line arguments (visible in process listings) or bake them into container images (visible to anyone who can pull the image) even if they're excluded from source control — the leak surface extends beyond just git.

## Trade-offs
A secrets manager adds operational infrastructure (another system to run/depend on, an access-control model of its own) in exchange for secrets that can be rotated, audited, and revoked without a code deploy.

## Typical violations
A `.env` file with real production credentials committed to git — and once in git history, deleting the file later does not remove the secret from history; it must be treated as compromised and rotated.

## Anti-patterns
Hardcoding secrets directly in source or config files, and reusing the same secret across environments (dev/staging/prod) so a lower-security environment's leak compromises production too.

## Related concepts
- [[security.owasp-top10]]
