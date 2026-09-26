"""Quality gate command derivation (CLAUDE.md section 28).

Never hardcodes a command family (e.g. `npm test`) for every project; only
returns gates backed by a manifest that `discovery.scan()` actually found.
Security scanners follow the same rule (sast_gates.py): a configured scanner
becomes a blocking gate, an absent one is simply not a gate.
"""
from __future__ import annotations

try:
    from . import discovery, sast_gates
except ImportError:  # executed as a plain script/module, not a package
    import discovery
    import sast_gates

_GATE_ORDER = ["build", "lint", "type_check", "test", "coverage"]


def detect(root: str = ".") -> list[dict]:
    info = discovery.scan(root)
    gates: list[dict] = []
    for stack in info["stacks"]:
        commands = stack["commands"]
        for gate_name in _GATE_ORDER:
            if gate_name in commands:
                gates.append({
                    "name": f"{gate_name} ({stack['language']})",
                    "command": commands[gate_name],
                    "blocking": gate_name in ("build", "test"),
                })
    gates.extend(sast_gates.detect(root))
    return gates
