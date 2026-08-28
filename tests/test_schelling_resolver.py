"""
Tests for SchellingResolver.

    gltest --network studionet tests/test_schelling_resolver.py

The resolver's guarantees are structural: submissions require a stake,
resolution needs a minimum crowd, the pull-payment ledger balances, and
preconditions revert cleanly. The clustering outcome itself is asserted only
on shape (a non-empty winning set, a share that fits the pool) -- never on
which exact indices the model picks, since that is genuinely non-deterministic
LLM judgment.
"""

import json

from gltest import get_contract_factory, create_account
from gltest.assertions import tx_execution_succeeded


def _deploy(min_submissions=2):
    factory = get_contract_factory("SchellingResolver")
    return factory.deploy(args=[min_submissions])


def test_deploys_empty():
    c = _deploy()
    assert c.count().call() == 0
    assert c.is_resolved().call() is False


def test_submit_requires_stake():
    c = _deploy()
    # No value attached -> the "stake required" guard must revert.
    receipt = c.submit(args=["blue"]).transact()
    assert not tx_execution_succeeded(receipt)


def test_submit_requires_nonempty_answer():
    c = _deploy()
    receipt = c.submit(args=[""]).transact(value=100)
    assert not tx_execution_succeeded(receipt)


def test_resolve_requires_minimum_submissions():
    c = _deploy(min_submissions=2)
    assert tx_execution_succeeded(c.submit(args=["blue"]).transact(value=100))
    # Only one submission exists; resolve() must revert until the minimum is met.
    receipt = c.resolve().transact()
    assert not tx_execution_succeeded(receipt)


def test_focal_cluster_wins_and_pool_splits():
    c = _deploy(min_submissions=2)
    a = create_account()
    b = create_account()
    d = create_account()
    accounts = {
        a.address.lower(): a,
        b.address.lower(): b,
        d.address.lower(): d,
    }

    # Two submitters converge on the same focal answer, one is an outlier.
    assert tx_execution_succeeded(
        c.connect(account=a).submit(args=["blue"]).transact(value=1000)
    )
    assert tx_execution_succeeded(
        c.connect(account=b).submit(args=["the sky is blue"]).transact(value=1000)
    )
    assert tx_execution_succeeded(
        c.connect(account=d).submit(args=["green"]).transact(value=1000)
    )
    assert c.count().call() == 3

    receipt = c.resolve().transact()
    assert tx_execution_succeeded(receipt)
    assert c.is_resolved().call() is True

    winners = json.loads(c.winning_indices().call())["winning_indices"]
    # The largest cluster must be a real winning set, and cannot be everyone
    # (the outlier submission should not be included alongside the pair that
    # actually agree).
    assert len(winners) > 0
    assert len(winners) < 3

    # Total pool (3000) split across winners must be recoverable via claim().
    for i in winners:
        rec = json.loads(c.get(args=[i]).call())
        owed = c.claimable_of(args=[rec["submitter"]]).call()
        assert owed > 0
        assert owed <= 3000
        assert tx_execution_succeeded(
            c.connect(account=accounts[rec["submitter"].lower()]).claim().transact()
        )
        assert c.claimable_of(args=[accounts[rec["submitter"].lower()].address]).call() == 0


def test_double_resolve_reverts():
    c = _deploy(min_submissions=2)
    c.submit(args=["blue"]).transact(value=1000)
    c.submit(args=["blue"]).transact(value=1000)
    assert tx_execution_succeeded(c.resolve().transact())
    # A second resolve() must hit the "already resolved" guard.
    receipt = c.resolve().transact()
    assert not tx_execution_succeeded(receipt)


def test_claim_without_balance_reverts():
    c = _deploy()
    # The deployer has nothing credited yet, so claim() must revert.
    receipt = c.claim().transact()
    assert not tx_execution_succeeded(receipt)
