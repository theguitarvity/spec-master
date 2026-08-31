---
id: design.domain-event
type: Pattern
name: Domain Event
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

# Domain Event

## Definition
Something significant that happened in the domain. Past tense naming, immutable.

## Problem it addresses
When something significant happens in the domain (an order is placed, a payment fails), other parts of the system that need to react to it often end up tightly coupled to the code that caused it, via direct method calls, instead of reacting to the fact that it happened.

## Core principles
- A domain event represents something significant that has already happened in the domain — named in the past tense (`OrderPlaced`, not `PlaceOrder`) to reflect that it's a fact, not a command.
- Domain events are immutable — once it happened, the record of it happening doesn't change.
- They decouple the part of the system that causes a change from the parts that need to react to it — the aggregate that raises `OrderPlaced` doesn't need to know who's listening or what they'll do.

## Appropriate use
Raise a domain event whenever another part of the system (in-process or in another service, via an outbox) needs to react to a state change without the originating code needing to know about or call that reaction directly.

## Inappropriate use
Don't model every field mutation as a domain event ('NameFieldChanged') — reserve events for changes that are meaningful in the domain's own vocabulary, not for incidental technical state changes.

## Trade-offs
Domain events add a layer of indirection (publish now, react later, possibly elsewhere) that costs some traceability effort but decouples producers from consumers and makes new reactions easy to add without touching the originating code.

## Typical violations
Naming an event in the imperative ('PlaceOrder') instead of the past tense, which conflates a command (an instruction to do something, which can be rejected) with an event (a fact that already happened, which cannot be undone).

## Anti-patterns
A domain event bus with events named as commands, or a growing 'god event' carrying every field anyone might ever need, defeats the purpose of small, meaningful, decoupled facts.

## Related concepts
- [[design.aggregate]]
- [[architecture.eda]]
