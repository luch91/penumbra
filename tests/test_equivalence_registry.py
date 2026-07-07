"""
Tests for EquivalenceRegistry.

    gltest --network studionet tests/test_equivalence_registry.py

EquivalenceRegistry runs NO non-deterministic block -- it is pure,
deterministic state CRUD whose whole purpose is to be read by other
contracts. So unlike every other suite in this repo, none of these tests
touch LLM output at all; they pin the deterministic guarantees:
register-once, author-only bump, monotonic versioning, existence sentinel,
and the exact round-trip of the stored principle text.
"""

import json

from gltest import get_contract_factory, create_account
from gltest.assertions import tx_execution_succeeded


_NAME = "materially_different"
_TEXT = (
    "Two texts are materially different if they change the meaning, "
    "obligations, or outcome a reader would act on -- not merely wording, "
    "formatting, or spelling."
)
_TEXT_V2 = (
    "Two texts are materially different if they alter meaning, obligations, "
    "or the outcome a reader would act on. Pure wording, formatting, or "
    "spelling changes are cosmetic."
)


def _deploy():
    factory = get_contract_factory("EquivalenceRegistry")
    return factory.deploy(args=[])


def test_deploys_empty():
    c = _deploy()
    assert c.exists(args=["anything"]).call() is False
    assert c.version_of(args=["anything"]).call() == 0


def test_register_stores_and_round_trips_text():
    c = _deploy()
    receipt = c.register(args=[_NAME, _TEXT]).transact()
    assert tx_execution_succeeded(receipt)

    assert c.exists(args=[_NAME]).call() is True
    assert c.version_of(args=[_NAME]).call() == 1
    # The registry's core promise: the text comes back byte-for-byte, because
    # other contracts feed it straight into their own equivalence principle.
    assert c.get(args=[_NAME]).call() == _TEXT


def test_get_full_reports_name_text_author_and_version():
    c = _deploy()
    assert tx_execution_succeeded(c.register(args=[_NAME, _TEXT]).transact())
    full = json.loads(c.get_full(args=[_NAME]).call())
    assert full["name"] == _NAME
    assert full["text"] == _TEXT
    assert full["version"] == 1
    assert full["author"].startswith("0x")


def test_duplicate_register_reverts():
    c = _deploy()
    assert tx_execution_succeeded(c.register(args=[_NAME, _TEXT]).transact())
    # Registering the same name again must revert -- bump is the only way to
    # change an existing principle.
    receipt = c.register(args=[_NAME, "some other text"]).transact()
    assert not tx_execution_succeeded(receipt)
    # State must be untouched by the failed register.
    assert c.version_of(args=[_NAME]).call() == 1
    assert c.get(args=[_NAME]).call() == _TEXT


def test_author_can_bump_and_version_increments():
    c = _deploy()
    assert tx_execution_succeeded(c.register(args=[_NAME, _TEXT]).transact())
    receipt = c.bump(args=[_NAME, _TEXT_V2]).transact()
    assert tx_execution_succeeded(receipt)

    assert c.version_of(args=[_NAME]).call() == 2
    assert c.get(args=[_NAME]).call() == _TEXT_V2


def test_non_author_cannot_bump():
    c = _deploy()
    # Registered by the default account.
    assert tx_execution_succeeded(c.register(args=[_NAME, _TEXT]).transact())

    stranger = create_account()
    receipt = c.connect(account=stranger).bump(args=[_NAME, "hostile rewrite"]).transact()
    assert not tx_execution_succeeded(receipt)
    # The author-only gate must have preserved both version and text.
    assert c.version_of(args=[_NAME]).call() == 1
    assert c.get(args=[_NAME]).call() == _TEXT


def test_bump_unregistered_name_reverts():
    c = _deploy()
    receipt = c.bump(args=["never_registered", "text"]).transact()
    assert not tx_execution_succeeded(receipt)
    assert c.exists(args=["never_registered"]).call() is False


def test_register_empty_name_or_text_reverts():
    c = _deploy()
    assert not tx_execution_succeeded(c.register(args=["   ", _TEXT]).transact())
    assert not tx_execution_succeeded(c.register(args=["valid_name", "   "]).transact())
    assert c.exists(args=["valid_name"]).call() is False


def test_get_unregistered_name_reverts():
    c = _deploy()
    try:
        c.get(args=["missing"]).call()
        assert False, "expected get() on a missing principle to revert"
    except Exception:
        pass


def test_independent_principles_coexist():
    c = _deploy()
    assert tx_execution_succeeded(c.register(args=["a", "alpha text"]).transact())
    assert tx_execution_succeeded(c.register(args=["b", "beta text"]).transact())
    assert c.get(args=["a"]).call() == "alpha text"
    assert c.get(args=["b"]).call() == "beta text"
    assert c.version_of(args=["a"]).call() == 1
    assert c.version_of(args=["b"]).call() == 1
