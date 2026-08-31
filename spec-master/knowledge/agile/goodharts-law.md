---
id: agile.goodharts-law
type: Principle
name: Goodhart's Law
category: agile
applicable_roles:
  - scrum-master
  - product-owner
tags:
  - agile
  - laws
depth:
  scrum-master: L3
---

# Goodhart's Law

## Definition
When a measure becomes a target, it ceases to be a good measure. Velocity, coverage% misuse examples.

## Problem it addresses
Once a metric is chosen as an explicit target, people optimize for the metric itself rather than for the underlying outcome it was meant to represent — and the metric quietly stops meaning what it used to mean.

## Core principles
- 'When a measure becomes a target, it ceases to be a good measure' (Charles Goodhart, more famously paraphrased by Marilyn Strathern).
- Any metric used as an explicit target invites gaming, consciously or not, because people respond to the incentive the metric creates rather than the outcome it was meant to proxy for.
- The fix is not to abandon metrics, but to track multiple, harder-to-game indicators together, and to treat a metric as a signal to investigate rather than a target to hit at all costs.

## Appropriate use
Use Goodhart's Law as a check whenever a single number becomes a team's explicit target — ask what behavior that target incentivizes, and whether gaming it would actually look different from genuinely improving.

## Inappropriate use
Don't stop measuring anything just because measures can be gamed — the fix is choosing harder-to-game, outcome-linked measures (and multiple of them), not abandoning measurement altogether.

## Trade-offs
Tracking a single simple metric is easy to communicate and act on, but is the most exploitable; tracking several complementary metrics is harder to game but harder to communicate and requires more judgment to interpret.

## Typical violations
Setting 'code coverage percentage' as a hard target, which predictably produces tests that execute lines without asserting anything meaningful, inflating the number while quality stays flat or worsens.

## Anti-patterns
'Velocity' used as a cross-team comparison or a target to maximize (rather than a team-internal planning input) is a textbook Goodhart's Law failure — teams inflate story point estimates to hit a number that stops meaning anything once it's a target.

## Related concepts
- [[agile.little-law]]
