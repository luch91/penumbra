# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""
Test fixture only -- NOT one of the 20 catalog primitives.

A minimal stand-in callback target used by tests/test_canary_tripwire.py to
pin the cross-contract WRITE shape CanaryTripwire depends on
(gl.get_contract_at(addr).emit().on_trip(condition) firing without a typed
return value). Records every call it receives so a test can confirm the
callback actually landed, not just that poll() reported tripped=true.
"""

from genlayer import *
import json


class TripwireCallbackStub(gl.Contract):
    trip_count: u256
    last_condition: str

    def __init__(self):
        self.trip_count = u256(0)
        self.last_condition = ""

    @gl.public.write
    def on_trip(self, condition: str) -> None:
        self.trip_count = u256(int(self.trip_count) + 1)
        self.last_condition = condition if isinstance(condition, str) else ""

    @gl.public.view
    def status(self) -> str:
        return json.dumps(
            {"trip_count": int(self.trip_count), "last_condition": self.last_condition},
            sort_keys=True,
            separators=(",", ":"),
        )
