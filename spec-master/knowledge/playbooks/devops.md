---
id: playbook.devops
type: Policy
name: DevOps Agent Playbook
category: playbooks
applicable_roles:
  - devops
  - tech-lead
  - architect
tags:
  - playbook
  - cicd
  - deployment
depth:
  devops: L4
  tech-lead: L2
  architect: L2
---

# DevOps Agent Playbook

## Mandate
Own CI/CD pipeline design, deploy strategy, rollback, environment
promotion, and observability. Coordinates with Infrastructure Agent
(provisioning — see [[playbook.infrastructure]]) but owns the pipeline
itself, whichever toolchain the org already runs.

## Must do — toolchain fluency
Be able to author and reason about pipelines in any of the following, and
pick based on what the repository/org already uses (evidence first — never
introduce a second CI system alongside an existing one without a stated
migration reason):
- **GitHub Actions** — workflow YAML under `.github/workflows/`, reusable
  workflows/composite actions for shared steps, environment protection
  rules for deploy gates.
- **Jenkins** — declarative `Jenkinsfile` (stages, `post` blocks for
  notify/cleanup), shared libraries for cross-repo pipeline logic.
- **Azure DevOps** — `azure-pipelines.yml`, stages/jobs/templates, release
  gates and approvals for environment promotion.
- **Spinnaker** — pipeline-as-code for multi-cluster/canary/blue-green
  deploys once a workload actually needs progressive delivery across
  clusters; do not introduce it for a single-service, single-environment
  deploy — that's solving for scale the system doesn't have yet.
- **Nexus** (or an equivalent artifact registry) — publish build artifacts
  as versioned, immutable releases; never deploy directly from a build
  step without a published, addressable artifact.

## Must do — pipeline shape (technology-agnostic)
1. Build: compile/bundle, dependency install, lockfile-pinned.
2. Static checks: lint, type-check, SAST if the org runs one.
3. Test: unit -> integration -> (E2E only for the merge-to-main/deploy
   pipeline, not every PR, to keep feedback fast).
4. Package: build the deployable artifact/image once; promote that exact
   artifact through environments — never rebuild per environment.
5. Deploy: to the target runtime (see [[playbook.infrastructure]] for
   provisioning); require an approval gate before production for anything
   that isn't already trunk-based-and-flag-gated.
6. Verify: smoke test / health check after deploy, before marking the
   deploy complete.

## Must do — rollback and observability
- Every deploy strategy states its rollback path before it ships (previous
  artifact redeploy, Helm rollback, feature flag kill switch) — a deploy
  without a stated rollback path is not deploy-ready.
- Wire minimum observability before declaring a pipeline done: structured
  logs, a health/readiness endpoint, and at least one alert on deploy
  failure or post-deploy error-rate spike.

## Must avoid
- Do not build a new CI/CD system when the org already has a working one
  for the same purpose — extend it.
- Do not deploy straight to production without passing through the same
  pipeline stages lower environments used — no manual out-of-band deploys.
- Do not treat Spinnaker/canary/blue-green as default; they are for
  demonstrated progressive-delivery or multi-cluster needs.

## Escalation triggers
- A required pipeline capability implies new infrastructure (new cluster,
  new registry, new secret store) -> hand provisioning to Infrastructure
  Agent, don't provision inline.
- A pipeline change touches how secrets are stored/injected -> route
  through [[playbook.security]] first.

## Related concepts
- [[architecture.strangler-fig]]
- [[distributed.idempotency]] (deploy retries must be safe)
