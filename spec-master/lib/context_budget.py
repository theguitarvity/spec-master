"""Context budget accounting for hosted harness execution.

The host runtime owns the real tokenizer, but Spec Master still needs a
deterministic preflight budget so context growth is governed before prompts
are assembled. This module uses a conservative character-based token estimate
and returns a trimmed, auditable bundle.
"""
from __future__ import annotations

ESTIMATED_CHARS_PER_TOKEN = 4
DEFAULT_TOKEN_BUDGET = 12000


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, (len(text) + ESTIMATED_CHARS_PER_TOKEN - 1) // ESTIMATED_CHARS_PER_TOKEN)


def budget_items(items: list[dict], token_budget: int = DEFAULT_TOKEN_BUDGET,
                 text_key: str = "content") -> dict:
    """Select items until the estimated token budget is exhausted.

    Items are assumed to arrive already ranked. Returned payload includes
    selected and omitted ids so the host agent can explain what was loaded.
    """
    selected = []
    omitted = []
    used = 0
    for item in items:
        cost = estimate_tokens(str(item.get(text_key, "")))
        entry = dict(item)
        entry["estimated_tokens"] = cost
        if used + cost <= token_budget:
            selected.append(entry)
            used += cost
        else:
            omitted.append(entry)
    return {
        "token_budget": token_budget,
        "estimated_tokens": used,
        "remaining_tokens": max(0, token_budget - used),
        "selected": selected,
        "omitted": omitted,
        "selected_ids": [i.get("id") for i in selected if i.get("id")],
        "omitted_ids": [i.get("id") for i in omitted if i.get("id")],
    }
