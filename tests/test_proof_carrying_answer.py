"""
Tests for ProofCarryingAnswer.

    gltest --network studionet tests/test_proof_carrying_answer.py

We assert the verifier's invariants: a sound proof gets attested and becomes
queryable; an unsound proof leaves no trace; duplicates are rejected. We avoid
hand-picking borderline proofs whose soundness even humans would debate.
"""

from gltest import get_contract_factory
from gltest.assertions import tx_execution_succeeded


def _deploy(domain="arithmetic"):
    factory = get_contract_factory("ProofCarryingAnswer")
    return factory.deploy(args=[domain])


def test_sound_proof_is_attested():
    c = _deploy()
    claim = "The sum of the first three positive integers is 6."
    proof = "1 + 2 = 3. 3 + 3 = 6. Therefore 1 + 2 + 3 = 6, which matches the claim."
    receipt = c.attest(args=[claim, proof]).transact()
    assert tx_execution_succeeded(receipt)
    assert c.is_attested(args=[claim]).call() is True
    assert c.count().call() == 1
    rec = c.get(args=[0]).call()
    assert rec["confidence_milli"] > 0


def test_unsound_proof_leaves_no_trace():
    c = _deploy()
    claim = "All prime numbers are odd."
    proof = "Most primes I can think of are odd, so all of them must be odd."
    receipt = c.attest(args=[claim, proof]).transact()
    # The transaction itself succeeds (it ran), but nothing is attested because
    # the proof is unsound (2 is an even prime). The book stays empty.
    assert tx_execution_succeeded(receipt)
    assert c.is_attested(args=[claim]).call() is False
    assert c.count().call() == 0


def test_duplicate_claim_rejected():
    c = _deploy()
    claim = "Ten is greater than five."
    proof = "10 - 5 = 5, and 5 > 0, so 10 > 5."
    assert tx_execution_succeeded(c.attest(args=[claim, proof]).transact())
    # Re-submitting the same claim must revert on the dedupe guard.
    second = c.attest(args=[claim, proof]).transact()
    assert not tx_execution_succeeded(second)


def test_empty_inputs_revert():
    c = _deploy()
    assert not tx_execution_succeeded(c.attest(args=["", "proof"]).transact())
    assert not tx_execution_succeeded(c.attest(args=["claim", ""]).transact())
