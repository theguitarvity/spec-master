import _pathfix

import tool_policy


def test_policy_allows_known_safe_test_command():
    result = tool_policy.classify_command("python3 -m pytest")
    assert result["allowed"] is True
    assert result["risk"] == "low"


def test_policy_blocks_destructive_sequence():
    result = tool_policy.classify_command("rm -rf .")
    assert result["allowed"] is False
    assert result["risk"] == "blocked"


def test_policy_requires_approval_for_unknown_executable():
    result = tool_policy.classify_command("deploy-prod")
    assert result["allowed"] is False
    assert result["risk"] == "requires_approval"


def test_preflight_aggregates_blocked_commands():
    result = tool_policy.preflight(["python3 -m pytest", "sudo reboot"])
    assert result["allowed"] is False
    assert len(result["blocked"]) == 1
