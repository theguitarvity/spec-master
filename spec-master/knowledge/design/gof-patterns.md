---
id: design.gof-patterns
type: Pattern
name: Object-Oriented Design Patterns (GoF)
category: design
applicable_roles:
  - architect
  - tech-lead
  - backend-dev
  - frontend-dev
  - fullstack-dev
tags:
  - design-patterns
  - gof
  - clean-code
depth:
  architect: L4
  tech-lead: L3
  backend-dev: L3
  frontend-dev: L2
  fullstack-dev: L2
---

# Object-Oriented Design Patterns (GoF)

## Definition
Reusable solutions to recurring object-design problems, grouped as
Creational (object construction), Structural (object composition), and
Behavioral (object collaboration/communication).

## Problem it addresses
Without named patterns, agents reinvent ad-hoc solutions to problems that
already have a well-understood shape, or apply a pattern the codebase
doesn't actually need because it "sounds enterprise." This module gives a
detection heuristic: match the *symptom* in the code to the pattern that
resolves it, not the other way around.

## Detection heuristic — symptom to pattern
- **Object needs to vary construction logic by context, or construction is
  multi-step/expensive** -> Factory Method / Abstract Factory (family of
  related objects) or Builder (many optional constructor params).
- **Only one instance should exist and it's genuinely global (config,
  connection pool)** -> Singleton. Prefer DI-container-scoped instances over
  a hand-rolled Singleton; a hand-rolled one blocks testability.
- **An existing class's interface doesn't match what a caller needs, and you
  can't change the existing class** -> Adapter.
- **A class hierarchy explodes because two independent dimensions vary
  together (e.g. `SqlUserRepo`, `MongoUserRepo`, `CachedSqlUserRepo`...)**
  -> Bridge (separate abstraction from implementation).
- **You need to add behavior to individual objects without subclassing
  every combination** -> Decorator.
- **A subsystem has many moving parts and callers keep reaching into all of
  them** -> Facade.
- **Behavior must change based on internal state, and you see a large
  `switch`/`if-else` on a `status`/`state` field repeated across methods**
  -> State.
- **An algorithm has interchangeable variants selected at runtime, and you
  see a `switch` on a `type`/`strategy` field to pick behavior** -> Strategy.
- **Multiple objects must react when one object changes, and you see manual
  polling or tightly coupled callback lists** -> Observer (domain events —
  see [[design.domain-event]] — are the DDD-flavored version of this).
- **A request must pass through a chain of independent handlers, each of
  which may fully handle it or pass it on** -> Chain of Responsibility
  (middleware pipelines, validation pipelines).
- **You need to build a complex object step-by-step, and constructor
  overloads are multiplying** -> Builder.
- **You need to encapsulate a request as an object (undo/redo, queued
  work, retryable jobs)** -> Command.
- **You need to traverse a composite/tree structure uniformly (files and
  folders, UI component trees, org charts)** -> Composite.
- **An operation must apply across a class hierarchy without polluting the
  hierarchy itself, and it changes more often than the hierarchy does**
  -> Visitor. Use sparingly — it's the highest-ceremony pattern here.

## Appropriate use
Apply a pattern only after the symptom is visible in the actual code (a
repeated conditional, a combinatorial class explosion, duplicated
construction logic) — never speculatively. One additional concrete variant
does not justify a pattern; a third variant with a fourth already planned
usually does (see [[principle.yagni]]).

## Inappropriate use
Do not introduce a pattern to look sophisticated, to satisfy a checklist,
or to abstract a single implementation "in case it changes." That is
Cargo Cult, see [[antipattern.cargo-cult]]. Visitor and Abstract Factory in
particular are frequently over-applied to problems Strategy or a plain
function would solve with less ceremony.

## Trade-offs
Every pattern trades directness for flexibility: more types, more
indirection, a steeper on-ramp for a new reader. The right call favors the
smallest structure that removes the actual duplication or actual variation
point in front of you.

## Escalation
When a backend/frontend/fullstack dev agent spots a structural symptom
above but the fix would cross package boundaries or change a shared
contract, do not apply the pattern unilaterally — flag it to the architect
or tech-lead with the symptom (file/class, the repeated conditional or
duplicated construction) and the candidate pattern, and let them decide
scope.

## Related concepts
- [[principle.solid]]
- [[principle.dry]]
- [[principle.kiss]]
- [[principle.yagni]]
- [[antipattern.cargo-cult]]
- [[antipattern.god-object]]
