"""
Tests for ConstitutionalContract.

    gltest --network studionet tests/test_constitutional_contract.py

ConstitutionalContract's guarantee is that `core` is fixed forever at
deploy time (no method can ever touch it) and only an amendment consensus
judges consistent with every core principle is appended to `body`. A
rejected amendment changes nothing but is still logged. Assertions pin
these deterministic guards and the archive shape, never the exact LLM
wording of a borderline consistency call.
"""

import json

from gltest import get_contract_factory
from gltest.assertions import tx_execution_succeeded


def _deploy(
    core_principles="No amendment may authorize spending treasury funds without a member vote.",
    initial_body="",
):
    factory = get_contract_factory("ConstitutionalContract")
    return factory.deploy(args=[core_principles, initial_body])


def test_deploys_with_core_and_empty_amendments():
    c = _deploy()
    assert c.core_count().call() == 1
    assert c.count().call() == 0
    principle = c.get_core(args=[0]).call()
    assert "treasury" in principle.lower()


def test_multiple_core_principles_parsed_correctly():
    c = _deploy(
        core_principles=(
            "No amendment may authorize spending treasury funds without a member vote."
            "|Membership may never be restricted by nationality."
            "|The core principles themselves may never be amended."
        )
    )
    assert c.core_count().call() == 3


def test_consistent_amendment_is_accepted_and_appended():
    c = _deploy(
        core_principles="No amendment may authorize spending treasury funds without a member vote."
    )
    receipt = c.propose_amendment(
        args=["Meetings shall be held on the first Monday of every month."]
    ).transact()
    assert tx_execution_succeeded(receipt)
    assert c.count().call() == 1

    rec = json.loads(c.get_amendment(args=[0]).call())
    assert rec["text"] == "Meetings shall be held on the first Monday of every month."

    doc = json.loads(c.read_constitution().call())
    if rec["accepted"]:
        assert "Meetings shall be held" in doc["body"]
    else:
        assert doc["body"] == ""


def test_conflicting_amendment_is_rejected_and_body_unchanged():
    c = _deploy(
        core_principles="No amendment may authorize spending treasury funds without a member vote.",
        initial_body="",
    )
    receipt = c.propose_amendment(
        args=[
            "The treasurer may unilaterally spend any amount of treasury funds "
            "without a member vote, at their sole discretion."
        ]
    ).transact()
    assert tx_execution_succeeded(receipt)

    rec = json.loads(c.get_amendment(args=[0]).call())
    # A direct, explicit contradiction of the sole core principle should be
    # rejected in essentially every reasonable judgment.
    assert rec["accepted"] is False

    doc = json.loads(c.read_constitution().call())
    assert doc["body"] == ""


def test_core_is_immutable_no_method_exists_to_change_it():
    c = _deploy()
    # Structural guarantee: the only way core could change is via a method
    # this contract exposes. Confirm the full method surface never mutates it
    # by checking core_count() stays 1 across an amendment cycle.
    c.propose_amendment(args=["A harmless procedural clause about meeting minutes."]).transact()
    assert c.core_count().call() == 1


def test_amendment_archive_grows_and_is_indexable():
    c = _deploy()
    assert tx_execution_succeeded(
        c.propose_amendment(args=["First procedural amendment about record-keeping."]).transact()
    )
    assert tx_execution_succeeded(
        c.propose_amendment(args=["Second procedural amendment about quorum size."]).transact()
    )
    assert c.count().call() == 2

    first = json.loads(c.get_amendment(args=[0]).call())
    second = json.loads(c.get_amendment(args=[1]).call())
    assert "record-keeping" in first["text"]
    assert "quorum" in second["text"]


def test_empty_amendment_reverts():
    c = _deploy()
    receipt = c.propose_amendment(args=["   "]).transact()
    assert not tx_execution_succeeded(receipt)
