"""
Tests for CanaryTripwire.

    gltest --network studionet tests/test_canary_tripwire.py

CanaryTripwire's guarantee is that `tripped` only ever flips when consensus
independently agrees the watched condition is met, and that a genuine trip
fires the callback exactly once. This suite deploys a real
TripwireCallbackStub fixture (never a synthetic address) as the callback
target for every test that arms the switch, per CLAUDE.md's documented risk
that `gl.get_contract_at` on an address with no deployed code can hang
rather than revert -- a real, live-deployed contract sidesteps that risk
entirely. Assertions pin the deterministic guards and the cross-contract
delivery shape, never the exact wording an LLM uses to judge the condition.
"""

import json
import time

from gltest import get_contract_factory
from gltest.assertions import tx_execution_succeeded


def _wait_for_trip_count(stub, expected, timeout_s=60, interval_s=3):
    # Cross-contract WRITE messages (the `messages` array on a receipt) are
    # queued by the initiating transaction but delivered asynchronously --
    # confirmed live (see DECISIONS.md, 2026-07-04): a CLI poll() reached
    # ACCEPTED/FINALIZED immediately, but the target contract's state only
    # reflected the callback a short while later. `tx_execution_succeeded`
    # on the initiating tx does NOT guarantee the downstream message has
    # landed yet, so reads of the callback target must retry, not assume
    # synchronous delivery.
    deadline = time.time() + timeout_s
    status = json.loads(stub.status().call())
    while status["trip_count"] != expected and time.time() < deadline:
        time.sleep(interval_s)
        status = json.loads(stub.status().call())
    return status

# A stable, static reference page already live-verified in this session
# (CorroborationOracle, ProvenanceAttestor) for reproducible judgments.
_URL = "https://en.wikipedia.org/wiki/Boiling_point"

# Clearly true / false conditions against that page.
_TRUE_CONDITION = "the page mentions the word water"
_FALSE_CONDITION = "the page prominently discusses cryptocurrency prices"


def _deploy_stub():
    return get_contract_factory("TripwireCallbackStub").deploy(args=[])


def _deploy_tripwire(url=_URL):
    return get_contract_factory("CanaryTripwire").deploy(args=[url])


def test_deploys_unarmed():
    c = _deploy_tripwire()
    status = json.loads(c.status().call())
    assert status["armed"] is False
    assert status["tripped"] is False


def test_poll_before_armed_reverts():
    c = _deploy_tripwire()
    receipt = c.poll().transact()
    assert not tx_execution_succeeded(receipt)


def test_arm_requires_condition_and_callback():
    c = _deploy_tripwire()
    stub = _deploy_stub()
    assert not tx_execution_succeeded(c.arm(args=["   ", stub.address]).transact())

    zero = "0x0000000000000000000000000000000000000000"
    assert not tx_execution_succeeded(
        c.arm(args=[_TRUE_CONDITION, zero]).transact()
    )


def test_false_condition_does_not_trip():
    c = _deploy_tripwire()
    stub = _deploy_stub()
    assert tx_execution_succeeded(c.arm(args=[_FALSE_CONDITION, stub.address]).transact())

    receipt = c.poll().transact()
    assert tx_execution_succeeded(receipt)

    status = json.loads(c.status().call())
    assert status["tripped"] is False
    # No trip means the callback must never have been exercised.
    stub_status = json.loads(stub.status().call())
    assert stub_status["trip_count"] == 0


def test_true_condition_trips_and_fires_callback():
    # This is the one path that exercises the cross-contract WRITE callback --
    # live-verified via CLI before this suite was written (see DECISIONS.md,
    # 2026-07-04): a genuine trip queues and delivers a message to the
    # callback contract's on_trip() method.
    c = _deploy_tripwire()
    stub = _deploy_stub()
    assert tx_execution_succeeded(c.arm(args=[_TRUE_CONDITION, stub.address]).transact())

    receipt = c.poll().transact()
    assert tx_execution_succeeded(receipt)

    status = json.loads(c.status().call())
    assert status["tripped"] is True

    stub_status = _wait_for_trip_count(stub, 1)
    assert stub_status["trip_count"] == 1
    assert stub_status["last_condition"] == _TRUE_CONDITION


def test_poll_after_tripped_is_idempotent():
    c = _deploy_tripwire()
    stub = _deploy_stub()
    c.arm(args=[_TRUE_CONDITION, stub.address]).transact()
    assert tx_execution_succeeded(c.poll().transact())
    _wait_for_trip_count(stub, 1)

    # Second poll must not re-fetch, re-judge, or re-fire the callback.
    receipt = c.poll().transact()
    assert tx_execution_succeeded(receipt)
    stub_status = json.loads(stub.status().call())
    assert stub_status["trip_count"] == 1


def test_cannot_rearm_after_tripped():
    c = _deploy_tripwire()
    stub = _deploy_stub()
    c.arm(args=[_TRUE_CONDITION, stub.address]).transact()
    c.poll().transact()

    receipt = c.arm(args=["a different condition", stub.address]).transact()
    assert not tx_execution_succeeded(receipt)
