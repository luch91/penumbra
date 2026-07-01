# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""
PENUMBRA -- VI. REFLEXION -- 16

MirrorAudit -- one contract audits another against a plain-language behavioral
spec, reading the target's own reported state via a contract-to-contract call.

WHY IT IS UNUSUAL
  Contracts here have judged claims, prompts, and web content. This one judges
  ANOTHER CONTRACT -- treating the consensus layer as an auditor that can point
  at any deployed address and ask "does this actually behave the way it's
  supposed to?" That is only possible because GenLayer contracts can read each
  other's state deterministically; MirrorAudit is the first primitive in this
  repo to actually exercise that surface.

HOW CONSENSUS IS USED
  The cross-contract read happens in the method body, NOT inside a
  non-deterministic block -- it is deterministic (every validator reads the
  same committed state off the same target address) and must never be treated
  as if it needed an equivalence principle of its own. Only the JUDGMENT of
  whether that state conforms to the spec is uncertain, so the fetched state +
  spec become the identical input to the NON-COMPARATIVE principle: the leader
  rules on conformance, and validators verify the ruling's integrity against
  stated criteria rather than re-deriving it. This is the correct move (not
  `comparative`) precisely because the input is byte-identical on every node --
  there is nothing to disagree about except whether the leader's reasoning
  holds, which is exactly what non-comparative is for.

  ASSUMPTION (stated per CLAUDE.md instructions, since CONTRACTS.md's spec
  leaves the shape of "the target's public state" open): MirrorAudit expects
  the target contract to expose a `status() -> str` view returning a
  JSON-canonicalized string of its own state -- the same convention every
  contract in this repo already follows (DissensusOracle.latest_verdict,
  JailbreakBounty.status, SemanticDeadman.status, etc.). This keeps MirrorAudit
  generic across any Penumbra-style contract without needing per-target
  method-name configuration, at the cost of not being able to audit arbitrary
  contracts that use a different read-method convention.

STATE DESIGN
  An append-only `DynArray[Audit]` ledger: target address, the boolean
  verdict, and a sha256 digest of the leader's rationale (the full rationale
  is returned transiently from `audit()` but not stored on-chain, mirroring
  ProofCarryingAnswer's proof_digest -- the digest lets anyone who saved the
  original response verify it wasn't altered, without paying storage for
  prose on every audit).

REUSE
  Registry admission gates ("only list vaults whose reported state conforms to
  policy X"), agent-to-agent trust ("does this agent contract still behave the
  way its spec promised"), continuous on-chain compliance monitoring.

## Runner verification
  CONFIRMED live (2026-07-01), via a throwaway isolation test (a stub target
  contract with `get_label() -> str` and `get_count() -> int`, probed by a
  second contract calling `gl.get_contract_at(addr).view().<method>()`):
  the untyped proxy returns the value DIRECTLY -- a plain `str`/`int`, not a
  wrapper object -- and a no-argument view call works exactly as the untyped
  proxy convention in CLAUDE.md describes. This is the first confirmation of
  the "single least-verified surface in the repo" (see CLAUDE.md "Known
  blockers"); full detail in DECISIONS.md, 2026-07-01 entry.

  What remains UNVERIFIED: cross-contract WRITE calls (`.emit()`) -- MirrorAudit
  only reads, so this contract does not exercise that half of the surface.
  ConsensusThermometer or a future contract must confirm `.emit()` separately
  before it's treated as safe.

  The cross-contract read is isolated in `_read_target_status`, tagged
  `# VERIFY:`, and wrapped in try/except -- but CONFIRMED live (2026-07-01) that
  this does NOT catch every failure mode, correcting an earlier assumption:
  auditing a target that does not implement `status()` at all does not
  surface as our clean custom message. It fails as an uncaught runner-level
  dispatch fault (`ValueError: call to private method
  <function Contract.__handle_undefined_method__...>`), raised while GenVM
  resolves the method against the TARGET's own execution context -- below the
  level our contract's Python exception handling can intercept, and in a
  different way than `gl.nondet.web.render`'s catchable `NondetException`.
  The outcome is still SAFE: every validator independently agrees the call
  errors, the transaction reverts cleanly, and no incorrect audit is ever
  recorded -- it just surfaces as a raw traceback instead of our message. The
  `try/except` is kept because it may still catch other failure modes (e.g.
  an application-level exception raised inside the target's own `status()`
  body), but do not rely on it for "target lacks the method entirely." Full
  reasoning in DECISIONS.md, 2026-07-01 entry.
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


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))
# ------------------------------------------------------------------------------


@allow_storage
@dataclass
class Audit:
    target: Address
    conforms: bool
    note_hash: str


class MirrorAudit(gl.Contract):
    audits: DynArray[Audit]

    def __init__(self):
        pass

    # -- the cross-contract read, isolated so a shape mismatch is one line to fix --
    def _read_target_status(self, target: Address) -> str:
        # VERIFY: untyped proxy -- confirmed live to return the value directly
        # (see "## Runner verification" in the module docstring). If a future
        # runner changes this shape, this is the only line that needs to change.
        try:
            other = gl.get_contract_at(target)
            state = other.view().status()
            return str(state)
        except Exception as e:
            raise _PenumbraError(
                f"could not read target's status() -- target may not implement "
                f"it, or the cross-contract view() shape differs from what's "
                f"assumed here (see 'Runner verification' in the docstring): {e}"
            )

    # -- the audit ------------------------------------------------------------
    @gl.public.write
    def audit(self, target: Address, spec: str) -> bool:
        t = target if isinstance(target, Address) else Address(target)
        require(len(spec.strip()) > 0, "spec required")

        # Deterministic cross-contract read -- every validator reads the same
        # committed state off the same address, so this is identical input on
        # every node. It must happen here, never inside a nondet block.
        state = self._read_target_status(t)
        target_hex = t.as_hex

        def verification_input() -> str:
            # Fully deterministic: identical on leader and every validator.
            return canonical({"target": target_hex, "spec": spec, "state": state})

        task = (
            "You are auditing whether a target smart contract's own reported "
            "state conforms to a plain-language behavioral specification. The "
            "input JSON has 'target' (an address), 'spec' (the rule the target "
            "should uphold), and 'state' (the target's own status() output, a "
            "JSON string it reported about itself). Decide whether 'state' "
            "satisfies 'spec'. Output ONLY strict JSON: "
            '{"conforms": <true|false>, "note": "<one sentence citing the specific field(s) in state that support or violate spec>"}.'
        )
        criteria = (
            "A trustworthy verdict has these properties: (1) 'conforms' is true "
            "ONLY if every specific, checkable condition named in spec is "
            "actually satisfied by a field present in state; (2) if spec names "
            "a condition that state does not contain enough information to "
            "verify, 'conforms' must be false -- never assume a fact state "
            "doesn't state; (3) 'note' must name the specific field(s) in state "
            "the verdict rests on. Reject the verdict if it asserts conformance "
            "without pointing to supporting evidence actually present in state."
        )

        raw = gl.eq_principle.prompt_non_comparative(
            verification_input, task=task, criteria=criteria
        )
        verdict = json.loads(raw) if isinstance(raw, str) else raw
        conforms = bool(verdict["conforms"])
        note = str(verdict.get("note", ""))[:280]
        note_hash = hashlib.sha256(note.encode()).hexdigest()

        self.audits.append(Audit(target=t, conforms=conforms, note_hash=note_hash))
        return conforms

    # -- reads ----------------------------------------------------------------
    @gl.public.view
    def count(self) -> int:
        return len(self.audits)

    @gl.public.view
    def get(self, index: int) -> str:
        require(0 <= index < len(self.audits), "no such audit")
        a = self.audits[index]
        return canonical(
            {
                "target": a.target.as_hex,
                "conforms": a.conforms,
                "note_hash": a.note_hash,
            }
        )

    @gl.public.view
    def history(self, target: Address) -> str:
        t = target if isinstance(target, Address) else Address(target)
        n = len(self.audits)
        records = []
        for i in range(n):
            a = self.audits[i]
            if a.target == t:
                records.append(
                    {"conforms": a.conforms, "note_hash": a.note_hash}
                )
        return canonical({"target": t.as_hex, "audits": records})
