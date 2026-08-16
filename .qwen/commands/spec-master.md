---
description: Run Spec Master against a single context file for this project.
---

## User Input

```text
$ARGUMENTS
```

Use the first argument as the context file path. Do not rewrite it in prose.

## Action

1. Resolve the provided path relative to the current project.
2. Read the Spec Master protocol from `spec-master/PROTOCOL.md` in this repo.
3. Follow the protocol against the context file exactly as written.
4. Prefer the local `spec-master/` engine in this repository when available.
5. If the context file is missing, stop and report the missing path clearly.

