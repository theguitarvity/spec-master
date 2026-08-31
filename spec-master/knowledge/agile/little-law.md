---
id: agile.little-law
type: Principle
name: Little's Law
category: agile
applicable_roles:
  - scrum-master
tags:
  - agile
  - laws
depth:
  scrum-master: L4
---

# Little's Law

## Definition
L = λW (inventory = throughput × cycle time). WIP limits derive from this.

## Problem it addresses
Teams intuitively add more work-in-progress to 'go faster', without realizing that more concurrent work items, given a fixed processing capacity, mechanically increases how long each item takes to finish — the math works against the intuition.

## Core principles
- **L = λW**: average number of items in a system (L) equals arrival rate (λ) times average time each item spends in the system (W) — a general queuing-theory law that applies directly to any workflow with a queue.
- Applied to software delivery: average work-in-progress (WIP) = throughput × average cycle time. Rearranged: cycle time = WIP / throughput.
- Consequence: for a fixed throughput, increasing WIP directly and proportionally increases cycle time — this is the mathematical justification for WIP limits in Kanban.

## Appropriate use
Use Little's Law to justify and calibrate WIP limits — if cycle time is too long, the lever is reducing WIP (or increasing throughput), and the law quantifies exactly how those two levers relate.

## Inappropriate use
Don't apply Little's Law to a workflow that isn't actually in a steady state (highly volatile arrival rates, frequent large batch releases) — the formula assumes a reasonably stable average, and reading too much precision into it under volatile conditions is misleading.

## Trade-offs
Enforcing lower WIP (to reduce cycle time per Little's Law) means some work waits longer to even start, trading 'everything is technically in progress' for 'fewer things in progress, but each one finishes faster' — a real cultural shift for teams used to starting everything immediately.

## Typical violations
A team starts every incoming request immediately with no WIP limit, then wonders why individual items take longer and longer to actually finish despite everyone being 'busy'.

## Anti-patterns
Maximizing 'utilization' (keeping everyone always busy on something) instead of managing WIP is a common flow anti-pattern — it directly increases cycle time per Little's Law even though it looks productive.

## Related concepts
- [[agile.flow-metrics]]
- [[agile.kanban]]
