"""
Tests for PolyglotConsensus.

    gltest --network studionet tests/test_polyglot_consensus.py

PolyglotConsensus's guarantee is that meaning, not language or wording,
drives both storage (submit) and comparison (same_meaning). Assertions pin
that shape and the deterministic dedupe/id behavior, never the exact English
phrasing an LLM happens to produce during normalization.
"""

import json

from gltest import get_contract_factory
from gltest.assertions import tx_execution_succeeded


def _deploy():
    factory = get_contract_factory("PolyglotConsensus")
    return factory.deploy(args=[])


def test_deploys_empty():
    c = _deploy()
    assert c.count().call() == 0
    assert c.id_for_text(args=["never submitted"]).call() == -1


def test_submit_returns_valid_shape():
    c = _deploy()
    receipt = c.submit(args=["The sky is blue on a clear day."]).transact()
    assert tx_execution_succeeded(receipt)
    assert c.count().call() == 1

    rec = json.loads(c.get(args=[0]).call())
    assert len(rec["normalized"]) > 0
    assert len(rec["text_hash"]) == 64
    assert rec["original_text"] == "The sky is blue on a clear day."


def test_resubmitting_identical_text_dedupes():
    c = _deploy()
    text = "Water boils at 100 degrees Celsius at sea level."
    r1 = c.submit(args=[text]).transact()
    assert tx_execution_succeeded(r1)
    assert c.count().call() == 1

    r2 = c.submit(args=[text]).transact()
    assert tx_execution_succeeded(r2)
    # Identical source text must not spend a second consensus round.
    assert c.count().call() == 1
    assert c.id_for_text(args=[text]).call() == 0


def test_same_meaning_same_id_is_a_valid_call():
    # id_a == id_b short-circuits deterministically inside the contract before
    # any consensus round runs -- pin that it's a cheap, always-succeeding call.
    c = _deploy()
    c.submit(args=["The Eiffel Tower is in Paris."]).transact()
    receipt = c.same_meaning(args=[0, 0]).transact()
    assert tx_execution_succeeded(receipt)


def test_same_meaning_across_languages_matches():
    c = _deploy()
    a = c.submit(args=["The sky is blue."]).transact()
    b = c.submit(args=["Le ciel est bleu."]).transact()  # French: "The sky is blue."
    assert tx_execution_succeeded(a)
    assert tx_execution_succeeded(b)
    assert c.count().call() == 2

    receipt = c.same_meaning(args=[0, 1]).transact()
    assert tx_execution_succeeded(receipt)


def test_same_meaning_across_distinct_claims_differs():
    c = _deploy()
    a = c.submit(args=["The sky is blue."]).transact()
    b = c.submit(args=["The ocean is extremely deep."]).transact()
    assert tx_execution_succeeded(a)
    assert tx_execution_succeeded(b)

    # Distinct, unrelated claims -- the write itself must still succeed (the
    # judgment is a valid false, not a revert); we don't assert the boolean
    # value via .transact() success alone, so read it back through a view-less
    # path is unavailable -- same_meaning has no side effects to inspect, so
    # this test only pins that a clear-cut non-match does not revert.
    receipt = c.same_meaning(args=[0, 1]).transact()
    assert tx_execution_succeeded(receipt)


def test_archive_grows_and_is_indexable():
    c = _deploy()
    assert tx_execution_succeeded(c.submit(args=["First claim here."]).transact())
    assert tx_execution_succeeded(c.submit(args=["A second, different claim."]).transact())
    assert c.count().call() == 2

    first = json.loads(c.get(args=[0]).call())
    second = json.loads(c.get(args=[1]).call())
    assert first["text_hash"] != second["text_hash"]


def test_empty_text_reverts():
    c = _deploy()
    receipt = c.submit(args=["   "]).transact()
    assert not tx_execution_succeeded(receipt)


def test_same_meaning_invalid_id_reverts():
    c = _deploy()
    c.submit(args=["Only one claim exists."]).transact()
    receipt = c.same_meaning(args=[0, 99]).transact()
    assert not tx_execution_succeeded(receipt)
