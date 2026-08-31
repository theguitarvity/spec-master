---
id: principle.technical-debt
type: Principle
name: Technical Debt
category: foundations
applicable_roles:
  - architect
  - tech-lead
  - product-owner
tags:
  - agile
  - management
depth:
  architect: L3
  tech-lead: L3
---

# Technical Debt

## Definition
Deliberate vs. accidental debt, debt quadrant, interest metaphor.

## Problem it addresses
Every codebase accumulates shortcuts, and untracked shortcuts compound: what would have cost an hour to do right today costs a week once three more features are built on top of the shortcut.

## Core principles
- Ward Cunningham's debt metaphor: a shortcut is a loan — it buys speed now and charges 'interest' (extra effort on every future change) until repaid (refactored).
- Martin Fowler's Technical Debt Quadrant separates debt along two axes: deliberate vs. inadvertent, and reckless vs. prudent. Prudent-deliberate debt ('we know the right design, but we need to ship first') is a legitimate trade-off; reckless-inadvertent debt ('what's layering?') is not.
- Debt is only a problem when it isn't tracked and isn't paid down — undocumented debt is what turns into a Big Ball of Mud.

## Appropriate use
Take on debt deliberately and visibly — e.g. a documented shortcut to hit a launch date, with a follow-up ticket — when the interest rate (cost of the shortcut compounding) is acceptable relative to the value of shipping now.

## Inappropriate use
Do not use 'technical debt' as an excuse to skip the constitution's non-negotiable requirements (security, correctness) — those aren't debt, they're defects. Also avoid taking on debt silently, with no record of what was skipped or why.

## Trade-offs
Debt trades short-term velocity for long-term maintenance cost; the trade is worth it only when the short-term win is real (a genuine deadline, a genuine learning opportunity) and there's a credible plan to repay it before the interest compounds past what the team can absorb.

## Typical violations
Shipping a hardcoded value 'temporarily' with no tracking ticket, which six months later three other features depend on, making the eventual fix far more expensive than the original shortcut.

## Anti-patterns
Big Ball of Mud is what unmanaged technical debt becomes at scale; 'debt' used as a blanket excuse for skipping tests or design review is a misuse of the term, not a genuine trade-off.

## Related concepts
- [[principle.evolutionary-design]]
- [[principle.boy-scout-rule]]
