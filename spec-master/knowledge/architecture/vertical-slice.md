---
id: architecture.vertical-slice
type: Pattern
name: Vertical Slice Architecture
category: architecture
applicable_roles:
  - architect
  - tech-lead
tags:
  - architecture
depth:
  architect: L3
---

# Vertical Slice Architecture

## Definition
Feature-organized slices instead of horizontal layers. CQRS/MediatR in .NET, similar patterns in other stacks.

## Problem it addresses
Layered architecture forces every feature change to touch the same shared layers as every other feature, so features can't be added, understood, or removed independently — a small feature change requires navigating the entire codebase's layers.

## Core principles
- Organize code by feature/use-case slice, not by technical layer: each slice contains everything needed to handle one request end-to-end.
- Reduces coupling between unrelated features, since each slice owns its logic rather than sharing a layer with every other feature.
- Commonly implemented with a mediator/CQRS-style request handler per slice (e.g. MediatR in .NET), though the concept applies in any stack.

## Appropriate use
Use it when features evolve independently and shared horizontal layers create more coordination cost than benefit — especially in codebases with many features owned by different people or teams.

## Inappropriate use
Skip it when there's genuinely significant shared logic across features that would just be duplicated across slices — a shared layer earns its keep there.

## Trade-offs
Some duplication across slices (each slice may re-implement similar validation or mapping logic) in exchange for each feature being independently understandable, testable, and removable without touching a shared layer.

## Typical violations
Slices that quietly share a mutable service or repository with hidden cross-slice coupling, recreating layered architecture's coupling problems inside a folder structure that looks vertical.

## Anti-patterns
A 'vertical slice in name only' — folders per feature, but everything still routes through the same shared, tightly coupled service layer underneath — provides none of the pattern's actual isolation benefit.

## Related concepts
- [[architecture.layered]]
- [[architecture.cqrs]]
