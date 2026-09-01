import _pathfix

import context_budget


def test_estimate_tokens_is_conservative_char_budget():
    assert context_budget.estimate_tokens("") == 0
    assert context_budget.estimate_tokens("abcd") == 1
    assert context_budget.estimate_tokens("abcde") == 2


def test_budget_items_keeps_ranked_items_and_omits_overflow():
    result = context_budget.budget_items([
        {"id": "a", "content": "abcd"},
        {"id": "b", "content": "x" * 40},
    ], token_budget=5)

    assert result["selected_ids"] == ["a"]
    assert result["omitted_ids"] == ["b"]
    assert result["remaining_tokens"] == 4
