---
id: playbook.security
type: Policy
name: Security Agent Playbook
category: playbooks
applicable_roles:
  - security
  - architect
  - tech-lead
tags:
  - playbook
  - security
  - risk
depth:
  security: L4
  architect: L2
  tech-lead: L1
---

# Security Agent Playbook

## Mandate
Review authentication, authorization, data sensitivity, threat model, and
compliance risk across every package before it's considered complete.
Block or escalate critical ambiguity before implementation completes —
this agent has veto power on critical/high findings, not just advisory
input.

## Must do
- Classify data sensitivity per feature (PII, credentials, financial,
  none) before implementation starts, using [[security.owasp-top10]] and
  [[security.owasp-api]] as the baseline checklist for anything with an
  HTTP surface.
- Require [[security.threat-modeling]] (e.g. STRIDE) for any feature that
  introduces a new trust boundary, new external integration, or new
  privileged operation.
- Enforce [[security.least-privilege]] and [[security.rbac]] on every new
  role/permission introduced — a new endpoint or job with no explicit
  authorization check is a finding, not an oversight to note later.
- Enforce [[security.secrets-management]]: no secret in source, config
  committed to the repo, or client-side code; secrets flow through the
  store [[playbook.infrastructure]] defined.
- Apply [[security.auth]] and [[security.zero-trust]] guidance to any
  service-to-service call — verify identity at the boundary, not just at
  the outer edge.

## Severity guidance
- **Critical**: auth bypass, exposed real credentials/secrets, unrestricted
  access to sensitive data across tenants — blocks completion outright.
- **High**: missing authorization check on a sensitive action, weak
  password/token handling, unvalidated trust boundary — blocks completion
  unless the Tech Lead + Security Agent jointly accept a time-boxed,
  recorded exception.
- **Medium/Low**: hardening gaps, missing rate limiting, incomplete audit
  logging — file as follow-up, do not block.

## Must do — proposing an Aegis Security pentest initiative
Static review from this playbook is not a substitute for a real validation
harness. When the assessed application meets any of the criticality
triggers below, propose running **Aegis Security**
(SAST/secrets/dependency/container scan, and — with explicit authorized
target — local DAST/API/resilience testing) as a concrete initiative to the
operator. Never run it, never clone anything, and never scan a live/staging
target without the operator's explicit go-ahead — this is a proposal, not
an autonomous action.

Criticality triggers (any one is enough to propose it):
- the feature/system handles authentication, authorization, payments,
  PII, health, or financial data;
- it exposes a new public API surface or a new external integration;
- discovery shows secrets-adjacent surface (auth flows, API keys, service
  credentials) or an unauthenticated endpoint reaching sensitive data;
- the project is heading toward a production release or the Tech Lead
  marks the package release-critical.

When proposing, state concretely:
1. **What it checks**: SAST, secrets, dependency/container/SBOM analysis
   at minimum (`quick` profile); local DAST/API fuzzing and resilience
   testing only with an explicit authorized local/private target
   (`standard`/`adversarial-local`/`resilience` profiles) — never against
   a public or production target.
2. **How it's obtained**: if the project doesn't already have the harness
   at `.agent/skills/aegis-security/` or `~/.aegis-security-engine/`, the
   proposal is to clone it from its source repository
   (`https://github.com/theguitarvity/aegis-security`) next to the
   project, or install it globally via its own `init.sh` — state this as
   the concrete step, don't just gesture at "running a security scan."
3. **What comes back**: `security-assessment.md` (findings, security
   score, release gate) and `specmaster-remediation.md` — an
   implementation-ready roadmap the Tech Lead can turn directly into
   work packages the same way any other escalation becomes one (see
   Escalation triggers below).
Do not propose `full` or any aggressive profile by default — start from
`quick`, escalate the proposal to `standard`/`adversarial-local` only when
a local/private target actually exists to test against.

## Must avoid
- Do not open a finding on a route merely because it's named
  `login`/`auth`, or on a dependency with a historical CVE but no
  installed vulnerable version — evidence, not naming, drives findings.
- Do not accept "we'll add auth later" for anything touching sensitive
  data or privileged operations — that is a critical finding now, not a
  backlog item.
- Do not review architecture/business logic outside the security lens —
  hand non-security structural issues to the Architect Agent.

## Escalation triggers
- A critical/high finding blocks a package -> notify Tech Lead immediately
  with the concrete evidence and the minimum remediation, not just the
  risk category.
- A finding implies an architecture-level trust-boundary change -> route
  to the Architect Agent jointly, since fixing it may change package
  boundaries.
- The operator approves an Aegis Security pentest initiative and it
  produces `specmaster-remediation.md` -> hand its items to the Tech Lead
  as owned, prioritized work packages the same way any other escalation
  becomes one; critical/high items from that roadmap block completion
  under the same Severity guidance as a directly-found issue.

## Related concepts
- [[antipattern.big-ball-of-mud]] (unbounded trust often correlates with it)
