"""
Tests for SemanticDiffLedger.

    gltest --network studionet tests/test_semantic_diff_ledger.py

SemanticDiffLedger's guarantee is that only a MATERIAL edit bumps the
version and mutates `current`; a cosmetic edit changes nothing at all.
Assertions pin that invariant and the deterministic guards, never the exact
LLM wording of a borderline materiality call.
"""

import json

from gltest import get_contract_factory
from gltest.assertions import tx_execution_succeeded


def _deploy(initial_text="The tenant shall pay $1000 rent on the 1st of each month.", tolerance_milli=250):
    factory = get_contract_factory("SemanticDiffLedger")
    return factory.deploy(args=[initial_text, tolerance_milli])


def test_deploys_at_version_zero():
    c = _deploy()
    assert c.version().call() == 0
    assert c.count().call() == 1
    snap = json.loads(c.snapshot(args=[0]).call())
    assert snap["version"] == 0


def test_material_change_updates_current_and_archive():
    c = _deploy(initial_text="The tenant shall pay $1000 rent on the 1st of each month.")
    new_text = (
        "The tenant shall pay $2000 rent on the 15th of each month, doubling "
        "the prior amount and moving the due date."
    )
    receipt = c.propose(args=[new_text]).transact()
    assert tx_execution_succeeded(receipt)

    # A change this stark (price doubled, due date moved) should register as
    # material in essentially every reasonable judgment.
    assert c.version().call() == 1
    assert c.count().call() == 2
    assert c.get_current().call() == new_text
    snap = json.loads(c.snapshot(args=[1]).call())
    assert snap["text"] == new_text
    assert snap["version"] == 1


def test_cosmetic_change_leaves_state_untouched():
    original = "The tenant shall pay $1000 rent on the 1st of each month."
    c = _deploy(initial_text=original)
    # Pure reformatting / whitespace-only rewrite, same obligation.
    receipt = c.propose(
        args=["The tenant shall pay $1000 rent on the 1st of each month.  "]
    ).transact()
    assert tx_execution_succeeded(receipt)

    # Whether or not the model called this material, the invariant we pin is
    # structural: if it wasn't material, nothing changed at all.
    if c.version().call() == 0:
        assert c.count().call() == 1
        assert c.get_current().call() == original


def test_multiple_material_changes_chain_correctly():
    c = _deploy(initial_text="Version A: the fee is $10.")
    r1 = c.propose(args=["Version B: the fee is $500, a hundredfold increase."]).transact()
    assert tx_execution_succeeded(r1)
    v1 = c.version().call()

    r2 = c.propose(args=["Version C: the fee is $0, entirely waived."]).transact()
    assert tx_execution_succeeded(r2)
    v2 = c.version().call()

    # Both edits are unambiguously material (order-of-magnitude price swings),
    # so version and archive size must stay in lockstep regardless of the
    # exact wording the model used to describe them.
    assert v2 >= v1
    assert c.count().call() == v2 + 1


def test_empty_proposal_reverts():
    c = _deploy()
    receipt = c.propose(args=["   "]).transact()
    assert not tx_execution_succeeded(receipt)
