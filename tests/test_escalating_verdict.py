"""
Tests for EscalatingVerdict.

    gltest --network studionet tests/test_escalating_verdict.py

EscalatingVerdict's guarantee is that the tier a dispute gets is a
deterministic function of its escrowed stake, fixed at open time, and that
resolve() always produces exactly one non-empty verdict per dispute
regardless of which of the three consensus moves handled it. Assertions
pin tier selection, the one-shot resolve gate, and the treasury ledger --
never the exact wording an LLM rules with.
"""

import json

from gltest import get_contract_factory
from gltest.assertions import tx_execution_succeeded

_MID = 1000
_LARGE = 10000

# A near-mechanical factual question -- appropriate for the STRICT tier,
# which requires byte-identical (strict_eq) agreement across validators.
_STRICT_QUESTION = "Is 7 a prime number?"

# A plain judgment question -- appropriate for COMPARATIVE, which only
# requires paraphrase-tolerant agreement on the verdict's meaning.
_COMPARATIVE_QUESTION = "Is a 30-day return window fair for an online electronics retailer?"

# A genuinely weighty, multi-angle question -- appropriate for
# NON_COMPARATIVE, whose criteria demand the ruling address multiple
# analytical lenses (factual accuracy, internal consistency,
# counter-argument robustness).
_NON_COMPARATIVE_QUESTION = (
    "Should a city ban gas-powered leaf blowers to reduce noise and emissions, "
    "given the cost to landscaping businesses?"
)


def _deploy(mid_threshold=_MID, large_threshold=_LARGE):
    factory = get_contract_factory("EscalatingVerdict")
    return factory.deploy(args=[mid_threshold, large_threshold])


def test_deploys_empty():
    c = _deploy()
    assert c.count().call() == 0


def test_zero_stake_lands_strict_tier():
    c = _deploy()
    receipt = c.open_dispute(args=[_STRICT_QUESTION]).transact(value=0)
    assert tx_execution_succeeded(receipt)

    rec = json.loads(c.get(args=[0]).call())
    assert rec["tier"] == "STRICT"
    assert rec["stake"] == 0
    assert rec["resolved"] is False


def test_mid_stake_lands_comparative_tier():
    c = _deploy()
    receipt = c.open_dispute(args=[_COMPARATIVE_QUESTION]).transact(value=5000)
    assert tx_execution_succeeded(receipt)

    rec = json.loads(c.get(args=[0]).call())
    assert rec["tier"] == "COMPARATIVE"
    assert rec["stake"] == 5000


def test_large_stake_lands_non_comparative_tier():
    c = _deploy()
    receipt = c.open_dispute(args=[_NON_COMPARATIVE_QUESTION]).transact(value=20000)
    assert tx_execution_succeeded(receipt)

    rec = json.loads(c.get(args=[0]).call())
    assert rec["tier"] == "NON_COMPARATIVE"
    assert rec["stake"] == 20000


def test_strict_tier_resolves_to_nonempty_verdict():
    c = _deploy()
    c.open_dispute(args=[_STRICT_QUESTION]).transact(value=0)

    receipt = c.resolve(args=[0]).transact()
    assert tx_execution_succeeded(receipt)

    rec = json.loads(c.get(args=[0]).call())
    assert rec["resolved"] is True
    assert len(rec["verdict"]) > 0


def test_comparative_tier_resolves_to_nonempty_verdict():
    c = _deploy()
    c.open_dispute(args=[_COMPARATIVE_QUESTION]).transact(value=5000)

    receipt = c.resolve(args=[0]).transact()
    assert tx_execution_succeeded(receipt)

    rec = json.loads(c.get(args=[0]).call())
    assert rec["resolved"] is True
    assert len(rec["verdict"]) > 0


def test_non_comparative_tier_resolves_to_nonempty_verdict():
    c = _deploy()
    c.open_dispute(args=[_NON_COMPARATIVE_QUESTION]).transact(value=20000)

    receipt = c.resolve(args=[0]).transact()
    assert tx_execution_succeeded(receipt)

    rec = json.loads(c.get(args=[0]).call())
    assert rec["resolved"] is True
    assert len(rec["verdict"]) > 0


def test_double_resolve_reverts():
    c = _deploy()
    c.open_dispute(args=[_STRICT_QUESTION]).transact(value=0)
    assert tx_execution_succeeded(c.resolve(args=[0]).transact())

    receipt = c.resolve(args=[0]).transact()
    assert not tx_execution_succeeded(receipt)


def test_resolve_nonexistent_dispute_reverts():
    c = _deploy()
    receipt = c.resolve(args=[0]).transact()
    assert not tx_execution_succeeded(receipt)


def test_empty_question_reverts():
    c = _deploy()
    receipt = c.open_dispute(args=["   "]).transact(value=0)
    assert not tx_execution_succeeded(receipt)
    assert c.count().call() == 0


def test_treasury_accumulates_and_owner_can_withdraw():
    c = _deploy()
    c.open_dispute(args=[_STRICT_QUESTION]).transact(value=0)
    c.open_dispute(args=[_COMPARATIVE_QUESTION]).transact(value=5000)
    assert c.count().call() == 2

    receipt = c.withdraw_treasury().transact()
    assert tx_execution_succeeded(receipt)


def test_tier_for_stake_is_a_pure_deterministic_function():
    c = _deploy(mid_threshold=1000, large_threshold=10000)
    assert c.tier_for_stake(args=[0]).call() == "STRICT"
    assert c.tier_for_stake(args=[999]).call() == "STRICT"
    assert c.tier_for_stake(args=[1000]).call() == "COMPARATIVE"
    assert c.tier_for_stake(args=[9999]).call() == "COMPARATIVE"
    assert c.tier_for_stake(args=[10000]).call() == "NON_COMPARATIVE"
