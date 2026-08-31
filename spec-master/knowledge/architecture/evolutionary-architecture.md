---
id: architecture.evolutionary
type: Principle
name: Evolutionary Architecture
category: architecture
applicable_roles:
  - architect
  - tech-lead
tags:
  - architecture
  - practices
depth:
  architect: L4
  tech-lead: L3
---

# Evolutionary Architecture

## Definition
An architecture designed to support guided, incremental change across multiple dimensions (technical, data, security) as requirements evolve, rather than being treated as a fixed decision made once at project start.

## Problem it addresses
Architectures designed as a one-time, fixed decision become obstacles the moment real requirements diverge from the original assumptions — and by the time that divergence is obvious, the cost of changing course has grown far beyond what it would have been to build in adaptability from the start.

## Core principles
- **Fitness functions**: objective, ideally automated checks (architectural tests) that verify the architecture still satisfies its important characteristics (e.g. a dependency-direction check, a performance budget test) as the codebase changes — catching architectural drift the same way unit tests catch behavioral regressions.
- Incremental change: the architecture should support small, low-risk changes over time rather than requiring a large, risky migration whenever a real requirement shifts.
- Multiple architectural dimensions evolve at different rates (technical structure, data schema, security posture) and each may need its own fitness functions and change cadence.

## Appropriate use
Invest in evolutionary architecture practices (fitness functions, incremental migration paths) for long-lived systems expected to face significant, hard-to-predict requirement changes over their lifetime.

## Inappropriate use
Skip building fitness-function tooling for a short-lived prototype or a system with genuinely stable, well-understood requirements — the investment pays off specifically where change is expected and costly to discover late.

## Trade-offs
Building and maintaining fitness functions costs real engineering investment (writing architectural tests, defining what 'still fits' means quantitatively) in exchange for catching architectural drift automatically instead of discovering it during a costly, late migration.

## Typical violations
An architecture decision record capturing a boundary or constraint with no corresponding automated check, so the constraint quietly erodes over time with no one noticing until a major refactor is needed.

## Anti-patterns
Big Design Up Front, treated as permanent rather than as a starting point expected to evolve, is the mindset Evolutionary Architecture pushes back against.

## Related concepts
- [[architecture.adr]]
- [[principle.evolutionary-design]]
- [[architecture.quality-attributes]]
