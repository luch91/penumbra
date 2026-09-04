# { "Depends": "py-genlayer:5jycge4q8k23462jtb0b9fyey1s9q928sz2nbrd9mg4sxqg2qng" }
"""
Test fixture only -- NOT one of the 20 catalog primitives.

A minimal stand-in target contract used solely by
tests/test_mirror_audit_read.py to pin the cross-contract read shape
MirrorAudit depends on (gl.get_contract_at(addr).view().status() returning a
value directly). Exists so a cross-contract regression fails fast and
specifically, instead of hiding inside a slower LLM-judgment test.
"""

from genlayer import *
import json


class AuditStubTarget(gl.Contract):
    label: str

    def __init__(self, label: str = "fixture"):
        self.label = label

    @gl.public.view
    def status(self) -> str:
        return json.dumps({"label": self.label}, sort_keys=True, separators=(",", ":"))
