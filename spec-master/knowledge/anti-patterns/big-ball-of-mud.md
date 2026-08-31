---
id: antipattern.big-ball-of-mud
type: AntiPattern
name: Big Ball of Mud
category: anti-patterns
applicable_roles:
  - architect
  - tech-lead
tags:
  - anti-pattern
  - architecture
depth:
  architect: L4
---

# Big Ball of Mud

## Definition
No discernible architecture, everything depends on everything.

## Problem it addresses
Without deliberate architectural boundaries, every convenient shortcut compounds — 'just import this from over there', 'just add a field to this shared object' — until no part of the system can be understood, tested, or changed without understanding the whole thing.

## Core principles
- No discernible architecture: modules, layers, and features are all tangled together with no clear boundary anyone respects.
- Everything effectively depends on everything else, so a 'small' change anywhere carries an unpredictable risk of breaking something unrelated elsewhere.
- It is usually not the result of one bad decision, but the accumulation of many individually reasonable shortcuts taken without a structural boundary (Separation of Concerns, module boundaries) to contain them.

## Appropriate use
This is a diagnosis, not a technique to apply — recognize the symptoms (universal coupling, no respected boundaries) early, and use them as the signal to introduce (or re-enforce) [[principle.separation-of-concerns]] and [[principle.coupling-cohesion]] before the tangle grows further.

## Inappropriate use
Not applicable — there is no scenario where deliberately allowing a Big Ball of Mud is the right call. The relevant judgment call is how aggressively to invest in untangling an existing one versus containing further growth of the mess incrementally.

## Trade-offs
Untangling an existing Big Ball of Mud costs significant, risky refactoring effort with no new user-facing feature to show for it, which is precisely why it's hard to get budgeted — but the ongoing cost of leaving it in place is a permanently rising cost-per-change until the system becomes effectively unmaintainable.

## Typical violations
Modules that reach directly into each other's internals instead of a defined interface, and files that grow because 'the code that needs this data is easiest to add right here'.

## Anti-patterns
The terminal state that ignoring [[principle.solid]], [[principle.coupling-cohesion]], and [[principle.separation-of-concerns]] over a long enough period converges toward.

## Related concepts
- [[principle.coupling-cohesion]]
- [[principle.separation-of-concerns]]
