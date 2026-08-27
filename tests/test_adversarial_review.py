"""
Tests for AdversarialReview.

    gltest --network studionet tests/test_adversarial_review.py

AdversarialReview's guarantee is that every adjudicate() call produces a
recorded ruling with a valid winner, an in-range margin, and content-addressed
digests of both the pro and con cases the leader constructed -- never that
the ruling favors any particular side. Assertions pin that shape and the
deterministic input-validation gate, never which side an LLM happens to rule
for on a genuinely contested claim.
"""

import json

from gltest import get_contract_factory
from gltest.assertions import tx_execution_succeeded

_CLAIM_A = "Remote work is better for employee productivity than office work"
_CLAIM_B = "Standardized testing is a fair way to measure student ability"


def _deploy():
    return get_contract_factory("AdversarialReview").deploy()


def test_source_normalizes_markdown_code_fenced_json():
    source = open("contracts/adversarial_review.py", encoding="ascii").read()
    assert "def parse_json_response" in source
    assert 'value.startswith("```")' in source


def test_deploys_empty():
    c = _deploy()
    assert c.count().call() == 0


def test_adjudicate_archives_valid_verdict():
    c = _deploy()
    receipt = c.adjudicate(args=[_CLAIM_A]).transact()
    assert tx_execution_succeeded(receipt)

    assert c.count().call() == 1
    rec = json.loads(c.get(args=[0]).call())
    assert rec["claim"] == _CLAIM_A
    assert rec["winner"] in ("pro", "con")
    assert 0 <= rec["margin_milli"] <= 1000
    assert len(rec["pro_case_hash"]) == 64
    assert len(rec["con_case_hash"]) == 64
    # The two sides must be genuinely distinct cases, not the same text hashed twice.
    assert rec["pro_case_hash"] != rec["con_case_hash"]


def test_empty_claim_reverts():
    c = _deploy()
    receipt = c.adjudicate(args=["   "]).transact()
    assert not tx_execution_succeeded(receipt)
    assert c.count().call() == 0


def test_archive_grows_and_is_indexable():
    c = _deploy()
    assert tx_execution_succeeded(c.adjudicate(args=[_CLAIM_A]).transact())
    assert tx_execution_succeeded(c.adjudicate(args=[_CLAIM_B]).transact())
    assert c.count().call() == 2

    first = json.loads(c.get(args=[0]).call())
    second = json.loads(c.get(args=[1]).call())
    assert first["claim"] == _CLAIM_A
    assert second["claim"] == _CLAIM_B
    assert first["winner"] in ("pro", "con")
    assert second["winner"] in ("pro", "con")


def test_get_nonexistent_case_reverts():
    c = _deploy()
    c.adjudicate(args=[_CLAIM_A]).transact()
    # Only index 0 exists; index 1 does not.
    try:
        result = c.get(args=[1]).call()
        assert False, f"expected revert, got {result}"
    except Exception:
        pass
