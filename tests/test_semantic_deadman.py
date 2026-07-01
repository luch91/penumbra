"""
Tests for SemanticDeadman.

    gltest --network studionet tests/test_semantic_deadman.py

Unlike JailbreakBounty/SchellingResolver, poke() and check_in() are plain
(non-payable) writes, so the full LLM-judgment path is exercisable here without
the CLI payable-value limitation. Guarantees asserted are structural: only the
owner can check_in(), the switch releases exactly once and stays released,
claim() follows the pull-payment ledger, and a genuinely unreachable liveness
source is judged not-alive (a deterministic, clear-cut case — a real fetch
failure, not a borderline LLM opinion). We never assert the exact wording of
an "alive" judgment against a live, ambiguous source, since that is genuinely
non-deterministic model opinion.
"""

import json

from gltest import get_contract_factory, create_account
from gltest.assertions import tx_execution_succeeded

BENEFICIARY = "0x1111111111111111111111111111111111111111"
DEAD_URL = "https://this-domain-genuinely-does-not-exist-penumbra-test-8842.com/"


def _deploy(url=DEAD_URL, policy="Alive only if the page loads and shows a recent, dated public post."):
    factory = get_contract_factory("SemanticDeadman")
    return factory.deploy(args=[BENEFICIARY, url, policy])


def test_deploys_armed():
    c = _deploy()
    status = json.loads(c.status().call())
    assert status["released"] is False
    assert status["last_alive_snapshot"] == ""
    assert status["treasury"] == 0


def test_only_owner_can_check_in():
    c = _deploy()
    other = create_account()
    receipt = c.connect(account=other).check_in().transact()
    assert not tx_execution_succeeded(receipt)


def test_claim_without_balance_reverts():
    c = _deploy()
    receipt = c.claim().transact()
    assert not tx_execution_succeeded(receipt)


def test_dead_source_releases_and_pays_out():
    c = _deploy()
    receipt = c.poke().transact()
    assert tx_execution_succeeded(receipt)

    status = json.loads(c.status().call())
    assert status["released"] is True

    # No treasury was ever funded (payable fund() is untestable via this
    # harness's CLI-equivalent path — see CLAUDE.md), so nothing is owed, but
    # the release itself must be permanent and idempotent-safe.
    owed = c.claimable_of(args=[BENEFICIARY]).call()
    assert owed == status["treasury"]


def test_poke_after_release_reverts():
    c = _deploy()
    assert tx_execution_succeeded(c.poke().transact())
    receipt = c.poke().transact()
    assert not tx_execution_succeeded(receipt)


def test_check_in_after_release_reverts():
    c = _deploy()
    assert tx_execution_succeeded(c.poke().transact())
    receipt = c.check_in().transact()
    assert not tx_execution_succeeded(receipt)
