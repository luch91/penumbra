# { "Depends": "py-genlayer:5jycge4q8k23462jtb0b9fyey1s9q928sz2nbrd9mg4sxqg2qng" }
"""
PENUMBRA -- II. ASYMMETRIC RITES -- 03

ProofCarryingAnswer -- submit a claim together with the reasoning that backs it.
The network attests the claim only if the proof actually holds. Producing the
proof is hard; checking it is cheap. This contract is the cheap half.

WHY IT IS UNUSUAL
  Most "AI decides X" contracts make every validator redo the full reasoning,
  which is slow, costly, and noisy. This contract refuses to do that. It uses
  the NON-COMPARATIVE equivalence principle, the one principle where the leader
  does the work and the validators ONLY verify integrity. The claim and its
  proof are passed in as plain arguments, so every node sees the identical
  input -- there is nothing to disagree about except whether the proof is sound.
  That turns the contract into a trustless verifier for any domain where
  "answer + justification" can be checked more easily than it can be produced:
  the on-chain analogue of a proof-carrying computation.

HOW CONSENSUS IS USED
  The non-deterministic block returns the verification INPUT (claim + proof).
  The principle's `task` instructs the leader to verify the proof and emit a
  structured verdict; the `criteria` tell validators exactly what makes a
  verdict trustworthy (every step must follow, the conclusion must match the
  claim, no gaps). Validators never re-derive the proof -- they audit it. If the
  leader's verdict lacks integrity under the criteria, validators vote it down
  and the attestation never lands.

STATE DESIGN
  A content-addressed attestation book. Each accepted claim is appended with
  its proof digest and the verdict, building an on-chain ledger of things the
  network has checked and stands behind. Rejected claims revert and leave no
  trace, so the book contains only attested truth.

REUSE
  Eligibility proofs ("this address qualifies for the airdrop because ..."),
  compliance proofs, math/logic lemmas, derivation of a number from a dataset.
  Pair it with an off-chain solver that races to produce proofs.
"""

from genlayer import *
import json
import hashlib
from dataclasses import dataclass

# -- PENUMBRA helpers ----------------------------------------------------------
try:
    _PenumbraError = gl.vm.UserError
except Exception:
    _PenumbraError = Exception


def require(condition: bool, message: str) -> None:
    if not condition:
        raise _PenumbraError(message)
# ------------------------------------------------------------------------------


@allow_storage
@dataclass
class Attestation:
    claim: str
    proof_digest: str
    submitter: Address
    confidence_milli: u256


class ProofCarryingAnswer(gl.Contract):
    domain: str                          # what kind of claims this book attests
    attestations: DynArray[Attestation]
    seen: TreeMap[str, u256]             # claim_digest -> 1 + index, for dedupe

    def __init__(self, domain: str = "general"):
        self.domain = domain

    @gl.public.write
    def attest(self, claim: str, proof: str) -> bool:
        require(len(claim.strip()) > 0, "empty claim")
        require(len(proof.strip()) > 0, "a claim needs a proof")

        claim_digest = hashlib.sha256(claim.strip().encode()).hexdigest()
        require(int(self.seen.get(claim_digest, u256(0))) == 0, "claim already attested")

        domain = self.domain
        c = claim
        p = proof

        def verification_input() -> str:
            # The input is fully deterministic: identical on leader and every
            # validator. We return it verbatim; the principle does the judging.
            return json.dumps({"domain": domain, "claim": c, "proof": p}, sort_keys=True)

        task = (
            "You are a rigorous verifier. The input JSON has a 'claim' and a 'proof'. "
            "Check whether the proof actually establishes the claim within the given "
            "domain. Do NOT invent missing steps. Output ONLY strict JSON: "
            '{"valid": <true|false>, "confidence": <float 0..1>, "flaw": "<empty if valid, else the first broken step>"}.'
        )
        criteria = (
            "A trustworthy verdict has these properties: (1) 'valid' is true ONLY when "
            "every step of the proof follows from the previous ones or from stated facts, "
            "and the final step entails the claim; (2) if any step is unsupported, circular, "
            "or the conclusion does not match the claim, 'valid' must be false with a 'flaw' "
            "naming the first failure; (3) 'confidence' reflects how airtight the proof is. "
            "Reject the verdict if it asserts validity while leaving a gap unaddressed."
        )

        raw = gl.eq_principle.prompt_non_comparative(
            verification_input, task=task, criteria=criteria
        )
        verdict = json.loads(raw) if isinstance(raw, str) else raw
        valid = bool(verdict["valid"])
        confidence = max(0.0, min(1.0, float(verdict.get("confidence", 0.0))))

        if not valid:
            # Nothing is written. The book holds only attested truth.
            return False

        proof_digest = hashlib.sha256(proof.strip().encode()).hexdigest()
        att = Attestation(
            claim=claim,
            proof_digest=proof_digest,
            submitter=gl.message.sender_address,
            confidence_milli=u256(int(round(confidence * 1000))),
        )
        self.attestations.append(att)
        self.seen[claim_digest] = u256(len(self.attestations))  # 1-based marker
        return True

    # -- reads --------------------------------------------------------------------
    @gl.public.view
    def count(self) -> int:
        return len(self.attestations)

    @gl.public.view
    def is_attested(self, claim: str) -> bool:
        digest = hashlib.sha256(claim.strip().encode()).hexdigest()
        return int(self.seen.get(digest, u256(0))) > 0

    @gl.public.view
    def get(self, index: int) -> str:
        require(0 <= index < len(self.attestations), "no such attestation")
        a = self.attestations[index]
        return json.dumps(
            {
                "claim": a.claim,
                "proof_digest": a.proof_digest,
                "submitter": a.submitter.as_hex,
                "confidence_milli": int(a.confidence_milli),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
