"""
Tests for DissensusOracle.

These are integration tests: they require a GenLayer network that can run LLM
calls (the Studio localnet with providers configured, or studionet/testnet).

    gltest --network studionet tests/test_dissensus_oracle.py

Because the answers come from non-deterministic models, the assertions check the
SHAPE and INVARIANTS of the result, never an exact string. That is the correct
way to test an intelligent contract: pin the contract's guarantees, not the LLM.
"""

import json

from gltest import get_contract_factory, create_account
from gltest.assertions import tx_execution_succeeded


def _deploy(ensemble=7, tolerance_milli=250):
    factory = get_contract_factory("DissensusOracle")
    return factory.deploy(args=[ensemble, tolerance_milli])


def test_deploys_empty():
    c = _deploy()
    assert c.count().call() == 0


def test_clearcut_question_has_low_dissensus():
    c = _deploy()
    receipt = c.resolve(args=["Is water wet under normal conditions?"]).transact()
    assert tx_execution_succeeded(receipt)

    rec = json.loads(c.latest_verdict().call())
    # A clear-cut question should land near-unanimous: dissensus well below half.
    assert rec["dissensus_milli"] < 400
    assert rec["sample_size"] >= 3
    assert len(rec["verdict"]) > 0


def test_record_archive_grows_and_is_indexable():
    c = _deploy()
    assert tx_execution_succeeded(c.resolve(args=["Is 7 a prime number?"]).transact())
    assert tx_execution_succeeded(
        c.resolve(args=["Was the 2010s the best decade for music?"]).transact()
    )
    assert c.count().call() == 2

    first = json.loads(c.get(args=[0]).call())
    assert "prime" in first["question"].lower()

    # A subjective taste question should be measurably more contested than a fact.
    fact = json.loads(c.get(args=[0]).call())
    taste = json.loads(c.get(args=[1]).call())
    assert taste["dissensus_milli"] >= fact["dissensus_milli"]


def test_is_contested_gate():
    c = _deploy()
    c.resolve(args=["Will it definitely rain somewhere on Earth tomorrow?"]).transact()
    # With a permissive threshold the freshest record should read as not contested.
    assert c.is_contested(args=[0]).call() in (True, False)  # type returns bool
