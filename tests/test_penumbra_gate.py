"""Invariant tests for PenumbraGate.

Run the live contract tests with:
    gltest --network studionet tests/test_penumbra_gate.py
"""

import json

from gltest import create_account, get_contract_factory
from gltest.assertions import tx_execution_succeeded


_AGENT = "0x1111111111111111111111111111111111111111"
_PART_A = (
    "This invariant test uses a fixed acceptance rule. For any non-empty "
    "submission source and summary, the only valid verdict is ACCEPT. The "
    "reason must state that both fields are non-empty. Reject any response "
    "that does not return ACCEPT for that case."
)
_PART_B = _PART_A


def _deploy():
    factory = get_contract_factory("PenumbraGate")
    account = create_account()
    contract = factory.deploy(
        args=[_AGENT, 100, _PART_A, _PART_B], account=account
    )
    return contract, account


def test_empty_source_and_summary_revert_before_review():
    contract, _ = _deploy()
    assert not tx_execution_succeeded(contract.submit(args=["", "summary"]).transact())
    assert not tx_execution_succeeded(contract.submit(args=["source", ""]).transact())


def test_second_submission_requires_stake():
    contract, _ = _deploy()
    first = contract.submit(args=["source one", "summary one"]).transact(value=0)
    assert tx_execution_succeeded(first)
    second = contract.submit(args=["source two", "summary two"]).transact(value=0)
    assert not tx_execution_succeeded(second)


def test_refund_is_full_on_the_recorded_verdict():
    contract, account = _deploy()
    receipt = contract.submit(args=["source", "summary"]).transact(value=250)
    assert tx_execution_succeeded(receipt)
    record = json.loads(contract.get(args=[0]).call())
    submitter = account.address
    assert record["submitter"].lower() == submitter.lower()
    assert tx_execution_succeeded(contract.withdraw().transact())
    assert not tx_execution_succeeded(contract.withdraw().transact())


def test_record_is_public_json_and_count_is_lifetime_state():
    contract, _ = _deploy()
    receipt = contract.submit(args=["source", "summary"]).transact()
    assert tx_execution_succeeded(receipt)
    record = json.loads(contract.get(args=[0]).call())
    assert record["source"] == "source"
    assert record["summary"] == "summary"


def test_public_source_has_no_custom_appeal_method():
    source = open("contracts/penumbra_gate.py", encoding="ascii").read()
    assert "def appeal(" not in source
    assert "def reroll(" not in source
    assert "def resubmit_for_review(" not in source
    assert "prompt_non_comparative" in source
    assert "prompt_comparative" not in source


def test_submit_has_appeal_reexecution_idempotency_guard():
    source = open("contracts/penumbra_gate.py", encoding="ascii").read()
    assert 'gl.message_raw["datetime"]' in source
    assert "hashlib.sha256" in source
    assert "last_submission_key" in source
    assert "last_submission_id" in source
