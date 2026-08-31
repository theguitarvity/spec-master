---
id: principle.dry
type: Principle
name: Don't Repeat Yourself
category: foundations
applicable_roles:
  - architect
  - tech-lead
  - backend-dev
  - frontend-dev
tags:
  - dry
  - simplicity
depth:
  architect: L3
  tech-lead: L3
  backend-dev: L2
---

# Don't Repeat Yourself

## Definition
Definition, WET anti-pattern, Rule of Three heuristic. Caveat: wrong abstraction can be worse than duplication.

## Problem it addresses
Duplicated logic means every future change to that logic must be found and applied in every copy — miss one, and behavior silently diverges. DRY targets that specific failure: knowledge, not text, that exists in more than one place.

## Core principles
- DRY is about **knowledge duplication** (a business rule, a piece of domain logic), not textual similarity — two blocks of code that look alike but express unrelated rules are not a DRY violation.
- The Rule of Three: tolerate one duplicate, watch the second, extract on the third occurrence — premature extraction after a single repeat often guesses the wrong abstraction.
- WET ('Write Everything Twice/We Enjoy Typing') is the failure mode of ignoring DRY entirely.

## Appropriate use
Extract shared logic when the same business rule or invariant is expressed in multiple places and is likely to change as a unit — validation rules, pricing formulas, auth checks.

## Inappropriate use
Do not merge two pieces of code just because they currently look similar if they represent unrelated concerns that happen to coincide today (e.g. two DTOs with the same three fields for different reasons). Forcing a shared abstraction over accidental similarity creates coupling between things that should be free to diverge.

## Trade-offs
Deduplication reduces edit surface but adds indirection and coupling between call sites — every caller of the shared abstraction now depends on it, so a change for one caller's sake can ripple into the others.

## Typical violations
The same discount calculation copy-pasted into three endpoint handlers, each drifting slightly out of sync after a few sprints, until a promo code applies correctly on the web checkout but not on mobile.

## Anti-patterns
The 'wrong abstraction' anti-pattern: forcing two subtly different pieces of logic behind one shared function via a growing pile of boolean flags and special-case branches, which is usually worse than the duplication it replaced. Sandi Metz's guidance applies: prefer duplication over the wrong abstraction.

## Related concepts
- [[principle.solid]]
- [[principle.kiss]]
