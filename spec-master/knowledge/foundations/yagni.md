---
id: principle.yagni
type: Principle
name: You Aren't Gonna Need It
category: foundations
applicable_roles:
  - architect
  - tech-lead
  - product-owner
tags:
  - agile
  - simplicity
depth:
  architect: L3
  tech-lead: L3
---

# You Aren't Gonna Need It

## Definition
Speculative generality anti-pattern, costs of premature abstraction.

## Problem it addresses
Engineers routinely build generality for future requirements that never materialize, paying real cost now for a hypothetical later that often turns out different from what was guessed. YAGNI is the reminder that speculative work is a bet, usually a losing one.

## Core principles
- Build the feature the current, confirmed requirement needs — not the one you imagine a future requirement might need.
- Speculative generality (unused strategy interfaces, config knobs with one real value, 'just in case' parameters) is a cost paid today against a benefit that may never arrive.
- YAGNI pairs with evolutionary design: it is safe to defer generalization because refactoring later, once the real second use case shows up, is cheaper than guessing wrong now.

## Appropriate use
Apply YAGNI whenever a requirement is speculative — 'we might need multi-tenancy someday', 'let's support three databases just in case'. Build for the one confirmed case and let a second real case drive the abstraction.

## Inappropriate use
YAGNI is not a license to skip work items already in the confirmed requirements or the constitution (e.g. skipping auth because 'maybe we won't need it') — it applies only to unrequested generality, not to shrinking scope.

## Trade-offs
Deferring generalization keeps current code smaller and cheaper to change, but the eventual generalization — once genuinely needed — costs a refactor that could have been avoided with better upfront guessing. YAGNI bets that this refactor is cheaper than paying for unused flexibility on every requirement that never shows up.

## Typical violations
A config system built to support five swappable backends when only one is used in production a year later, adding indirection every reader must pay for.

## Anti-patterns
Speculative Generality — the anti-pattern YAGNI exists specifically to counter — and Gold Plating, adding unrequested polish or capability beyond what was asked.

## Related concepts
- [[principle.kiss]]
- [[principle.evolutionary-design]]
