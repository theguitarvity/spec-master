---
id: agile.flow-metrics
type: Principle
name: Flow Metrics
category: agile
applicable_roles:
  - scrum-master
  - product-owner
  - spec-master
tags:
  - agile
  - metrics
depth:
  scrum-master: L4
  spec-master: L3
---

# Flow Metrics

## Definition
Lead time, Cycle time, Throughput, WIP. How to measure and improve flow.

## Problem it addresses
Teams that track only output (story points completed, velocity) have no visibility into how long individual work items actually take to get through the system, or where they get stuck — velocity can look fine while individual items silently take weeks longer than they should.

## Core principles
- **Lead time**: total elapsed time from when a work item is requested to when it's delivered.
- **Cycle time**: elapsed time from when work actually starts on an item to when it's finished — a subset of lead time, and usually the more actionable of the two since it excludes queue-waiting time before work begins.
- **Throughput**: number of items completed per unit time.
- **WIP**: number of items currently in progress — the lever connected to cycle time via [[agile.little-law]].
- Improving flow means finding where items sit idle (queued, blocked, waiting for review) rather than assuming slow delivery means people aren't working hard enough.

## Appropriate use
Track cycle time and WIP whenever a team wants to improve delivery predictability or speed — these metrics point directly at where work is waiting, which is usually the actual bottleneck, more often than active work being slow.

## Inappropriate use
Don't use flow metrics as an individual performance measure (e.g. ranking people by their items' cycle time) — that invites the exact gaming Goodhart's Law predicts and destroys the metric's value as a system-level diagnostic.

## Trade-offs
Measuring flow requires disciplined status tracking (accurately marking when work starts, gets blocked, and finishes) which costs process overhead, in exchange for visibility into where delivery time is actually being lost.

## Typical violations
Reporting velocity every sprint while cycle time silently doubles because more items are being started concurrently than the team can actually finish — velocity alone hides this.

## Anti-patterns
Optimizing for 'items started' or 'utilization' instead of flow (cycle time, throughput) is the same anti-pattern Little's Law warns against, applied at the metrics-reporting level.

## Related concepts
- [[agile.little-law]]
- [[agile.kanban]]
