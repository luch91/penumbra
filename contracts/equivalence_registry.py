# { "Depends": "py-genlayer:5jycge4q8k23462jtb0b9fyey1s9q928sz2nbrd9mg4sxqg2qng" }
"""
PENUMBRA -- VI. REFLEXION -- 17

EquivalenceRegistry -- named, reusable equivalence principles as first-class
on-chain objects that other contracts fetch and apply in their own
consensus calls.

WHY IT IS UNUSUAL
  Every other primitive in this repo runs at least one non-deterministic
  block -- an LLM call wrapped in an equivalence principle. This one runs
  NONE. Its entire job is deterministic state CRUD: register a named
  principle, let its own author revise it, and let anyone read it back.
  The interesting part of this primitive is not what it computes but what
  it is FOR -- it exists to be read by OTHER contracts via a cross-contract
  READ (`gl.get_contract_at(registry).view().get(name)`, confirmed live and
  safe by MirrorAudit and CanaryTripwire elsewhere in this repo), which then
  feed the returned text straight into their own `comparative` or
  `non_comparative` calls as the equivalence principle string. Composable
  consensus policy as infrastructure: many contracts sharing one audited,
  versioned definition of "these two things count as equivalent," instead
  of each hardcoding its own principle prose.

HOW CONSENSUS IS USED
  There is no equivalence principle applied WITHIN this contract at all --
  `register`/`bump`/reads are plain deterministic writes and views, matching
  CONTRACTS.md's own description ("strict_eq-trivial": if you forced an
  equivalence principle onto trivial deterministic state mutation, it would
  trivially agree, so there is no reason to pay for a nondet block here).
  The actual consensus USE happens downstream, in whichever contract fetches
  a principle from this registry and hands it to `gl.eq_principle.
  prompt_comparative(inner, fetched_principle_text)`.

STATE DESIGN
  `principles: TreeMap[str, Principle]` (text, author) holds the current
  text of each named principle. `versions: TreeMap[str, u256]` is a parallel
  existence/version index -- 0 means "never registered" -- kept separate
  from `principles` because `TreeMap.get(key, default)` needs a default of
  the SAME type as the map's value type to be safe on this runner, and a
  scalar `u256(0)` sentinel is the proven-safe idiom already used elsewhere
  in this repo (ProofCarryingAnswer's `seen`, PolyglotConsensus's dedupe
  map) for "does this key exist yet" without ever touching a Principle
  record that might not exist. A principle's `author` is fixed at
  registration and is the only address permitted to `bump()` it -- a form
  of decentralized, per-entry ownership rather than one global registry
  owner, so no single party controls every shared definition.

REUSE
  Shared, audited "definitions of agreement" across an ecosystem of
  contracts: a DAO could publish one canonical "materially different"
  principle that every one of its SemanticDiffLedger-style contracts reads
  from, so a governance vote to tighten or loosen the definition updates
  every consumer at once instead of requiring N separate upgrades.

## Runner verification
  This contract itself never calls `gl.get_contract_at` -- it is always the
  TARGET of a cross-contract read, never the caller. The read half of that
  surface (`.view().method()` returning a value directly, no wrapper) is
  already confirmed live via MirrorAudit and CanaryTripwire; no new
  verification is needed here. Any contract that fetches from this registry
  should still audit its own call site per CLAUDE.md's "Contract-to-contract"
  rules (isolate the call, tag it `# VERIFY:`, document the check).
"""

from genlayer import *
import json
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
class Principle:
    text: str
    author: Address


class EquivalenceRegistry(gl.Contract):
    principles: TreeMap[str, Principle]
    versions: TreeMap[str, u256]

    def __init__(self):
        pass

    @gl.public.write
    def register(self, name: str, text: str) -> int:
        n = (name if isinstance(name, str) else "").strip()
        t = (text if isinstance(text, str) else "").strip()
        require(len(n) > 0, "empty name")
        require(len(t) > 0, "empty text")
        require(int(self.versions.get(n, u256(0))) == 0, "already registered; use bump")

        self.principles[n] = Principle(text=t, author=gl.message.sender_address)
        self.versions[n] = u256(1)
        return 1

    @gl.public.write
    def bump(self, name: str, text: str) -> int:
        n = (name if isinstance(name, str) else "").strip()
        t = (text if isinstance(text, str) else "").strip()
        current_version = int(self.versions.get(n, u256(0)))
        require(current_version > 0, "not registered; use register")
        require(len(t) > 0, "empty text")

        existing = self.principles[n]
        require(gl.message.sender_address == existing.author, "only the original author may bump")

        self.principles[n] = Principle(text=t, author=existing.author)
        new_version = current_version + 1
        self.versions[n] = u256(new_version)
        return new_version

    # -- reads --------------------------------------------------------------------
    @gl.public.view
    def exists(self, name: str) -> bool:
        n = name if isinstance(name, str) else ""
        return int(self.versions.get(n, u256(0))) > 0

    @gl.public.view
    def version_of(self, name: str) -> int:
        n = name if isinstance(name, str) else ""
        return int(self.versions.get(n, u256(0)))

    @gl.public.view
    def get(self, name: str) -> str:
        # The plain-text return other contracts feed straight into their own
        # comparative/non_comparative calls as the equivalence principle.
        n = name if isinstance(name, str) else ""
        require(int(self.versions.get(n, u256(0))) > 0, "no such principle")
        return self.principles[n].text

    @gl.public.view
    def get_full(self, name: str) -> str:
        n = name if isinstance(name, str) else ""
        v = int(self.versions.get(n, u256(0)))
        require(v > 0, "no such principle")
        p = self.principles[n]
        return canonical(
            {"name": n, "text": p.text, "author": p.author.as_hex, "version": v}
        )
