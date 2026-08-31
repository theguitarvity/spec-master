---
id: architecture.adr
type: Principle
name: Architecture Decision Records
category: architecture
applicable_roles:
  - architect
  - tech-lead
  - spec-master
tags:
  - documentation
  - architecture
depth:
  architect: L4
  tech-lead: L3
---

# Architecture Decision Records

## Definition
Context, Decision, Consequences format. Why ADRs matter: captures reasoning, not just outcome.

## Problem it addresses
Architectural decisions get made in a meeting or a chat thread and the reasoning is lost within months — a new team member sees an odd design choice with no record of why it was made, and either reverses it blindly or fears touching it.

## Core principles
- A short, numbered document per significant decision, capturing **Context** (the forces at play), **Decision** (what was chosen), and **Consequences** (the resulting trade-offs, including negative ones).
- ADRs are immutable once accepted — a later decision that changes course is a new ADR that supersedes the old one, not an edit to history.
- What matters most is capturing the *reasoning*, not just the outcome — the decision itself is often visible in the code; the 'why' is what disappears without a record.

## Appropriate use
Write an ADR for decisions that are expensive to reverse or that future readers will likely question — choice of database, service boundary, a rejected alternative approach with a non-obvious reason.

## Inappropriate use
Don't write an ADR for routine, easily-reversible implementation choices (variable naming conventions, a single function's internal algorithm) — that's noise, not decision history worth preserving.

## Trade-offs
A few minutes of writing per significant decision, in exchange for a searchable record that prevents re-litigating settled decisions and helps new team members understand why the system looks the way it does.

## Typical violations
Recording only the decision ('we use Postgres') with no context or rejected alternatives, so a future reader can't tell whether MySQL was actually considered and rejected, or never considered at all.

## Anti-patterns
Tribal knowledge — architectural reasoning that exists only in the heads of the people who were in the room — is the failure mode ADRs exist to prevent.

## Related concepts
- [[architecture.evolutionary]]
