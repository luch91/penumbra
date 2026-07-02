"""
Tests for SemanticCommitReveal.

    gltest --network studionet tests/test_semantic_commit_reveal.py

SemanticCommitReveal's guarantee is that a reveal is bound to the exact
pre-image via a deterministic hash check (unforgeable), and separately
gated on whether the public statement means the same as the private intent
(judged by consensus, paraphrase-tolerant). Assertions pin the deterministic
guards and the phase state machine, never the exact LLM verdict on a
borderline paraphrase.
"""

import hashlib
import json

from gltest import get_contract_factory, create_account
from gltest.assertions import tx_execution_succeeded


def _deploy():
    factory = get_contract_factory("SemanticCommitReveal")
    return factory.deploy(args=[])


def _hash(intent: str, salt: str) -> str:
    return hashlib.sha256((intent + salt).encode()).hexdigest()


def test_deploys_in_commit_phase():
    c = _deploy()
    assert c.phase_now().call() == "COMMIT"
    assert c.count().call() == 0
    assert c.reveal_count().call() == 0


def test_commit_then_reveal_matching_intent_is_accepted():
    c = _deploy()
    intent = "I will vote yes on proposal 7"
    salt = "saltvalue123"
    h = _hash(intent, salt)

    assert tx_execution_succeeded(c.commit(args=[h]).transact())
    assert c.count().call() == 1

    assert tx_execution_succeeded(c.open_reveal_phase().transact())
    assert c.phase_now().call() == "REVEAL"

    receipt = c.reveal(args=[intent, salt, "I vote yes on proposal 7."]).transact()
    assert tx_execution_succeeded(receipt)
    assert c.reveal_count().call() == 1

    rec = json.loads(c.get_reveal(args=[0]).call())
    assert rec["accepted"] is True
    assert rec["statement"] == "I vote yes on proposal 7."


def test_reveal_with_wrong_salt_reverts():
    c = _deploy()
    intent = "I bid 500 tokens for item X"
    salt = "correct-salt"
    h = _hash(intent, salt)
    c.commit(args=[h]).transact()
    c.open_reveal_phase().transact()

    receipt = c.reveal(args=[intent, "wrong-salt", "I bid 500 tokens for item X"]).transact()
    assert not tx_execution_succeeded(receipt)


def test_reveal_before_phase_open_reverts():
    c = _deploy()
    intent = "I predict rain tomorrow"
    salt = "s1"
    h = _hash(intent, salt)
    c.commit(args=[h]).transact()

    # Reveal phase never opened.
    receipt = c.reveal(args=[intent, salt, "I predict rain tomorrow"]).transact()
    assert not tx_execution_succeeded(receipt)


def test_commit_after_reveal_phase_opened_reverts():
    c = _deploy()
    c.open_reveal_phase().transact()
    receipt = c.commit(args=[_hash("x", "y")]).transact()
    assert not tx_execution_succeeded(receipt)


def test_double_reveal_reverts():
    c = _deploy()
    intent = "I support the merger"
    salt = "z9"
    h = _hash(intent, salt)
    c.commit(args=[h]).transact()
    c.open_reveal_phase().transact()

    assert tx_execution_succeeded(
        c.reveal(args=[intent, salt, "I support the proposed merger."]).transact()
    )
    receipt = c.reveal(args=[intent, salt, "I support the proposed merger."]).transact()
    assert not tx_execution_succeeded(receipt)


def test_reveal_without_commit_reverts():
    c = _deploy()
    c.open_reveal_phase().transact()
    receipt = c.reveal(args=["intent", "salt", "statement"]).transact()
    assert not tx_execution_succeeded(receipt)


def test_invalid_hash_format_reverts():
    c = _deploy()
    receipt = c.commit(args=["not-a-valid-sha256-hash"]).transact()
    assert not tx_execution_succeeded(receipt)


def test_double_commit_reverts():
    c = _deploy()
    h1 = _hash("a", "b")
    h2 = _hash("c", "d")
    assert tx_execution_succeeded(c.commit(args=[h1]).transact())
    receipt = c.commit(args=[h2]).transact()
    assert not tx_execution_succeeded(receipt)


def test_commit_of_and_has_revealed_lookup():
    c = _deploy()
    committer = create_account()
    intent = "I approve the budget"
    salt = "salty"
    h = _hash(intent, salt)

    assert tx_execution_succeeded(c.connect(account=committer).commit(args=[h]).transact())
    assert c.has_revealed(args=[committer.address]).call() is False

    commit_rec = json.loads(c.commit_of(args=[committer.address]).call())
    assert commit_rec["hash"] == h

    c.open_reveal_phase().transact()
    assert tx_execution_succeeded(
        c.connect(account=committer)
        .reveal(args=[intent, salt, "I approve the proposed budget."])
        .transact()
    )

    assert c.has_revealed(args=[committer.address]).call() is True
    reveal_rec = json.loads(c.reveal_of(args=[committer.address]).call())
    assert reveal_rec["accepted"] is True
