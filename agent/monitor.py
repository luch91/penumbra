"""Finality and appeal monitoring for PenumbraGate submissions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent.review_agent import mark_appealed_if_needed, wait_for_finalized


@dataclass(frozen=True)
class FinalizedSubmission:
    transaction_hash: str
    receipt: Any
    appeal_recorded: bool


def monitor_submission(
    client: Any,
    transaction_hash: str,
    contract_address: str,
    submission_id: int,
    default_validator_count: int = 0,
) -> FinalizedSubmission:
    """Wait for finality and record an observed native appeal if required."""
    receipt = wait_for_finalized(client, transaction_hash)
    appeal_receipt = mark_appealed_if_needed(
        client,
        contract_address,
        submission_id,
        receipt,
        default_validator_count,
    )
    return FinalizedSubmission(
        transaction_hash=transaction_hash,
        receipt=receipt,
        appeal_recorded=appeal_receipt is not None,
    )
