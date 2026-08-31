---
id: agile.brooks-law
type: Principle
name: Brooks's Law
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

# Brooks's Law

## Definition
Adding people to a late project makes it later. Training cost, communication overhead n*(n-1)/2.

## Problem it addresses
When a project falls behind schedule, the instinctive response is to add more people — but Fred Brooks observed this frequently makes a late project later, not earlier, because the naive assumption (more people = proportionally more output) ignores the real cost of onboarding and coordination.

## Core principles
- 'Adding manpower to a late software project makes it later' (Fred Brooks, *The Mythical Man-Month*).
- New team members need ramp-up time from existing team members, which temporarily *reduces* the existing team's output before the new members become productive.
- Communication overhead grows combinatorially with team size — roughly n(n-1)/2 communication paths for n people — so a bigger team spends proportionally more time coordinating, not just building.

## Appropriate use
Consider Brooks's Law before adding people to a project that is already behind schedule and close to its deadline — it's a warning to weigh ramp-up and coordination cost against the apparent gain, not a blanket rule against ever growing a team.

## Inappropriate use
Don't cite Brooks's Law to block adding people to a project that has ample runway before its deadline — the law specifically concerns *late* projects near their deadline, where there's no time left to absorb the ramp-up cost.

## Trade-offs
Adding people brings more eventual capacity at the cost of a real short-term productivity dip while onboarding happens and communication paths multiply — the trade only pays off if there's enough runway left to recoup that dip.

## Typical violations
Doubling a team two weeks before a deadline in response to slipping progress, without accounting for the weeks of ramp-up and mentoring time that pulls the existing team away from actually finishing the work.

## Anti-patterns
Treating headcount as a simple, linear substitute for schedule ('we're a month behind, so add one more person per week of delay') ignores both onboarding cost and the combinatorial growth of coordination overhead.

## Related concepts
- [[agile.conways-law]]
