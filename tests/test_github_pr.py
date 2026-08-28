"""Unit tests for the GitHub reporting adapter."""

import pytest

from agent.github_pr import PullRequestRef, parse_pull_request_ref, recommendation_message


def test_parse_pull_request_payload():
    ref = parse_pull_request_ref(
        {
            "repository": {"name": "penumbra", "owner": {"login": "luch91"}},
            "pull_request": {"number": 7},
        }
    )
    assert ref == PullRequestRef("luch91", "penumbra", 7)


def test_parse_pull_request_payload_rejects_non_pull_request():
    with pytest.raises(ValueError):
        parse_pull_request_ref({})


def test_recommendation_message_never_merges():
    message = recommendation_message("ACCEPT", "All rules passed.", "0xabc")
    assert "recommended for human merge" in message
    assert "merge automatically" not in message


def test_recommendation_message_rejects_unknown_verdict():
    with pytest.raises(ValueError):
        recommendation_message("MAYBE", "unclear", "0xabc")
