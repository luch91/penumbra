"""
Tests for AmbiguityGuard.

    gltest --network studionet tests/test_ambiguity_guard.py

AmbiguityGuard's guarantee is that it never returns a confident-sounding
answer to a question the ensemble itself would not commit to -- the stored
status is always either ABSTAIN or one of the caller-supplied options,
verbatim. Assertions pin that shape and the deterministic threshold routing,
never the exact option an LLM happens to prefer.
"""

import json

from gltest import get_contract_factory
from gltest.assertions import tx_execution_succeeded


def _deploy(ensemble_size=7, abstain_threshold_milli=600, tolerance_milli=250):
    factory = get_contract_factory("AmbiguityGuard")
    return factory.deploy(args=[ensemble_size, abstain_threshold_milli, tolerance_milli])


def test_deploys_empty():
    c = _deploy()
    assert c.count().call() == 0


def test_judge_returns_option_or_abstain():
    c = _deploy()
    receipt = c.judge(
        args=["Is 7 a prime number?", "yes,no"]
    ).transact()
    assert tx_execution_succeeded(receipt)

    rec = json.loads(c.get(args=[0]).call())
    assert rec["status"] in ("yes", "no", "ABSTAIN")
    assert 0 <= rec["confidence_milli"] <= 1000
    assert c.did_abstain().call() == (rec["status"] == "ABSTAIN")


def test_low_abstain_threshold_rarely_abstains():
    # abstain_threshold_milli=1 means any nonzero commit_fraction routes to a
    # real option; a model returning exactly 0.0 commitment on a plain
    # factual question would be a genuine anomaly, not something to tolerate.
    c = _deploy(abstain_threshold_milli=1)
    receipt = c.judge(
        args=["Is the sky blue on a clear day?", "yes,no"]
    ).transact()
    assert tx_execution_succeeded(receipt)
    status = json.loads(c.get(args=[0]).call())["status"]
    assert status != "ABSTAIN"
    assert status in ("yes", "no")


def test_high_abstain_threshold_forces_abstain():
    # abstain_threshold_milli=1000 requires perfect ensemble commitment to
    # avoid ABSTAIN; a genuinely subjective question should never clear that.
    c = _deploy(abstain_threshold_milli=1000)
    receipt = c.judge(
        args=["Which is the single best programming language?", "python,rust,go"]
    ).transact()
    assert tx_execution_succeeded(receipt)
    status = json.loads(c.get(args=[0]).call())["status"]
    assert status == "ABSTAIN"


def test_archive_grows_and_is_indexable():
    c = _deploy()
    assert tx_execution_succeeded(
        c.judge(args=["Is water wet under normal conditions?", "yes,no"]).transact()
    )
    assert tx_execution_succeeded(
        c.judge(args=["Is modern art better than classical art?", "yes,no"]).transact()
    )
    assert c.count().call() == 2

    status = json.loads(c.status().call())
    assert status["count"] == 2
    assert status["abstain_count"] <= 2


def test_empty_question_reverts():
    c = _deploy()
    receipt = c.judge(args=["   ", "yes,no"]).transact()
    assert not tx_execution_succeeded(receipt)


def test_single_option_reverts():
    c = _deploy()
    receipt = c.judge(args=["Is 7 a prime number?", "yes"]).transact()
    assert not tx_execution_succeeded(receipt)
