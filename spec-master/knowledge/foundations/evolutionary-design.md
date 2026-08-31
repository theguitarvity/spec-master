---
id: principle.evolutionary-design
type: Principle
name: Evolutionary Design
category: foundations
applicable_roles:
  - architect
  - tech-lead
tags:
  - design
  - agile
depth:
  architect: L4
  tech-lead: L3
---

# Evolutionary Design

## Definition
Refactoring safely, BDUF vs emergent design.

## Problem it addresses
Requirements are rarely fully known upfront. Designing the 'final' architecture before writing code (Big Design Up Front) locks in guesses that are frequently wrong, while refusing to design at all produces an unmaintainable mess.

## Core principles
- Let the design emerge through small, safe, continuous refactoring as real requirements become clear, rather than committing to a complete design before any code exists.
- Safety for evolutionary design comes from tests: refactoring without a test safety net is just as risky as BDUF, so the two practices (evolutionary design and strong test coverage) are inseparable in practice.
- This does not mean 'no upfront design' — it means keeping upfront design proportionate to actual certainty, and treating the design as a living artifact.

## Appropriate use
Favor evolutionary design when requirements are still being discovered (early-stage products, novel domains) and a solid automated test suite exists to make refactoring safe.

## Inappropriate use
Do not lean on evolutionary design as an excuse to skip architectural thinking on decisions that are expensive to reverse later (a database choice, a service boundary, a public API contract) — those still warrant deliberate upfront design.

## Trade-offs
Evolutionary design avoids over-investing in a guessed-wrong architecture, at the cost of accepting that the codebase will go through visible refactoring passes rather than being 'right' from day one — which requires organizational tolerance for that ongoing churn.

## Typical violations
Spending weeks designing a fully general plugin architecture before a single real plugin exists, based on requirements that turn out to be wrong once actual usage patterns emerge.

## Anti-patterns
Big Design Up Front (BDUF) is the anti-pattern evolutionary design responds to; the opposite failure — refactoring with no tests as a safety net — is sometimes called 'refactoring on a tightrope'.

## Related concepts
- [[principle.yagni]]
- [[principle.technical-debt]]
