"""Unit tests for finalized transaction monitoring."""

from agent.monitor import monitor_submission


class FakeClient:
    def __init__(self):
        self.mark_calls = []

    def wait_for_transaction_receipt(self, **kwargs):
        return {"last_round": {"round": "0", "round_validators": ["a"]}}


def test_monitor_waits_for_finality_without_marking_first_round():
    client = FakeClient()
    result = monitor_submission(client, "0xabc", "0xcontract", 0, 1)
    assert result.transaction_hash == "0xabc"
    assert result.appeal_recorded is False
    assert client.mark_calls == []
