---
id: distributed.clock-skew
type: Principle
name: Clock Skew
category: distributed-systems
applicable_roles:
  - architect
tags:
  - distributed
  - theory
depth:
  architect: L3
---

# Clock Skew

## Definition
Wall clock unreliability, Lamport clocks, vector clocks.

## Problem it addresses
Wall-clock time on different machines in a distributed system is never perfectly synchronized — using timestamps to determine event order across nodes can silently produce the wrong order, especially under clock drift or NTP correction jumps.

## Core principles
- Physical clocks drift and are only approximately synchronized (even NTP-synced clocks can differ by tens of milliseconds or more, and step corrections can even move a clock backward).
- **Lamport clocks**: a simple logical counter that captures causal 'happened-before' ordering between events without relying on wall-clock time at all.
- **Vector clocks**: extend Lamport clocks to detect concurrent (not causally related) events, not just order causally related ones — used to detect and resolve conflicting concurrent writes in leaderless replication.

## Appropriate use
Use logical clocks (Lamport/vector) instead of wall-clock timestamps whenever correctness depends on the true causal order of distributed events — conflict detection in a leaderless data store, distributed debugging/tracing causality.

## Inappropriate use
Don't use wall-clock timestamps to break ties or order events across nodes when correctness matters — timestamps are fine for human-readable logging/display, but not as a source of truth for ordering.

## Trade-offs
Logical clocks add a small amount of bookkeeping (a counter or vector to propagate with messages) in exchange for correctness guarantees that wall-clock time cannot provide across independent machines.

## Typical violations
Using `if timestampA > timestampB` to decide which of two concurrent writes 'wins' in a distributed store, which can pick the wrong writer whenever clock skew exceeds the real time gap between the writes.

## Anti-patterns
'Last write wins by wall-clock timestamp' is a widely used but fragile conflict-resolution strategy — a case where the simple, obvious approach is a known anti-pattern in the presence of clock skew.

## Related concepts
- [[distributed.consensus]]
