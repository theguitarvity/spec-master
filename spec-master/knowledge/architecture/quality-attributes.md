---
id: architecture.quality-attributes
type: Principle
name: Quality Attributes
category: architecture
applicable_roles:
  - architect
  - tech-lead
  - spec-master
tags:
  - architecture
  - requirements
depth:
  architect: L4
---

# Quality Attributes

## Definition
Performance, Reliability, Scalability, Maintainability, Security, Observability, Testability. Tension between attributes (CAP is one example).

## Problem it addresses
Requirements documents describe what the system should do (functional requirements) far more often than how well it should do it — and 'how well' (performance, reliability, security) is what actually determines architecture, not the feature list.

## Core principles
- Also called non-functional requirements or -ilities: Performance, Reliability, Scalability, Maintainability, Security, Observability, Testability, among others.
- Quality attributes are in tension with each other, not free to maximize simultaneously — CAP theorem is one concrete instance of this general tension (consistency vs. availability under partition).
- Architecture decisions should be traceable to specific quality attribute requirements, not made in the abstract — 'we need microservices' is not a requirement, 'we need independent deployability per team' is.

## Appropriate use
Make quality attributes explicit and prioritized early in a project — during constitution/architecture definition — so trade-off decisions (e.g. consistency vs. availability) have a stated rationale to be measured against.

## Inappropriate use
Don't treat every quality attribute as equally critical by default — an internal admin tool rarely needs the same availability target as a payments API; unstated priorities lead to over-engineering the wrong dimension.

## Trade-offs
Explicitly prioritizing quality attributes forces uncomfortable but necessary trade-off conversations early (what are we willing to sacrifice, and for what) rather than discovering the trade-off implicitly, and badly, during an incident.

## Typical violations
Designing a system without ever stating its scalability or availability targets, then being surprised when an architecture optimized for one unstated priority fails a different, actually-important one.

## Anti-patterns
Premature Optimization — over-investing in a quality attribute (usually performance) that was never actually a stated priority, at the expense of ones that were.

## Related concepts
- [[distributed.cap]]
