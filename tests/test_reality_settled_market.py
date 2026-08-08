"""
Tests for RealitySettledMarket.

    gltest --network studionet tests/test_reality_settled_market.py

RealitySettledMarket's guarantees are structural and monetary, never a bet on
exact LLM wording: pools accumulate correctly, only YES/NO stakes are
accepted, a settled market pays winners the whole pool via a pull ledger that
can never over-credit, and an unresolvable market REFUNDS every stake instead
of guessing a side. The two settle() tests deploy a clearly-YES market and a
deliberately unresolvable one (dead sources) and assert the invariants that
must hold for EITHER a decisive settlement or a refund -- a borderline model
call may occasionally flake and should be re-run, never "fixed" by weakening a
guard.
"""

import json

from gltest import get_contract_factory, create_account
from gltest.assertions import tx_execution_succeeded


_YES = "YES"
_NO = "NO"
_REFUND = "REFUND"

# A question two reputable sources settle unambiguously YES.
_CLEAR_QUESTION = "Did Apollo 11 land humans on the Moon in 1969?"
_CLEAR_URLS = "https://en.wikipedia.org/wiki/Apollo_11,https://en.wikipedia.org/wiki/Moon_landing"

# Two unreachable sources -> the fetch guard degrades both to failed sources,
# leaving nothing to determine the question -> the ambiguity guard REFUNDS.
_DEAD_QUESTION = "Did the fictional nation of Wakanda join the United Nations in 2018?"
_DEAD_URLS = (
    "https://nonexistent-penumbra-market-a.invalid,"
    "https://nonexistent-penumbra-market-b.invalid"
)


def _deploy(question=_CLEAR_QUESTION, urls=_CLEAR_URLS, abstain=600, tol=250):
    factory = get_contract_factory("RealitySettledMarket")
    return factory.deploy(args=[question, urls, abstain, tol])


def test_deploys_unsettled():
    c = _deploy()
    st = json.loads(c.status().call())
    assert st["outcome"] == ""
    assert st["yes_pool"] == 0 and st["no_pool"] == 0
    assert st["bets"] == 0
    assert c.is_settled().call() is False
    assert c.count().call() == 0


def test_bet_requires_stake():
    c = _deploy()
    # gltest sends value 0 by default -> the stake guard must revert.
    receipt = c.bet(args=[_YES]).transact()
    assert not tx_execution_succeeded(receipt)
    assert c.count().call() == 0


def test_bet_rejects_invalid_side():
    c = _deploy()
    receipt = c.bet(args=["MAYBE"]).transact(value=1000)
    assert not tx_execution_succeeded(receipt)
    assert c.count().call() == 0


def test_bets_accumulate_into_pools():
    c = _deploy()
    assert tx_execution_succeeded(c.bet(args=[_YES]).transact(value=1000))
    assert tx_execution_succeeded(c.bet(args=["no"]).transact(value=500))  # case-insensitive
    assert tx_execution_succeeded(c.bet(args=[_YES]).transact(value=250))

    st = json.loads(c.status().call())
    assert st["yes_pool"] == 1250
    assert st["no_pool"] == 500
    assert st["bets"] == 3


def test_settle_requires_bets():
    c = _deploy()
    receipt = c.settle().transact()
    assert not tx_execution_succeeded(receipt)


def test_redeem_before_settle_reverts():
    c = _deploy()
    assert tx_execution_succeeded(c.bet(args=[_YES]).transact(value=1000))
    receipt = c.redeem().transact()
    assert not tx_execution_succeeded(receipt)


def test_clear_market_settles_and_winner_takes_pool():
    c = _deploy(question=_CLEAR_QUESTION, urls=_CLEAR_URLS)
    yes_bettor = create_account()
    no_bettor = create_account()
    assert tx_execution_succeeded(
        c.connect(account=yes_bettor).bet(args=[_YES]).transact(value=1000)
    )
    assert tx_execution_succeeded(
        c.connect(account=no_bettor).bet(args=[_NO]).transact(value=500)
    )

    receipt = c.settle().transact()
    assert tx_execution_succeeded(receipt)
    assert c.is_settled().call() is True
    outcome = c.settled_outcome().call()

    # This question is settled YES by its sources; the one thing that must
    # never happen is a confident NO. A cautious REFUND is acceptable (the
    # model is non-deterministic), but the invariants below must hold either
    # way, and the total credited can never exceed the pool.
    assert outcome in (_YES, _REFUND)

    yes_claim = c.claimable_of(args=[yes_bettor.address]).call()
    no_claim = c.claimable_of(args=[no_bettor.address]).call()
    assert yes_claim + no_claim <= 1500  # never over-credit the pool

    if outcome == _YES:
        # Single winning-side bettor takes the whole pool exactly (no dust).
        assert yes_claim == 1500
        assert no_claim == 0
        # Winner can redeem once; the ledger is drained afterward.
        r = c.connect(account=yes_bettor).redeem().transact()
        assert tx_execution_succeeded(r)
        assert c.claimable_of(args=[yes_bettor.address]).call() == 0
        # Loser has nothing to redeem.
        assert not tx_execution_succeeded(
            c.connect(account=no_bettor).redeem().transact()
        )
    else:  # REFUND
        assert yes_claim == 1000
        assert no_claim == 500
        assert tx_execution_succeeded(
            c.connect(account=yes_bettor).redeem().transact()
        )
        assert tx_execution_succeeded(
            c.connect(account=no_bettor).redeem().transact()
        )
        assert c.claimable_of(args=[yes_bettor.address]).call() == 0
        assert c.claimable_of(args=[no_bettor.address]).call() == 0

    # A settled market is closed: no re-settling, no new bets.
    assert not tx_execution_succeeded(c.settle().transact())
    assert not tx_execution_succeeded(
        c.connect(account=yes_bettor).bet(args=[_YES]).transact(value=100)
    )


def test_unresolvable_market_refunds_every_stake():
    c = _deploy(question=_DEAD_QUESTION, urls=_DEAD_URLS)
    a = create_account()
    b = create_account()
    assert tx_execution_succeeded(c.connect(account=a).bet(args=[_YES]).transact(value=700))
    assert tx_execution_succeeded(c.connect(account=b).bet(args=[_NO]).transact(value=300))

    receipt = c.settle().transact()
    assert tx_execution_succeeded(receipt)

    # With both sources unreachable there is nothing to determine the answer,
    # so the ambiguity guard must refuse to pick a side and REFUND. Each bettor
    # is owed exactly their own stake back.
    outcome = c.settled_outcome().call()
    assert outcome == _REFUND
    assert c.claimable_of(args=[a.address]).call() == 700
    assert c.claimable_of(args=[b.address]).call() == 300
