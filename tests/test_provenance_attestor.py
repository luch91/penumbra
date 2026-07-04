"""
Tests for ProvenanceAttestor.

    gltest --network studionet tests/test_provenance_attestor.py

ProvenanceAttestor's guarantee is that every attest() call is recorded,
whether or not the source turns out to support the claim -- an audit trail,
not a filter. Assertions pin that shape and the deterministic input-validation
gate, never the exact span wording an LLM extracts from a page.
"""

import json

from gltest import get_contract_factory
from gltest.assertions import tx_execution_succeeded

# A stable, static reference page that live smoke-testing on studionet
# reproduced supports=true for, with a real extracted span quoting the
# boiling point. Live-verified twice (CLI smoke test + this suite).
_CLAIM = "Water boils at 100 degrees Celsius at sea level"
_URL = "https://en.wikipedia.org/wiki/Boiling_point"

# A deliberately unreachable URL -- exercises the try/except fetch-failure
# guard (proven in SemanticDeadman, reused here), which must resolve
# cleanly to supports=false rather than aborting the transaction.
_DEAD_URL = "https://this-domain-absolutely-does-not-exist-penumbra-test-99999.invalid"


def _deploy():
    factory = get_contract_factory("ProvenanceAttestor")
    return factory.deploy(args=[])


def test_deploys_empty():
    c = _deploy()
    assert c.count().call() == 0


def test_supporting_source_is_attested_and_archived():
    c = _deploy()
    receipt = c.attest(args=[_CLAIM, _URL]).transact()
    assert tx_execution_succeeded(receipt)

    assert c.count().call() == 1
    rec = json.loads(c.get(args=[0]).call())
    assert rec["claim"] == _CLAIM
    assert rec["url"] == _URL
    assert rec["supports"] is True
    assert len(rec["span"]) > 0
    assert len(rec["span_hash"]) == 64  # sha256 hex digest

    latest = json.loads(c.latest_attestation().call())
    assert latest == rec


def test_unreachable_source_resolves_to_not_supporting_without_reverting():
    # The fetch-failure guard must resolve the write cleanly (supports=false),
    # not abort the transaction -- an unreachable source is itself a valid,
    # recordable outcome, not an error state.
    c = _deploy()
    receipt = c.attest(args=["The moon is made of cheese", _DEAD_URL]).transact()
    assert tx_execution_succeeded(receipt)

    assert c.count().call() == 1
    rec = json.loads(c.get(args=[0]).call())
    assert rec["supports"] is False
    assert rec["span"] == ""
    assert rec["span_hash"] == ""


def test_archive_grows_and_is_indexable():
    c = _deploy()
    assert tx_execution_succeeded(c.attest(args=[_CLAIM, _URL]).transact())
    assert tx_execution_succeeded(
        c.attest(args=["The moon is made of cheese", _DEAD_URL]).transact()
    )
    assert c.count().call() == 2

    first = json.loads(c.get(args=[0]).call())
    second = json.loads(c.get(args=[1]).call())
    assert first["supports"] is True
    assert second["supports"] is False


def test_empty_claim_reverts():
    c = _deploy()
    receipt = c.attest(args=["   ", _URL]).transact()
    assert not tx_execution_succeeded(receipt)
    assert c.count().call() == 0


def test_empty_url_reverts():
    c = _deploy()
    receipt = c.attest(args=[_CLAIM, "   "]).transact()
    assert not tx_execution_succeeded(receipt)
    assert c.count().call() == 0
