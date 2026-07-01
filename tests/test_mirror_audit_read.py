"""
Isolation test for MirrorAudit's cross-contract read.

    gltest --network studionet tests/test_mirror_audit_read.py

Cross-contract calls (gl.get_contract_at) are the single least-verified
surface in this repo (see CLAUDE.md "Known blockers") — this test exists so a
regression in that surface fails here, fast and specifically, instead of
hiding inside a slower LLM-conformance-judgment test in test_mirror_audit.py.
Uses contracts/fixtures/audit_stub_target.py, a 3-line stand-in target, not
one of the 20 catalog primitives.
"""

from gltest import get_contract_factory
from gltest.assertions import tx_execution_succeeded


def test_mirror_audit_can_read_stub_targets_status():
    stub = get_contract_factory("AuditStubTarget").deploy(args=["pinned-value"])
    auditor = get_contract_factory("MirrorAudit").deploy()

    receipt = auditor.audit(
        args=[stub.address, "The reported label must be exactly 'pinned-value'."]
    ).transact()
    assert tx_execution_succeeded(receipt)
    assert auditor.count().call() == 1
