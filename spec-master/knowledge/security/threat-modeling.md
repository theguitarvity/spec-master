---
id: security.threat-modeling
type: Principle
name: Threat Modeling
category: security
applicable_roles:
  - architect
  - security
  - spec-master
tags:
  - security
  - practices
depth:
  security: L4
  architect: L3
---

# Threat Modeling

## Definition
STRIDE model: Spoofing, Tampering, Repudiation, Information Disclosure, DoS, Elevation of Privilege.

## Problem it addresses
Security work applied reactively — patching whatever vulnerability was just found — misses the threats that were never considered in the first place, because no one asked 'what could go wrong here and who would want to make it go wrong' before the system was built.

## Core principles
- Threat modeling is the structured practice of identifying what could go wrong in a system, before or alongside building it, rather than discovering threats only via later incidents or audits.
- **STRIDE** is a common classification for threat categories: **S**poofing (impersonating something/someone), **T**ampering (modifying data/code without authorization), **R**epudiation (denying having performed an action, without an audit trail to disprove it), **I**nformation Disclosure (exposing data to unauthorized parties), **D**enial of Service, **E**levation of Privilege.
- Effective threat modeling asks, per component/data flow: what can go wrong here, under STRIDE, and what mitigates it — done at design time, it's far cheaper than fixing the same gap after an incident.

## Appropriate use
Run a threat modeling pass during design of any system component that handles authentication, sensitive data, payments, or an externally-reachable attack surface — ideally as part of the constitution/architecture phase, not bolted on after launch.

## Inappropriate use
Don't skip threat modeling for internal-only tools on the assumption that 'no external attacker can reach it' — insider threats, compromised internal credentials, and supply-chain risks (STRIDE's Elevation of Privilege, Tampering) still apply.

## Trade-offs
Threat modeling costs a dedicated design-review session and some documentation effort, in exchange for catching design-level security gaps (which are expensive to fix post-launch) at the point where they're cheapest to redesign around.

## Typical violations
Designing an audit log feature with no protection against a privileged user editing or deleting the log entries themselves — a Repudiation gap that only surfaces when someone actually needs to prove what happened after the fact.

## Anti-patterns
Purely reactive security ('we'll fix it when a pentest or an incident finds it') is the anti-pattern threat modeling exists to move away from, by finding the same classes of issue earlier and cheaper.

## Related concepts
- [[security.owasp-top10]]
- [[security.zero-trust]]
