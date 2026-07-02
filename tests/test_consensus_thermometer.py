"""
Tests for ConsensusThermometer.

    gltest --network studionet tests/test_consensus_thermometer.py

ConsensusThermometer never runs the real expensive analysis -- it only
predicts whether one would reach consensus. The assertions below pin the
contract's guarantees (shape of a probe record, deterministic routing given
an extreme threshold, archive indexing) rather than betting on the exact
predicted_agreement value an LLM returns for a given task.
"""

import json

from gltest import get_contract_factory
from gltest.assertions import tx_execution_succeeded


def _deploy(threshold_milli=700, tolerance_milli=200):
    factory = get_contract_factory("ConsensusThermometer")
    return factory.deploy(args=[threshold_milli, tolerance_milli])


def test_deploys_empty():
    c = _deploy()
    assert c.count().call() == 0


def test_assess_returns_valid_route_and_probe_shape():
    c = _deploy()
    receipt = c.assess(args=["Is water wet under normal conditions?"]).transact()
    assert tx_execution_succeeded(receipt)

    probe = json.loads(c.last_probe().call())
    assert probe["routed_to"] in ("FULL", "DEFERRED")
    assert 0 <= probe["predicted_agreement_milli"] <= 1000
    # sha256 hex digest is always 64 characters.
    assert len(probe["task_hash"]) == 64


def test_low_threshold_routes_full():
    # threshold_milli=1 means any nonzero predicted agreement routes FULL --
    # a model returning exactly 0.0 confidence for a plain factual task would
    # be a genuine anomaly, not something this test should tolerate silently.
    c = _deploy(threshold_milli=1, tolerance_milli=200)
    receipt = c.assess(args=["Is the sky blue on a clear day?"]).transact()
    assert tx_execution_succeeded(receipt)
    probe = json.loads(c.last_probe().call())
    assert probe["routed_to"] == "FULL"


def test_high_threshold_routes_deferred():
    # threshold_milli=1000 requires perfect predicted agreement to route FULL;
    # any realistic estimate lands DEFERRED.
    c = _deploy(threshold_milli=1000, tolerance_milli=200)
    receipt = c.assess(
        args=["Which is the single best programming language?"]
    ).transact()
    assert tx_execution_succeeded(receipt)
    probe = json.loads(c.last_probe().call())
    assert probe["routed_to"] == "DEFERRED"


def test_probe_archive_grows_and_is_indexable():
    c = _deploy()
    assert tx_execution_succeeded(c.assess(args=["Is 7 a prime number?"]).transact())
    assert tx_execution_succeeded(
        c.assess(args=["Is modern art better than classical art?"]).transact()
    )
    assert c.count().call() == 2

    first = json.loads(c.get(args=[0]).call())
    second = json.loads(c.get(args=[1]).call())
    assert first["task_hash"] != second["task_hash"]
    assert json.loads(c.last_probe().call())["task_hash"] == second["task_hash"]


def test_empty_task_reverts():
    c = _deploy()
    receipt = c.assess(args=["   "]).transact()
    assert not tx_execution_succeeded(receipt)

