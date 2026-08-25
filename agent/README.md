# PenumbraGate agent

This directory contains the off-chain intake agent for `PenumbraGate`.

The agent performs cheap deterministic checks before a paid contract call:

1. It scans the candidate for ASCII safety, Python syntax, a pinned runner,
   forbidden public return types, structural documentation, real payout
   transfers, and unscoped web targets.
2. It reads the exact non-negotiables rubric from a caller-supplied external
   file. The two handoff documents are deliberately not repository files.
3. It passes source and summary as separate calldata values. They are data,
   never interpolated into an instruction string.
4. It submits through GenLayerPY and waits for `FINALIZED`.
5. It inspects the finalized receipt and records an observed appeal through
   `mark_appealed` when the receipt shows a later round or larger validator set.

The agent never holds stake, makes the verdict, or merges a pull request.

## Verification items

1. Minimum gas for appealability: the public APIs expose appeal transactions,
   appeal bonds, and additional appeal funding, but no developer-side setter.
   This is resolved by design: PenumbraGate does not release a verdict or
   merge anything before FINALIZED, and the contract has no appeal-dependent
   payout. A caller may add appeal funding during the finality window.
2. State replacement across appeal rounds: a live Studionet counter probe
   showed accumulation, not replacement. PenumbraGate therefore fingerprints
   the sender, submission data, value, and stable raw message timestamp. A
   matching appeal re-execution returns the recorded verdict without appending
   a second record or crediting the refund twice.
3. In-contract appeal metadata: the current transaction context documents no
   appeal round or validator-set accessor. This is resolved by design. The
   agent reads the finalized receipt and alone writes the audit flag.
4. Criteria length: no public ceiling was found. A live deployment stored two
   synthetic criteria values with the exact external-rubric part lengths,
   5,773 and 4,834 characters. The agent preserves the full rubric and splits
   it at the Tier B boundary. The contract runs both parts with
   non-comparative consensus and never silently truncates the source text.

The GenLayerPY receipt and finality calls follow the official SDK reference.
