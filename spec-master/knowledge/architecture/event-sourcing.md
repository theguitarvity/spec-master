---
id: architecture.event-sourcing
type: Pattern
name: Event Sourcing
category: architecture
applicable_roles:
  - architect
  - tech-lead
tags:
  - architecture
  - events
depth:
  architect: L4
---

# Event Sourcing

## Definition
Event log as source of truth, projections, snapshotting. Complexity cost: temporal queries vs. operational burden.

## Problem it addresses
Storing only current state discards the history of how that state was reached — no audit trail, no way to answer 'what did this look like last Tuesday', and no way to replay history to rebuild a new projection after a bug.

## Core principles
- The event log — an append-only, immutable sequence of domain events — is the source of truth, not a derived current-state table.
- Current state is a **projection**: replay the event log (or a snapshot plus the events since) to reconstruct it.
- **Snapshotting** periodically caches a projection's state so replay doesn't have to start from event zero for long-lived aggregates.

## Appropriate use
Use event sourcing where a full audit trail, temporal queries ('what was the state at time T'), or the ability to rebuild new read models from history is a real business requirement — financial ledgers, order lifecycles with compliance needs.

## Inappropriate use
Avoid it for simple entities with no audit or replay requirement — the operational burden (event schema evolution, snapshotting infrastructure, projection rebuilds) is not worth paying for a plain settings table.

## Trade-offs
A complete, replayable history and easy new-projection creation, at the cost of a genuinely harder operational model: event schema versioning/migration, eventual consistency of projections, and a steeper learning curve for the team.

## Typical violations
Modeling events as 'field X changed to value Y' (a mutation log) instead of meaningful domain facts ('OrderShipped'), which loses the intent the event sourcing model is meant to preserve.

## Anti-patterns
Cargo Cult CQRS+ES — reaching for event sourcing because it's fashionable rather than because the domain has a genuine audit/replay/temporal requirement.

## Related concepts
- [[architecture.cqrs]]
- [[principle.immutability]]
