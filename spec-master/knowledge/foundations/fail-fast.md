---
id: principle.fail-fast
type: Principle
name: Fail Fast
category: foundations
applicable_roles:
  - architect
  - tech-lead
  - backend-dev
  - qa
tags:
  - design
  - resilience
depth:
  architect: L3
  tech-lead: L3
---

# Fail Fast

## Definition
Validate early, crash loudly, defensive programming vs fail-fast.

## Problem it addresses
A system that swallows an invalid state and keeps running silently corrupts data or produces wrong output far from where the actual problem occurred, turning a five-minute fix into a multi-hour investigation.

## Core principles
- Validate inputs and invariants as early as possible — at the boundary, not deep inside business logic.
- Prefer a loud, immediate crash (exception, assertion) over silently continuing with bad state.
- Fail-fast is distinct from defensive programming: defensive programming tries to *tolerate* bad input gracefully (fallbacks, sanitization); fail-fast deliberately refuses to tolerate it, on the theory that hiding the error is more expensive than surfacing it immediately.

## Appropriate use
Use fail-fast at system boundaries and for invariants whose violation indicates a bug or corrupted state — e.g. a required config value missing at startup should crash immediately, not default to `None` silently.

## Inappropriate use
Do not fail-fast on expected, recoverable conditions a caller can reasonably handle (e.g. a user submitting an invalid form) — that calls for validation and a clear error response, not a crash. Reserve hard failure for truly unexpected states.

## Trade-offs
Failing fast surfaces bugs immediately and close to their cause, at the cost of being less tolerant of malformed input in the moment — a poorly chosen fail-fast check can turn a minor, recoverable hiccup into a full outage if applied where graceful degradation was actually appropriate.

## Typical violations
Catching a broad exception and logging-then-continuing in a code path where the caught error actually indicates corrupted state, letting bad data propagate downstream instead of stopping it at the source.

## Anti-patterns
Defensive programming taken to an extreme — swallowing all exceptions 'just in case' — is the anti-pattern fail-fast pushes back against; error hiding of this kind is sometimes called the 'pokemon exception handling' anti-pattern (gotta catch 'em all).

## Related concepts
- [[principle.solid]]
- [[principle.defensive-programming]]
