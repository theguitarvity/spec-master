# Quality Gates

No quality gates detected for this project (discovery.py does not yet
recognize a stdlib-only Python project as a stack with build/lint/test
commands — a pre-existing limitation, out of scope for this feature).

The project's actual test gate was run directly:
`python3 -m unittest discover -s spec-master/tests -v` — 129 passed, 0 failed.
