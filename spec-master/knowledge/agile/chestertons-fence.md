---
id: agile.chestertons-fence
type: Principle
name: Chesterton's Fence
category: agile
applicable_roles:
  - tech-lead
  - backend-dev
tags:
  - agile
  - laws
depth:
  tech-lead: L3
---

# Chesterton's Fence

## Definition
Don't remove something without understanding why it was put there. Application to code: understand before deleting.

## Problem it addresses
Code, process, or a design decision that looks unnecessary or wrong is often removed or 'fixed' without first understanding why it was put there — and it turns out to have been protecting against a real problem that then recurs.

## Core principles
- 'Do not remove a fence until you know why it was put up' (paraphrasing G.K. Chesterton's original reform parable).
- Before deleting seemingly-dead code, a strange conditional, or an odd config value, find out why it exists — check git blame, commit messages, related tests, or ask the team — rather than assuming it's simply a mistake.
- This is not an argument against ever removing anything — once the reason is understood, removing something whose reason no longer applies is exactly right; the rule is against removing *before* understanding.

## Appropriate use
Apply this before deleting or changing any code, config, or process that looks unnecessary but isn't obviously dead — investigate its origin first (blame, tests, related tickets) rather than assuming it's safe to remove.

## Inappropriate use
Don't use Chesterton's Fence as an excuse to never remove or question anything — once the original reason is understood and confirmed to no longer apply, removal is the correct outcome, not indefinite preservation out of caution.

## Trade-offs
Investigating the 'why' before removing something costs time upfront (git archaeology, asking around) in exchange for avoiding the specific, recurring failure of removing something protective and reintroducing a bug that was already solved once.

## Typical violations
Deleting a seemingly redundant null check or retry loop during a cleanup pass, only for the exact bug it was silently preventing to resurface in production weeks later.

## Anti-patterns
Removing code purely because it 'looks unnecessary' without checking its history is a common, quiet source of regressions — closely related to the Boy Scout Rule's own boundary (clean up only what you understand, not what merely looks messy).

## Related concepts
- [[principle.boy-scout-rule]]
