# Greenfield track (new project)

Use when there is no code yet. Spec Master asks, proposes, and waits.
Nothing is written without an explicit yes from the user.

1. **Intake** — `python3 spec-master/lib/cli.py tracks greenfield-intake`.
   Ask the stack question (python, node, go, rust) and the project name, in one
   batch with the other intake questions.
2. **Propose** — `tracks greenfield-propose --path . --stack <stack> --name <name>`.
   Returns `applied: false`: a skeleton, one CI workflow and the minimal test
   gate for the stack. Show the file list and the gate to the user. Files that
   already exist are marked `exists: true`.
3. **Confirm** — only after the user says yes in chat:
   `tracks greenfield-apply --path . --stack <stack> --name <name> --confirm`.
   Without `--confirm` it exits 2 and writes nothing. It never overwrites an
   existing file and reports `written` and `skipped`.
4. **Gates** — Principle VIII still only detects: run
   `python3 spec-master/lib/cli.py gates detect --path .` afterwards and use
   what it returns; do not hand-write `.spec-master/gates.json`.
5. **Constitution and first feature** — proceed with `speckit-constitution`
   from the user's stated principles (no repository evidence exists yet), then
   the normal lane.

Rules: never choose the stack for the user; never apply on a "probably yes";
the proposal is a starting point, not a framework decision.
