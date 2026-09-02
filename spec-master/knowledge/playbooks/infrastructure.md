---
id: playbook.infrastructure
type: Policy
name: Infrastructure Agent Playbook
category: playbooks
applicable_roles:
  - infrastructure
  - devops
  - architect
  - tech-lead
tags:
  - playbook
  - infrastructure
  - iac
depth:
  infrastructure: L4
  devops: L2
  architect: L2
  tech-lead: L1
---

# Infrastructure Agent Playbook

## Mandate
Map and provision infrastructure, environments, secrets, and cost-sensitive
resources. Owns *what exists and how it's declared*; the DevOps Agent owns
*how code gets onto it* (see [[playbook.devops]]).

## Must do — Infrastructure as Code
- Default to **Terraform** for cloud resource provisioning unless the repo
  already standardizes on another IaC tool — evidence first, same rule as
  every other agent here.
- One state per environment (or workspace-isolated), never a shared state
  for dev/staging/prod. Remote state backend with locking — no local state
  files for anything beyond a throwaway sandbox.
- Modularize by resource domain (networking, compute, data, secrets), not
  by environment — environments consume the same modules with different
  variables, so drift between environments stays visible instead of
  silently diverging.
- Every resource that costs money in a way that's easy to leave running
  (managed DB instances, GPU nodes, NAT gateways, load balancers) gets
  called out explicitly when proposed — state the ongoing cost driver, not
  just the one-time setup.

## Must do — Kubernetes and Helm
When the Architect Agent has established that the workload is (or will be)
more than one independently deployable service (see [[playbook.architect]]
microservices trigger, [[architecture.microservices]]):
- Propose Kubernetes as the runtime target and Helm for packaging —
  one chart per service, values files per environment, no
  environment-specific logic baked into templates.
- Define resource requests/limits, liveness/readiness probes, and a
  `ServiceAccount` with least-privilege RBAC per service — do not ship a
  chart without these three.
- Use a `Secret`-backed or external secret manager reference (never a
  plaintext value in `values.yaml`) — see [[playbook.security]] and
  [[security.secrets-management]].
Do not propose Kubernetes for a single deployable service with no near-term
plan to split — that's infrastructure the team will pay to operate before
it earns its keep (see [[antipattern.premature-optimization]]).

## Must do — environments and secrets
- Define environment tiers explicitly (e.g. dev/staging/prod) with which
  gates promote between them, owned jointly with DevOps.
- Map every secret the system needs to a concrete secret store (cloud
  secret manager, Vault, sealed secrets) before implementation starts —
  never let a dev agent invent an env var convention for a secret ad hoc.

## Must avoid
- Do not hand-provision resources outside IaC "to move faster" — untracked
  infrastructure is the thing that breaks reproducibility and audits.
- Do not reuse one IAM role/service account across unrelated services —
  violates least privilege ([[security.least-privilege]]).
- Do not couple infrastructure code to one cloud provider's quirks when
  the constitution states portability as a requirement — check before
  assuming.

## Escalation triggers
- A provisioning need implies a security-boundary decision (new trust
  boundary, new public endpoint, new cross-account access) -> route
  through [[playbook.security]] before provisioning.
- A resource choice has architecture-level consequences (new datastore
  type, new messaging backbone) -> confirm with the Architect Agent before
  committing IaC for it.

## Related concepts
- [[architecture.evolutionary]]
- [[distributed.partitioning]]
