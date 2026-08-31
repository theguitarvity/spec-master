---
id: design.specification
type: Pattern
name: Specification Pattern
category: design
applicable_roles:
  - architect
  - tech-lead
  - backend-dev
tags:
  - design
  - patterns
depth:
  architect: L3
---

# Specification Pattern

## Definition
Business rule encapsulation, composable with AND/OR/NOT.

## Problem it addresses
Business rules used to select or validate entities (e.g. 'is this order eligible for expedited shipping') often get duplicated across a query, a validation check, and an in-memory filter, drifting out of sync as the rule evolves in one place but not the others.

## Core principles
- A specification encapsulates a single business rule as an object with an `isSatisfiedBy(candidate)` check, reusable wherever that rule needs to be applied — in a query, in validation, or in an in-memory filter.
- Specifications compose with `AND`, `OR`, `NOT`, letting complex eligibility rules be built from small, independently testable pieces instead of one large conditional.
- The same specification object can, in principle, drive both an in-memory filter and a query translation (e.g. to SQL), keeping the rule defined exactly once.

## Appropriate use
Use the specification pattern when a business rule is reused in more than one place (query filtering, validation, in-memory selection) and is complex or likely to change — it keeps the rule defined exactly once.

## Inappropriate use
Don't wrap a single, simple, one-off condition used in exactly one place in a full specification object — that's unnecessary ceremony for a rule with no reuse or composition need.

## Trade-offs
An extra layer of small objects to navigate, in exchange for eliminating rule duplication across query, validation, and in-memory filtering call sites.

## Typical violations
The same 'eligible for discount' logic implemented once as a SQL `WHERE` clause and again as an in-memory `if` check, which silently diverge after one of the two is updated for a new promotion.

## Anti-patterns
Duplicated business-rule logic across query and application layers is a specific instance of the general DRY violation the specification pattern is designed to prevent.

## Related concepts
- [[design.repository]]
- [[design.ddd]]
