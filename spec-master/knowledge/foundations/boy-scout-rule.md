---
id: principle.boy-scout-rule
type: Principle
name: Boy Scout Rule
category: foundations
applicable_roles:
  - tech-lead
  - backend-dev
  - frontend-dev
tags:
  - agile
  - practices
depth:
  tech-lead: L3
---

# Boy Scout Rule

## Definition
Leave code cleaner than you found it, incremental improvement.

## Problem it addresses
Codebases decay gradually: no single commit makes things much worse, but the accumulation of many 'good enough for now' changes leaves a codebase no one wants to touch. Waiting for a dedicated 'cleanup sprint' rarely happens.

## Core principles
- 'Leave the code cleaner than you found it' — attributed to Robert C. Martin, borrowed from the actual Boy Scouts' campsite rule.
- Cleanup happens incrementally, as a byproduct of regular feature work, rather than as a separate, hard-to-schedule initiative.
- The rule is scoped to code you're already touching — it is not license to refactor unrelated modules while fixing an unrelated bug.

## Appropriate use
Apply it opportunistically: while implementing a feature or fixing a bug, rename a confusing variable, extract a small duplicated block, or tighten a nearby type — changes small enough to stay inside the current commit's blast radius.

## Inappropriate use
Do not use the Boy Scout Rule to justify a large, unrelated refactor bundled into a feature PR — that inflates review risk and obscures the actual change; large refactors deserve their own reviewed change.

## Trade-offs
Incremental cleanup keeps PRs slightly larger and reviewers need to distinguish 'the actual change' from 'the drive-by cleanup', in exchange for steadily improving code health without ever needing a dedicated cleanup sprint.

## Typical violations
Repeatedly working around a confusingly named function instead of renaming it while already inside that file, because 'that's not what this ticket is about' — small, safe cleanup deferred indefinitely.

## Anti-patterns
Its counterpart failure is scope creep — turning a bug-fix PR into a sprawling refactor under the banner of 'cleaning up while I'm here'; the rule is meant to bound cleanup to the campsite, not the whole park.

## Related concepts
- [[principle.technical-debt]]
- [[principle.evolutionary-design]]
