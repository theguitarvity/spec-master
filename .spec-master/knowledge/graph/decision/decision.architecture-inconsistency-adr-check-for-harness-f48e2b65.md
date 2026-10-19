---
id: decision.architecture-inconsistency-adr-check-for-harness-f48e2b65
type: Decision
name: ADR check for harness-hygiene (tier L)
status: active
source: EXPLICIT
confidence: 1.0
tags:
  - decision
  - kind:architecture_inconsistency
  - decided-by:architect
  - raised-by:tech-lead
  - involves:architect
  - involves:tech-lead
  - involves:scrum-master
  - feature:harness-hygiene
first_seen: {"phase": "escalation", "at": "2026-10-19T11:25:13Z"}
last_verified: {"at": "2026-10-19T11:25:13Z"}
---

## Decision

No ADR required: no new provider, data model, trust boundary or public contract shape change

## Context

- Kind: `architecture_inconsistency`
- Raised by: `tech-lead`
- Decided by: `architect`
- Feature: `harness-hygiene`
- Escalation chain: architect → scrum-master
- Recorded at: 2026-10-19T11:25:13Z

## Rationale

Pre-implement sensitivity hits (public_contract from 'endpoints'/'contracts', external_provider from 'third-party') are keyword false positives in tasks.md; changes are internal stdlib helpers, an additive CLI flag and a documented work-package default

## Alternatives considered

- Write an ADR for the H5 depends_on default change (rejected: documented in spec Clarifications/PROTOCOL; no architectural boundary moves)