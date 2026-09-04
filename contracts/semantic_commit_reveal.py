# { "Depends": "py-genlayer:5jycge4q8k23462jtb0b9fyey1s9q928sz2nbrd9mg4sxqg2qng" }
"""
PENUMBRA -- III. SEMANTIC MACHINES -- 05

SemanticCommitReveal -- a commit-reveal scheme where a reveal is accepted
only if it actually MEANS the thing that was committed to, not merely
because it can be bound to the commit hash. Defeats a dishonest pivot at
reveal time: bind the hash, but let the network judge whether the public
statement you register is a faithful instantiation of what you privately
locked in, or an opportunistic change of mind dressed up in different words.

WHY IT IS UNUSUAL
  Ordinary commit-reveal only proves you knew a pre-image before some
  deadline; it says nothing about whether what you reveal is what you
  actually meant when you committed. That gap is exploitable: in a
  commit-reveal vote or bid, a participant who watches early reveals land
  can try to quietly pivot their own reveal toward a more advantageous
  answer while still hash-binding to their original commitment, so long as
  they can craft SOME text consistent with the pre-image. This primitive
  closes that gap by splitting "prove you knew the secret" (deterministic,
  hash-bound, unforgeable) from "prove what you're registering now is the
  same claim you locked in" (judged by consensus, paraphrase-tolerant but
  pivot-intolerant).

HOW CONSENSUS IS USED
  Two checks run in sequence at reveal time, and only one of them touches an
  LLM:

  1. DETERMINISTIC BIND. `commit(hash)` stores `hash = sha256(intent + salt)`
     computed off-chain over a private `intent` string the committer chooses
     at commit time. At reveal, the caller submits `(intent, salt,
     statement)`. The contract recomputes `sha256(intent + salt)` and
     requires it to equal the stored hash, in plain Python, before anything
     else runs. This is the literal binding mechanism CONTRACTS.md's spec
     calls out ("a deterministic hash check still binds the commit phase")
     -- it proves the caller knew `intent` before ever seeing the reveal
     phase open, exactly like ordinary commit-reveal, and it CANNOT be
     satisfied by an LLM judgment call.

  2. COMPARATIVE SEMANTIC GATE. Only once the hash bind passes does the
     nondet block run: it asks whether the caller's now-revealed private
     `intent` and their public `statement` assert the SAME underlying claim.
     Consensus is reached with the COMPARATIVE equivalence principle --
     independent validators each re-run the judgment and must agree the two
     texts match under a "same intent" principle (paraphrase-tolerant,
     pivot-intolerant, same shape as PolyglotConsensus's translation-
     invariant meaning check). This is what CONTRACTS.md's spec means by
     "comparative on (decrypted commit intent) vs (revealed statement)" --
     `intent` is literally decrypted/recovered by the reveal call (it was
     never stored on-chain until now), and `statement` is what the caller
     wants publicly registered.

  A reveal is single-shot: attempting to reveal twice for the same address
  reverts (see STATE DESIGN), so there is no free retry loop to probe the
  LLM for wording that slips through. `accepted` records the actual outcome.

DEVIATIONS FROM THE LITERAL CATALOG SPEC (documented per repo convention --
see DECISIONS.md for the parallel cases in AmbiguityGuard and PolyglotConsensus)
  1. NO REVEAL-WINDOW TIMESTAMPS. The spec's State line names "reveal window
     timestamps", but CLAUDE.md's "Known blockers" section confirms live
     (via an isolation probe dumping `dir(gl.message)`) that this runner
     exposes NO clock, timestamp, or block-number accessor at all --
     `gl.message.datetime` does not exist. `SemanticDeadman` was already
     redesigned around this exact finding; this contract follows the same
     precedent. Instead of a time-based window, phase transition is an
     explicit two-state machine (`COMMIT` -> `REVEAL`) advanced by one
     owner-only deterministic call, `open_reveal_phase()`. This is strictly
     more conservative than a timestamp window (no ambiguity about "did the
     window already close"), at the cost of needing a trusted phase-advancer
     -- an acceptable tradeoff given the runner has no alternative primitive
     for time at all.
  2. STATE SHAPE -- TWO APPEND-ONLY ARCHIVES, NOT ONE MUTABLE MAP. The spec
     names `TreeMap[Address, Commit]` directly, implying a single record per
     address that gets mutated in place when revealed. Two separate risks
     ruled that out: (a) no contract in this repo has verified a TreeMap
     keyed to an `@allow_storage` dataclass VALUE live -- every proven
     TreeMap usage (ProofCarryingAnswer's `seen`, PolyglotConsensus's `seen`,
     the `claimable` ledgers in JailbreakBounty/SchellingResolver/
     SemanticDeadman) is a single concrete SCALAR value type (`u256`); (b)
     no contract in this repo has ever written to an existing `DynArray`
     index (`self.arr[i] = x`) -- every DynArray in every flagship is
     strictly append-only. Rather than combine two unverified patterns to
     match the spec's literal shape, this contract stays entirely inside
     proven territory: `commits` and `reveals` are two independent,
     append-only `DynArray` archives (mirroring SchellingResolver's
     `submissions`/`winners` split), each paired with its own
     `TreeMap[Address, u256]` "1 + index" existence map (ProofCarryingAnswer's
     `seen` pattern, used twice). "Already revealed" is enforced by checking
     whether a `reveals` entry already exists for the caller, not by reading
     a mutable field back out of the original commit.

STATE DESIGN
  `commits` and `committer_index` record the commit phase; `reveals` and
  `reveal_index` record the reveal phase. Both index maps use the same
  1-based "1 + index" sentinel (0 means "no entry yet") already proven
  throughout this repo. `phase` is the explicit two-state machine described
  above. `owner` is fixed at deploy time and is the only address permitted
  to advance the phase.

REUSE
  Sealed-bid auctions, commit-reveal votes, or any scheme where exact
  wording shouldn't be game-able but genuine paraphrase should still count
  -- register a short private `intent` at commit time, and let the public
  `statement` be as detailed as needed at reveal time.
"""

from genlayer import *
import json
import hashlib
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


def parse_json_response(text: str) -> dict:
    # response_format="json" crashes GenVM when combined with prompt_comparative
    # on this runner (confirmed by isolation testing) -- ask the model for JSON as
    # plain text instead and parse it ourselves, tolerating markdown code fences.
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t[:4].lower() == "json":
            t = t[4:]
        t = t.strip()
    start, end = t.find("{"), t.rfind("}")
    if start != -1 and end != -1:
        t = t[start : end + 1]
    return json.loads(t)
# ------------------------------------------------------------------------------


PHASE_COMMIT = "COMMIT"
PHASE_REVEAL = "REVEAL"


@allow_storage
@dataclass
class Commit:
    committer: Address
    hash: str


@allow_storage
@dataclass
class Reveal:
    committer: Address
    accepted: bool
    statement: str


class SemanticCommitReveal(gl.Contract):
    owner: Address
    phase: str
    commits: DynArray[Commit]
    committer_index: TreeMap[Address, u256]   # address -> 1 + index into commits
    reveals: DynArray[Reveal]
    reveal_index: TreeMap[Address, u256]      # address -> 1 + index into reveals

    def __init__(self):
        self.owner = gl.message.sender_address
        self.phase = PHASE_COMMIT

    @gl.public.write
    def commit(self, hash: str) -> None:
        require(self.phase == PHASE_COMMIT, "commit phase is closed")
        h = hash.strip().lower()
        require(len(h) == 64 and all(c in "0123456789abcdef" for c in h), "hash must be a sha256 hex digest")

        sender = gl.message.sender_address
        require(int(self.committer_index.get(sender, u256(0))) == 0, "already committed")

        self.commits.append(Commit(committer=sender, hash=h))
        self.committer_index[sender] = u256(len(self.commits))

    @gl.public.write
    def open_reveal_phase(self) -> None:
        require(gl.message.sender_address == self.owner, "only owner can open the reveal phase")
        require(self.phase == PHASE_COMMIT, "reveal phase already open")
        self.phase = PHASE_REVEAL

    @gl.public.write
    def reveal(self, intent: str, salt: str, statement: str) -> bool:
        require(self.phase == PHASE_REVEAL, "reveal phase is not open yet")
        i = intent.strip()
        s = salt.strip()
        st = statement.strip()
        require(len(i) > 0, "empty intent")
        require(len(s) > 0, "empty salt")
        require(len(st) > 0, "empty statement")

        sender = gl.message.sender_address
        slot = int(self.committer_index.get(sender, u256(0)))
        require(slot > 0, "no commit found for this address")
        require(int(self.reveal_index.get(sender, u256(0))) == 0, "already revealed")

        commit_rec = self.commits[slot - 1]

        # DETERMINISTIC BIND -- plain sha256 equality, no LLM involved. This is
        # the unforgeable half: it proves the caller knew `intent` (and `salt`)
        # before the reveal phase ever opened.
        computed = hashlib.sha256((i + s).encode()).hexdigest()
        require(computed == commit_rec.hash, "intent/salt does not match the committed hash")

        # COMPARATIVE SEMANTIC GATE -- only reached once the bind above holds.
        def same_intent() -> str:
            prompt = f"""You are auditing a commit-reveal scheme for dishonest pivots.
PRIVATELY COMMITTED INTENT (locked in before this text was ever public): {i}
PUBLICLY REGISTERED STATEMENT (what the participant wants recorded now): {st}

Decide whether the STATEMENT is a faithful instantiation of the INTENT --
same underlying claim, same substance, allowing paraphrase, added detail, or
clarification, but NOT a material change of position, target, amount, or
outcome.

Return ONLY strict JSON, no prose, no markdown:
{{
  "same_intent": <true|false>,
  "confidence": <float 0..1>
}}"""
            raw = gl.nondet.exec_prompt(prompt)
            data = parse_json_response(raw)
            same = bool(data["same_intent"])
            confidence = max(0.0, min(1.0, float(data.get("confidence", 0.0))))
            return canonical({"same_intent": same, "confidence_milli": int(round(confidence * 1000))})

        principle = (
            "The two results judge whether a PUBLIC STATEMENT faithfully instantiates "
            "a PRIVATELY COMMITTED INTENT, produced independently and possibly by "
            "different models. They are EQUIVALENT only if the 'same_intent' fields "
            "match. Judge the underlying claim conservatively: paraphrase, added "
            "detail, and clarification are consistent with a true 'same_intent'; any "
            "material change in position, target, amount, or outcome must be false."
        )
        agreed = gl.eq_principle.prompt_comparative(same_intent, principle)
        parsed = json.loads(agreed)
        accepted = bool(parsed["same_intent"])

        # Single-shot: the reveal_index entry is written regardless of outcome,
        # so there is no retry loop to probe the LLM for wording that slips
        # through. `commits`/`reveals` both stay strictly append-only.
        self.reveals.append(Reveal(committer=sender, accepted=accepted, statement=st))
        self.reveal_index[sender] = u256(len(self.reveals))
        return accepted

    # -- reads ------------------------------------------------------------------
    @gl.public.view
    def phase_now(self) -> str:
        return self.phase

    @gl.public.view
    def count(self) -> int:
        return len(self.commits)

    @gl.public.view
    def reveal_count(self) -> int:
        return len(self.reveals)

    @gl.public.view
    def get(self, index: int) -> str:
        require(0 <= index < len(self.commits), "no such commit")
        c = self.commits[index]
        return canonical({"committer": c.committer.as_hex, "hash": c.hash})

    @gl.public.view
    def get_reveal(self, index: int) -> str:
        require(0 <= index < len(self.reveals), "no such reveal")
        r = self.reveals[index]
        return canonical(
            {"committer": r.committer.as_hex, "accepted": r.accepted, "statement": r.statement}
        )

    @gl.public.view
    def commit_of(self, who: Address) -> str:
        addr = who if isinstance(who, Address) else Address(who)
        slot = int(self.committer_index.get(addr, u256(0)))
        require(slot > 0, "no commit found for this address")
        return self.get(slot - 1)

    @gl.public.view
    def reveal_of(self, who: Address) -> str:
        addr = who if isinstance(who, Address) else Address(who)
        slot = int(self.reveal_index.get(addr, u256(0)))
        require(slot > 0, "no reveal found for this address")
        return self.get_reveal(slot - 1)

    @gl.public.view
    def has_revealed(self, who: Address) -> bool:
        addr = who if isinstance(who, Address) else Address(who)
        return int(self.reveal_index.get(addr, u256(0))) > 0
