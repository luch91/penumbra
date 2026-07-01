"""
Tests for MirrorAudit.

    gltest --network studionet tests/test_mirror_audit.py

MirrorAudit's core novelty is the cross-contract read, which is deterministic
(pinned separately and fast in test_mirror_audit_read.py). These tests assert
the ledger's structural guarantees plus two clear-cut conformance judgments —
a spec that is transparently true of the target's real reported state, and one
that transparently contradicts it — never a borderline LLM opinion.
"""

import json

from gltest import get_contract_factory
from gltest.assertions import tx_execution_succeeded


def _deploy_stub(label):
    return get_contract_factory("AuditStubTarget").deploy(args=[label])


def _deploy_auditor():
    return get_contract_factory("MirrorAudit").deploy()


def test_deploys_empty():
    auditor = _deploy_auditor()
    assert auditor.count().call() == 0


def test_audit_requires_nonempty_spec():
    auditor = _deploy_auditor()
    stub = _deploy_stub("anything")
    receipt = auditor.audit(args=[stub.address, ""]).transact()
    assert not tx_execution_succeeded(receipt)


def test_true_claim_conforms():
    auditor = _deploy_auditor()
    stub = _deploy_stub("northern-lights")
    receipt = auditor.audit(
        args=[stub.address, "The target's reported label must be exactly 'northern-lights'."]
    ).transact()
    assert tx_execution_succeeded(receipt)
    assert auditor.count().call() == 1

    record = json.loads(auditor.get(args=[0]).call())
    assert record["target"].lower() == stub.address.lower()
    assert record["conforms"] is True


def test_false_claim_does_not_conform():
    auditor = _deploy_auditor()
    stub = _deploy_stub("northern-lights")
    receipt = auditor.audit(
        args=[stub.address, "The target's reported label must be exactly 'southern-lights'."]
    ).transact()
    assert tx_execution_succeeded(receipt)

    record = json.loads(auditor.get(args=[0]).call())
    assert record["conforms"] is False


def test_history_filters_by_target():
    auditor = _deploy_auditor()
    stub_a = _deploy_stub("alpha")
    stub_b = _deploy_stub("beta")

    assert tx_execution_succeeded(
        auditor.audit(args=[stub_a.address, "Label must be exactly 'alpha'."]).transact()
    )
    assert tx_execution_succeeded(
        auditor.audit(args=[stub_b.address, "Label must be exactly 'beta'."]).transact()
    )
    assert auditor.count().call() == 2

    history_a = json.loads(auditor.history(args=[stub_a.address]).call())
    assert len(history_a["audits"]) == 1
    assert history_a["audits"][0]["conforms"] is True

    history_b = json.loads(auditor.history(args=[stub_b.address]).call())
    assert len(history_b["audits"]) == 1
