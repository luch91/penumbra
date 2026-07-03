"""
Tests for IntentLock.

    gltest --network studionet tests/test_intent_lock.py

IntentLock's guarantee is that requests are judged against the written
policy conservatively (default-deny on ambiguity), that only the owner can
change the policy, and that a nonce-scoped grant can't be replayed once it
fires. Assertions pin the deterministic guards and the audit trail shape,
never the exact LLM wording of a borderline judgment.
"""

import json

from gltest import get_contract_factory, create_account
from gltest.assertions import tx_execution_succeeded


def _deploy(policy=""):
    factory = get_contract_factory("IntentLock")
    return factory.deploy(args=[policy])


def test_deploys_with_policy():
    c = _deploy(policy="Only allow requests that mention the word 'ping'.")
    assert c.get_policy().call() == "Only allow requests that mention the word 'ping'."
    assert c.count().call() == 0


def test_request_without_policy_reverts():
    c = _deploy(policy="")
    receipt = c.request(args=["do anything", ""]).transact()
    assert not tx_execution_succeeded(receipt)


def test_clear_cut_allowed_action_is_granted():
    c = _deploy(policy="Allow any action whose text contains the exact word 'ping'.")
    receipt = c.request(args=["please ping the server", ""]).transact()
    assert tx_execution_succeeded(receipt)
    assert c.count().call() == 1

    rec = json.loads(c.get(args=[0]).call())
    assert rec["granted"] is True
    assert rec["action"] == "please ping the server"


def test_clear_cut_disallowed_action_is_denied():
    c = _deploy(policy="Allow ONLY actions whose text contains the exact word 'ping'. Deny everything else, including anything about 'pong'.")
    receipt = c.request(args=["send a pong reply", ""]).transact()
    assert tx_execution_succeeded(receipt)

    rec = json.loads(c.get(args=[0]).call())
    assert rec["granted"] is False


def test_only_owner_can_set_policy():
    c = _deploy(policy="initial policy")
    other = create_account()
    receipt = c.connect(account=other).set_policy(args=["a new policy"]).transact()
    assert not tx_execution_succeeded(receipt)
    assert c.get_policy().call() == "initial policy"


def test_owner_can_update_policy():
    c = _deploy(policy="initial policy")
    assert tx_execution_succeeded(c.set_policy(args=["updated policy"]).transact())
    assert c.get_policy().call() == "updated policy"


def test_empty_policy_update_reverts():
    c = _deploy(policy="initial policy")
    receipt = c.set_policy(args=["   "]).transact()
    assert not tx_execution_succeeded(receipt)


def test_empty_action_reverts():
    c = _deploy(policy="allow anything")
    receipt = c.request(args=["   ", ""]).transact()
    assert not tx_execution_succeeded(receipt)


def test_nonce_scoped_grant_cannot_be_replayed():
    c = _deploy(policy="Allow any action whose text contains the exact word 'ping'.")
    assert c.nonce_used(args=[create_account().address, "ping once", "abc"]).call() is False

    receipt = c.request(args=["ping once", "abc"]).transact()
    assert tx_execution_succeeded(receipt)
    rec = json.loads(c.get(args=[0]).call())
    assert rec["granted"] is True

    # Same nonce again must revert -- the one-time permission was consumed.
    receipt2 = c.request(args=["ping once", "abc"]).transact()
    assert not tx_execution_succeeded(receipt2)


def test_denied_nonce_request_can_be_retried():
    c = _deploy(policy="Allow ONLY actions whose text contains the exact word 'ping'. Deny everything else.")
    receipt = c.request(args=["do something unrelated", "xyz"]).transact()
    assert tx_execution_succeeded(receipt)
    rec = json.loads(c.get(args=[0]).call())
    assert rec["granted"] is False

    # Nothing was granted, so the same nonce should still be usable.
    receipt2 = c.request(args=["please ping now", "xyz"]).transact()
    assert tx_execution_succeeded(receipt2)


def test_grant_archive_grows_and_is_indexable():
    c = _deploy(policy="Allow any action whose text contains the exact word 'ping'.")
    assert tx_execution_succeeded(c.request(args=["ping request one", ""]).transact())
    assert tx_execution_succeeded(c.request(args=["ping request two", ""]).transact())
    assert c.count().call() == 2

    last = json.loads(c.last_grant().call())
    assert last["action"] == "ping request two"
