---
id: agile.kanban
type: Principle
name: Kanban
category: agile
applicable_roles:
  - scrum-master
tags:
  - agile
  - frameworks
depth:
  scrum-master: L4
---

# Kanban

## Definition
WIP limits, flow optimization, pull system.

## Problem it addresses
Teams that pull in work without any limit on how much is in progress at once end up with everything half-done and nothing finished, because attention is spread across too many concurrent items instead of flowing work through to completion.

## Core principles
- **WIP limits**: an explicit cap on how many items may be in progress at each stage of the workflow at once, forcing the team to finish existing work before starting new work.
- **Flow optimization**: the goal is smooth, predictable movement of items through the board, not maximizing how busy any individual person looks.
- **Pull system**: work is pulled into the next stage only when there's capacity for it (per the WIP limit), rather than pushed in whenever someone finishes their current task — this is the mechanism, tied directly to [[agile.little-law]], that actually reduces cycle time.

## Appropriate use
Use Kanban for continuous-flow work with variable-sized or unpredictably-arriving items (support tickets, ongoing maintenance, a steady stream of small features) where fixed-length sprints don't fit the work's natural rhythm.

## Inappropriate use
Don't adopt WIP limits as a number without enforcing them — a Kanban board with no actual limit enforced, or with limits set so high they're never hit, provides none of the flow benefit and is just a to-do list with columns.

## Trade-offs
Enforcing WIP limits means some ready work must wait rather than starting immediately, which can feel like idle capacity in the short term, in exchange for lower average cycle time and more predictable delivery per [[agile.little-law]].

## Typical violations
A Kanban board with a 'WIP limit: 3' column that regularly holds 8 items with no one enforcing the limit or asking why it's being exceeded.

## Anti-patterns
A Kanban board used purely as a visual to-do list, with unenforced or absent WIP limits, gets none of the actual flow-improvement benefit the practice is meant to provide.

## Related concepts
- [[agile.flow-metrics]]
- [[agile.little-law]]
