"""Feature dependency graph and execution ordering (CLAUDE.md section 18)."""
from __future__ import annotations


class CycleError(Exception):
    def __init__(self, cycle: list[str]):
        self.cycle = cycle
        super().__init__(f"dependency cycle detected: {' -> '.join(cycle)}")


def order_features(features: list[dict]) -> list[str]:
    """Topologically sort features by `id`/`dependencies`.

    `features` is a list of {"id": str, "dependencies": [str, ...]}.
    Independent features keep their relative input order (stable sort) so
    that a purely-sequential executor still gets deterministic output.
    Raises CycleError if a circular dependency exists.
    """
    ids = [f["id"] for f in features]
    known = set(ids)
    deps = {f["id"]: [d for d in f.get("dependencies", []) if d in known] for f in features}

    visited: dict[str, str] = {}  # id -> "visiting" | "done"
    order: list[str] = []

    def visit(node: str, stack: list[str]) -> None:
        state = visited.get(node)
        if state == "done":
            return
        if state == "visiting":
            raise CycleError(stack + [node])
        visited[node] = "visiting"
        for dep in deps.get(node, []):
            visit(dep, stack + [node])
        visited[node] = "done"
        order.append(node)

    for fid in ids:
        visit(fid, [])

    return order
