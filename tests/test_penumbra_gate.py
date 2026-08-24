"""Invariant tests for PenumbraGate.

Run the live contract tests with:
    gltest --network studionet tests/test_penumbra_gate.py
"""

import json

from gltest import get_contract_factory
from gltest.assertions import tx_execution_succeeded


_AGENT = "0x1111111111111111111111111111111111111111"
_PART_A = "NN-1\nNN-2\nNN-3\nNN-4"
_PART_B = "NN-5\nNN-6\nNN-7\nNN-8"


def _deploy():
    factory = get_contract_factory("PenumbraGate")
    return factory.deploy(args=[_AGENT, 100, _PART_A, _PART_B])


def test_empty_source_and_summary_revert_before_review():
    contract = _deploy()
    assert not tx_execution_succeeded(contract.submit(args=["", "summary"]).transact())
    assert not tx_execution_succeeded(contract.submit(args=["source", ""]).transact())


def test_second_submission_requires_stake():
    contract = _deploy()
    first = contract.submit(args=["source one", "summary one"]).transact(value=0)
    assert tx_execution_succeeded(first)
    second = contract.submit(args=["source two", "summary two"]).transact(value=0)
    assert not tx_execution_succeeded(second)


def test_refund_is_full_on_the_recorded_verdict():
    contract = _deploy()
    receipt = contract.submit(args=["source", "summary"]).transact(value=250)
    assert tx_execution_succeeded(receipt)
    submitter = json.loads(contract.get(args=[0]).call())["submitter"]
    assert contract.claimable_of(args=[submitter]).call() == 250
    assert tx_execution_succeeded(contract.withdraw().transact())
    assert contract.claimable_of(args=[submitter]).call() == 0


def test_record_is_public_json_and_count_is_lifetime_state():
    contract = _deploy()
    receipt = contract.submit(args=["source", "summary"]).transact()
    assert tx_execution_succeeded(receipt)
    record = json.loads(contract.get(args=[0]).call())
    assert record["source"] == "source"
    assert record["summary"] == "summary"
    assert contract.submission_count_of(args=[record["submitter"]]).call() == 1


def test_public_source_has_no_custom_appeal_method():
    source = open("contracts/penumbra_gate.py", encoding="ascii").read()
    assert "def appeal(" not in source
    assert "def reroll(" not in source
    assert "def resubmit_for_review(" not in source
    assert "prompt_comparative" in source
    assert "prompt_non_comparative" not in source
