---
id: principle.defensive-programming
type: Principle
name: Defensive Programming
category: foundations
applicable_roles:
  - backend-dev
  - tech-lead
  - qa
tags:
  - practices
  - resilience
depth:
  tech-lead: L3
  backend-dev: L2
---

# Defensive Programming

## Definition
Writing code that anticipates and gracefully tolerates unexpected or invalid input/state at the boundaries it controls — sanitizing, validating, and providing sane fallbacks rather than trusting callers or external systems.

## Problem it addresses
Code that blindly trusts its inputs (a function's arguments, a parsed external payload, a config value) breaks in confusing ways when that trust is violated, especially when the violation comes from an external, less controlled source (user input, a third-party API response).

## Core principles
- Validate and sanitize input at boundaries you don't control — user input, external API responses, file parsing — since you can't guarantee that data's shape or safety.
- Provide sensible fallbacks or clear rejection for invalid input, rather than propagating it silently.
- Defensive programming's scope is deliberately bounded to genuine boundaries (external, untrusted sources) — applied to internal, controlled code paths instead of Fail Fast, it tends to just hide bugs instead of tolerating real uncertainty.

## Appropriate use
Apply defensive checks at real trust boundaries: parsing user input, handling third-party API responses, reading untrusted files or config — anywhere the caller/source is outside your control.

## Inappropriate use
Don't defensively guard against invalid state that indicates an internal bug (a private method called with an argument only your own code can pass) — that's exactly where Fail Fast, not defensive tolerance, is the right response.

## Trade-offs
Defensive checks add code and can mask real bugs if applied indiscriminately (swallowing an error that should have crashed loudly), in exchange for graceful handling of the genuinely unpredictable, external inputs a system must tolerate.

## Typical violations
Wrapping internal function calls in broad try/except blocks that silently continue on any failure, hiding bugs that should have failed fast and been caught during development.

## Anti-patterns
Over-applied defensive programming — catching and swallowing every possible exception 'just in case', including ones that indicate real internal bugs — is sometimes called 'pokemon exception handling' and directly undermines Fail Fast where Fail Fast should apply instead.

## Related concepts
- [[principle.fail-fast]]
