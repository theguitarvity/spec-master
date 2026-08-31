---
id: design.value-object
type: Pattern
name: Value Object
category: design
applicable_roles:
  - architect
  - tech-lead
  - backend-dev
tags:
  - design
  - ddd
depth:
  architect: L3
---

# Value Object

## Definition
Equality by value, immutable, no identity. Money, Address, Email as examples.

## Problem it addresses
Treating conceptually value-like data (an amount of money, an address, a date range) as a bag of primitives (a float and a currency string, three separate address fields) scatters validation and comparison logic across every place that touches them, and allows two logically-different things to be silently compared or swapped.

## Core principles
- A value object is defined entirely by its attributes, not by an identity — two value objects with the same attributes are equal, unlike entities which are equal only by identity even if their attributes match.
- Value objects are immutable — 'changing' one produces a new instance rather than mutating in place, which makes them safe to share freely.
- Classic examples: `Money` (amount + currency, with arithmetic that enforces matching currencies), `Address`, `Email`, `DateRange` — each bundles its own validation and behavior instead of leaving that scattered across callers.

## Appropriate use
Model any concept whose identity is entirely its value — quantities with units, ranges, identifiers with their own validation rules — as a value object rather than passing primitives around.

## Inappropriate use
Don't wrap every primitive in a value object reflexively when the concept genuinely has no invariant or behavior worth encapsulating — a raw `bool` doesn't need a value-object wrapper just for the sake of it.

## Trade-offs
Value objects add classes/types and construction/validation overhead at every entry point, in exchange for eliminating an entire class of bugs where invalid or mismatched primitive data (e.g. adding USD cents to EUR cents) passes silently through the system.

## Typical violations
Passing a raw `float` for money amounts across the codebase, allowing accidental unit mismatches (cents vs. dollars) or currency mismatches to compile and run without any error.

## Anti-patterns
Primitive Obsession — modeling everything as raw strings, numbers, and booleans instead of small, purpose-built value objects — is the specific anti-pattern value objects are the standard remedy for.

## Related concepts
- [[design.ddd]]
- [[principle.immutability]]
