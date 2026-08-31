---
id: antipattern.god-object
type: AntiPattern
name: God Object
category: anti-patterns
applicable_roles:
  - tech-lead
  - backend-dev
tags:
  - anti-pattern
  - design
depth:
  tech-lead: L3
---

# God Object

## Definition
One class knows/does too much, violates SRP.

## Problem it addresses
As a class accumulates 'just one more responsibility' over time, it becomes the class every feature touches, every developer is afraid to change, and every unrelated bug fix risks breaking — a single point of both coupling and cognitive overload.

## Core principles
- One class knows about or does far too much — often a central `Manager`, `Utils`, or `Service` class that every other part of the codebase depends on.
- Directly violates Single Responsibility (see [[principle.solid]]): a God Object has many, unrelated reasons to change, so unrelated changes constantly collide in the same file.
- Tends to grow through the path of least resistance — adding 'just one more method' to an existing familiar class is easier in the moment than creating a new, properly-scoped one, and this incremental convenience is exactly how the pattern forms.

## Appropriate use
Not applicable as a technique — recognize a growing God Object as the signal to extract responsibilities into focused, single-purpose classes before it becomes the bottleneck every change has to go through.

## Inappropriate use
Not applicable — there is no case where deliberately concentrating unrelated responsibility into one class is the right call; the judgment is only in how aggressively and how soon to split an emerging one.

## Trade-offs
Splitting an established God Object costs a real refactor (extracting responsibilities, updating every caller) with real regression risk if not backed by tests, versus the compounding cost of leaving it: every unrelated feature continuing to collide in the same file.

## Typical violations
A `UserManager` class that ends up handling authentication, email sending, billing, and audit logging, because each felt like a small addition to an already-central class at the time.

## Anti-patterns
This entry is itself the concrete failure mode of ignoring [[principle.solid]]'s Single Responsibility principle and [[principle.coupling-cohesion]]'s cohesion guidance.

## Related concepts
- [[principle.solid]]
- [[principle.coupling-cohesion]]
