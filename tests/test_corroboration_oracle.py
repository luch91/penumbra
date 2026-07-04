"""
Tests for CorroborationOracle.

    gltest --network studionet tests/test_corroboration_oracle.py

CorroborationOracle's guarantee is that a fact is only ever stored once
independent sources corroborate it above the caller's threshold; anything
that fails to clear the threshold reverts and appends nothing. Assertions
pin that shape and the deterministic threshold gate, never the exact
wording an LLM extracts from a page.
"""

import json

from gltest import get_contract_factory
from gltest.assertions import tx_execution_succeeded

# Two stable, static reference pages about the same simple, well-known fact.
# Live smoke-testing on studionet twice reproduced ratio_milli == 500 for this
# exact (question, urls) pair -- both Wikipedia pages restate the value, but
# the model only counts one as an explicit "agreeing" source. That makes this
# pair useful for both a low-threshold success test and a high-threshold
# revert test without betting on genuinely volatile LLM judgment.
_QUESTION = "What is the boiling point of water at sea level in Celsius"
_URLS = "https://en.wikipedia.org/wiki/Boiling_point,https://en.wikipedia.org/wiki/Water"


def _deploy(threshold_milli=300, tolerance_milli=200):
    factory = get_contract_factory("CorroborationOracle")
    return factory.deploy(args=[threshold_milli, tolerance_milli])


def test_deploys_empty():
    c = _deploy()
    assert c.count().call() == 0


def test_corroborated_fact_is_accepted_and_archived():
    # threshold_milli=300 is low enough that even partial corroboration
    # (observed live: 1 of 2 sources counted as agreeing, ratio_milli=500)
    # clears it.
    c = _deploy(threshold_milli=300)
    receipt = c.establish(args=[_QUESTION, _URLS]).transact()
    assert tx_execution_succeeded(receipt)

    assert c.count().call() == 1
    rec = json.loads(c.get(args=[0]).call())
    assert rec["question"] == _QUESTION
    assert len(rec["value"]) > 0
    assert 0 <= rec["ratio_milli"] <= 1000
    assert rec["ratio_milli"] >= 300
    assert rec["sources_count"] == 2

    latest = json.loads(c.latest_fact().call())
    assert latest == rec


def test_high_threshold_on_weak_corroboration_reverts():
    # threshold_milli=1000 requires every source to explicitly agree; the
    # same (question, urls) pair observed live at ratio_milli=500 does not
    # clear this, and nothing should be archived.
    c = _deploy(threshold_milli=1000)
    receipt = c.establish(args=[_QUESTION, _URLS]).transact()
    assert not tx_execution_succeeded(receipt)
    assert c.count().call() == 0


def test_single_url_reverts():
    c = _deploy()
    receipt = c.establish(args=[_QUESTION, "https://en.wikipedia.org/wiki/Water"]).transact()
    assert not tx_execution_succeeded(receipt)
    assert c.count().call() == 0


def test_too_many_urls_reverts():
    c = _deploy()
    nine_urls = ",".join(f"https://example.com/{i}" for i in range(9))
    receipt = c.establish(args=[_QUESTION, nine_urls]).transact()
    assert not tx_execution_succeeded(receipt)
    assert c.count().call() == 0


def test_empty_question_reverts():
    c = _deploy()
    receipt = c.establish(args=["   ", _URLS]).transact()
    assert not tx_execution_succeeded(receipt)
    assert c.count().call() == 0


def test_archive_grows_and_is_indexable():
    c = _deploy(threshold_milli=1)
    assert tx_execution_succeeded(
        c.establish(args=[_QUESTION, _URLS]).transact()
    )
    assert tx_execution_succeeded(
        c.establish(
            args=[
                "What is the freezing point of water at sea level in Celsius",
                _URLS,
            ]
        ).transact()
    )
    assert c.count().call() == 2

    first = json.loads(c.get(args=[0]).call())
    second = json.loads(c.get(args=[1]).call())
    assert "boiling" in first["question"].lower()
    assert "freezing" in second["question"].lower()
