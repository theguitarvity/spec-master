---
id: agile.conways-law
type: Principle
name: Conway's Law
category: agile
applicable_roles:
  - architect
  - product-owner
  - scrum-master
  - spec-master
tags:
  - agile
  - laws
depth:
  architect: L4
  scrum-master: L3
---

# Conway's Law

## Definition
Organizations design systems that mirror their communication structure. Inverse Conway Maneuver: design org around target architecture. Software consequence: team topology determines system topology.

## Problem it addresses
Teams design software boundaries as if they were a purely technical decision, then are surprised when the resulting architecture mirrors the org chart instead of the domain — two teams that don't talk to each other produce two systems with a mismatched interface between them, regardless of the intended design.

## Core principles
- 'Organizations which design systems are constrained to produce designs which are copies of the communication structures of these organizations' (Melvin Conway, 1967).
- **Inverse Conway Maneuver**: deliberately restructure teams to mirror the target architecture you want, since the architecture will end up mirroring team structure anyway — so design the org first if you want a specific system shape.
- Practical consequence: a service boundary that splits work across two teams with poor communication will tend to develop a poor, high-friction interface, independent of how well-designed the boundary looked on paper.

## Appropriate use
Use Conway's Law when deciding both team structure and service/module boundaries together — align them deliberately (Inverse Conway Maneuver) rather than treating org design and architecture design as unrelated decisions.

## Inappropriate use
Don't design an ambitious microservices boundary map without considering whether the team structure can actually sustain it — a boundary that splits ownership across teams with weak communication paths will degrade regardless of the diagram's elegance.

## Trade-offs
Deliberately aligning team structure to target architecture (or vice versa) costs an organizational change, which is often harder to make than a code change, in exchange for an architecture whose boundaries actually match how the org communicates.

## Typical violations
Splitting a service in two along a technical line (e.g. frontend/backend) that doesn't match any real team boundary, so both halves are maintained by the same team anyway and the split adds only overhead.

## Anti-patterns
A 'distributed monolith' often traces back to service boundaries drawn without regard to Conway's Law — teams split code without splitting communication structure, so services stay tightly coupled in practice despite being technically separate.

## Related concepts
- [[architecture.microservices]]
- [[design.bounded-context]]
