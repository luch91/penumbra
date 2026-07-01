# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
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
