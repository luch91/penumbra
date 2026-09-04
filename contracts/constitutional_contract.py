# { "Depends": "py-genlayer:5jycge4q8k23462jtb0b9fyey1s9q928sz2nbrd9mg4sxqg2qng" }
"""
PENUMBRA -- III. SEMANTIC MACHINES -- 08

ConstitutionalContract -- a rulebook in prose whose amendments must stay
consistent with a fixed set of immutable core principles. Anyone can
propose an amendment; consensus decides whether it survives contact with
the constitution's own core, not any human gatekeeper.

WHY IT IS UNUSUAL
  Most on-chain governance either hardcodes rules in code (rigid, requires a
  redeploy to change) or defers entirely to a vote (majority can rewrite
  anything, including principles meant to be foundational). This primitive
  splits the difference: `core` is a small set of principles fixed forever
  at deploy time -- no vote, no owner call, nothing can touch it -- while
  `body` is a living, amendable document that grows only by amendments the
  network itself judges consistent with that fixed core. It is a
  constitution in the literal sense: a document that can evolve, bounded by
  clauses that cannot.

HOW CONSENSUS IS USED
  `core` (already-agreed chain state, immutable) and the proposed amendment
  `text` (fresh calldata) are both deterministic and identical on every
  validator. This is the same shape as IntentLock's `request()` --
  compliance against a fixed rule set is a mechanical, criteria-checkable
  judgment, not the kind of genuinely interpretive call SemanticDiffLedger's
  materiality check is. So this uses the NON_COMPARATIVE equivalence
  principle: the leader decides whether the amendment conflicts with any
  core principle, and validators verify that ruling against explicit
  criteria rather than independently re-deriving it. The default posture is
  conservative, mirroring IntentLock's default-deny: an amendment is
  accepted only if it plainly does not contradict any core principle;
  ambiguity is a rejection, not a coin flip.

  Every proposal is logged -- accepted or rejected -- as a governance audit
  trail (see STATE DESIGN). Only accepted amendments are appended to `body`;
  a rejected proposal changes nothing.

DEVIATIONS FROM THE LITERAL CATALOG SPEC
  The spec's State line names `core: DynArray[str]` directly, implying the
  constructor takes a list of principles. No contract in this repo has ever
  exercised a list-typed calldata argument (see AmbiguityGuard's docstring
  for the same finding) -- `AmbiguityGuard.judge()`'s `options` parameter
  established the proven workaround of accepting a single delimited `str`
  and splitting it internally. This contract reuses that exact pattern for
  `core_principles`, delimited by `|` (principles are full sentences that
  may contain commas, so a comma delimiter -- AmbiguityGuard's choice --
  would be ambiguous here; `|` is not expected to appear in ordinary prose).

STATE DESIGN
  `core` is populated once in the constructor and never written to again by
  any method -- there is no owner-gated "update core" call at all, which is
  the actual mechanism of immutability (not just documentation). `body`
  starts as the deployer's initial text and grows by one appended,
  numbered clause per accepted amendment. `amendments` is the proven
  append-only `DynArray[Amendment]` audit-trail pattern (same shape as
  IntentLock's `grants`): every proposal is recorded with its outcome,
  accepted or not.

REUSE
  DAO charters, protocol policy documents, or agent operating agreements:
  lock the non-negotiable principles in at deploy time, then let the
  network itself gate every proposed addition against them.
"""

from genlayer import *
import json
from dataclasses import dataclass

# -- PENUMBRA helpers (copied; see lib/penumbra_consensus.py) ------------------
try:
    _PenumbraError = gl.vm.UserError
except Exception:
    _PenumbraError = Exception


def require(condition: bool, message: str) -> None:
    if not condition:
        raise _PenumbraError(message)


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))
# ------------------------------------------------------------------------------


@allow_storage
@dataclass
class Amendment:
    proposer: Address
    text: str
    accepted: bool


class ConstitutionalContract(gl.Contract):
    core: DynArray[str]
    body: str
    amendments: DynArray[Amendment]

    def __init__(self, core_principles: str, initial_body: str = ""):
        cp = core_principles if isinstance(core_principles, str) else ""
        principles = [p.strip() for p in cp.split("|") if p.strip()]
        require(len(principles) >= 1, "at least one core principle required")
        for p in principles:
            self.core.append(p)
        self.body = (initial_body if isinstance(initial_body, str) else "").strip()

    @gl.public.write
    def propose_amendment(self, text: str) -> bool:
        t = (text if isinstance(text, str) else "").strip()
        require(len(t) > 0, "empty amendment text")

        core_list = [str(self.core[i]) for i in range(len(self.core))]

        def verification_input() -> str:
            # Fully deterministic: identical on the leader and every validator,
            # since the core principles are already-agreed chain state and the
            # amendment is plain calldata, not fresh model output.
            return canonical({"core_principles": core_list, "proposed_amendment": t})

        task = (
            "You are reviewing a PROPOSED_AMENDMENT against a fixed list of "
            "CORE_PRINCIPLES for a governance document. Decide whether the "
            "amendment may be adopted -- it must not contradict, weaken, or "
            "carve an exception into any CORE_PRINCIPLE. Output ONLY strict "
            'JSON: {"accepted": <true|false>, "reason": "<<=20 words>"}.'
        )
        criteria = (
            "A trustworthy verdict has these properties: (1) 'accepted' is true "
            "ONLY if the amendment is plainly consistent with EVERY core "
            "principle -- default to false on any ambiguity, partial conflict, "
            "or an amendment that merely doesn't mention a principle (silence "
            "is not consistency if the amendment's effect would still "
            "contradict it); (2) an amendment that conflicts with even one "
            "core principle must be rejected, regardless of how reasonable it "
            "seems otherwise; (3) an amendment that is fully consistent with "
            "every principle, even if novel, must not be rejected merely for "
            "being new. Reject a verdict that accepts an amendment while a "
            "conflict with a stated principle is left unaddressed."
        )
        raw = gl.eq_principle.prompt_non_comparative(verification_input, task=task, criteria=criteria)
        verdict = json.loads(raw) if isinstance(raw, str) else raw
        accepted = bool(verdict["accepted"])

        self.amendments.append(
            Amendment(proposer=gl.message.sender_address, text=t, accepted=accepted)
        )

        if accepted:
            number = len(self.amendments)
            clause = f"Amendment {number}: {t}"
            self.body = (self.body + "\n\n" + clause) if len(self.body) > 0 else clause

        return accepted

    # -- reads ------------------------------------------------------------------
    @gl.public.view
    def read_constitution(self) -> str:
        core_list = [str(self.core[i]) for i in range(len(self.core))]
        return canonical({"core_principles": core_list, "body": self.body})

    @gl.public.view
    def core_count(self) -> int:
        return len(self.core)

    @gl.public.view
    def get_core(self, index: int) -> str:
        require(0 <= index < len(self.core), "no such core principle")
        return str(self.core[index])

    @gl.public.view
    def count(self) -> int:
        return len(self.amendments)

    @gl.public.view
    def get_amendment(self, index: int) -> str:
        require(0 <= index < len(self.amendments), "no such amendment")
        a = self.amendments[index]
        return canonical({"proposer": a.proposer.as_hex, "text": a.text, "accepted": a.accepted})
