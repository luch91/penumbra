# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""
PENUMBRA -- VII. CHRONOMANCY -- 19

EscalatingVerdict -- match consensus rigor to stakes, so a penny dispute
costs a penny's worth of scrutiny and real money gets real scrutiny.

WHY IT IS UNUSUAL
  Every other primitive in this repo picks ONE equivalence principle and
  commits to it. This one is a dispatcher: the same contract runs all three
  of the graduated consensus moves, and the caller's own escrowed stake --
  not an admin flag, not a spec field -- deterministically selects which one
  a given dispute gets. Cheap disputes get the cheapest, strictest check;
  expensive ones get the most scrutiny per resolution. This is the "match
  consensus rigor to stakes" idea taken literally, as a dispatcher rather
  than a single move.

HOW CONSENSUS IS USED
  `open_dispute(question)` is payable; `gl.message.value` is the stake, and
  the tier is a deterministic threshold compare against it -- no ambiguity,
  no LLM involved in tier selection. `resolve(id)` then dispatches on the
  STORED tier (fixed at open time, so a caller cannot game the tier after
  seeing early signal):
    - STRICT (small stake): `strict_eq`. The model is asked for a
      single-word verdict from a constrained vocabulary (yes/no/unclear).
      Low-entropy output is a precondition for `strict_eq` to ever agree --
      this tier is only appropriate for near-mechanical questions, which is
      exactly what "cheap disputes stay cheap" implies.
    - COMPARATIVE (mid stake): `prompt_comparative`, the same
      paraphrase-tolerant "same verdict" idiom used throughout this repo
      (DissensusOracle, JailbreakBounty, SemanticDiffLedger). Validators
      independently re-judge and must agree in meaning, not wording.
    - NON_COMPARATIVE (large stake): `prompt_non_comparative` over a
      DELIBERATE deviation from CONTRACTS.md's literal "multi-source"
      wording -- see below.

  DEVIATION, documented per CLAUDE.md instructions: CONTRACTS.md describes
  the large-stake tier as "multi-source non_comparative." `open_dispute`
  takes only a `question` string, with no URLs or external sources (unlike
  CorroborationOracle/ProvenanceAttestor, which genuinely fetch the web).
  `non_comparative` also requires its verification INPUT to be identical
  and deterministic on every node -- it cannot itself contain a leader-only
  LLM call's output, or the "same input on every node" guarantee breaks.
  So "multi-source" here is built as multi-LENS, not multi-URL: three fixed,
  deterministically-derived analytical angles (factual accuracy, internal
  consistency, counter-argument robustness) are named directly in the
  verification input, and the `task`/`criteria` require the leader's ruling
  to address all three explicitly. This keeps the input byte-identical
  across every validator (a hard requirement) while still giving the
  large-stake tier genuinely more scrutiny than the mid tier -- more angles
  the ruling must survive, not more raw web sources, since the API this
  primitive was specified with does not carry any.

STATE DESIGN
  Append-only `DynArray[Dispute]` (question, stake, tier) that is never
  mutated after creation, plus a separate `TreeMap[u256, str]` of verdicts
  keyed by dispute id, populated only once at resolve time -- the same
  dual-structure workaround SemanticCommitReveal uses, since no contract in
  this repo has verified in-place `DynArray` element mutation
  (`self.some_dyn_array[i] = x`), only append and read-by-index. A dispute
  is "resolved" precisely when its id has an entry in `verdicts`; every
  verdict this contract ever produces is a non-empty phrase, so a missing/
  empty lookup is an unambiguous "not yet resolved" signal. `treasury: u256`
  collects the escrowed stakes as non-refundable dispute fees (CONTRACTS.md
  specifies no payout mechanism for this primitive, unlike JailbreakBounty/
  SchellingResolver); the owner can sweep it via the same pull-payment idiom
  used everywhere else in this repo that touches payable value.

REUSE
  Marketplaces, insurance claims, arbitration -- any dispute mechanism where
  the cost of consensus should scale with what is actually at stake.
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

_TIER_STRICT = "STRICT"
_TIER_COMPARATIVE = "COMPARATIVE"
_TIER_NON_COMPARATIVE = "NON_COMPARATIVE"

_LENSES = (
    "Factual accuracy",
    "Internal consistency",
    "Counter-argument robustness",
)


@allow_storage
@dataclass
class Dispute:
    question: str
    stake: u256
    tier: str



@gl.evm.contract_interface
class _NativeRecipient:
    class View:
        pass

    class Write:
        pass


def send_native(recipient: Address, amount: int) -> None:
    _NativeRecipient(recipient).emit_transfer(value=u256(amount))

class EscalatingVerdict(gl.Contract):
    owner: Address
    mid_threshold: u256
    large_threshold: u256
    disputes: DynArray[Dispute]
    verdicts: TreeMap[u256, str]
    treasury: u256

    def __init__(self, mid_threshold: int = 1000, large_threshold: int = 10000):
        require(mid_threshold > 0, "mid_threshold must be positive")
        require(large_threshold > mid_threshold, "large_threshold must exceed mid_threshold")
        self.owner = gl.message.sender_address
        self.mid_threshold = u256(mid_threshold)
        self.large_threshold = u256(large_threshold)
        self.treasury = u256(0)

    def _tier_for(self, stake: int) -> str:
        if stake < int(self.mid_threshold):
            return _TIER_STRICT
        if stake < int(self.large_threshold):
            return _TIER_COMPARATIVE
        return _TIER_NON_COMPARATIVE

    @gl.public.write.payable
    def open_dispute(self, question: str) -> int:
        q = (question if isinstance(question, str) else "").strip()
        require(len(q) > 0, "empty question")
        stake = int(gl.message.value)
        tier = self._tier_for(stake)

        self.disputes.append(Dispute(question=q, stake=u256(stake), tier=tier))
        self.treasury = u256(int(self.treasury) + stake)
        return len(self.disputes) - 1

    @gl.public.write
    def resolve(self, dispute_id: int) -> str:
        require(0 <= dispute_id < len(self.disputes), "no such dispute")
        did = u256(dispute_id)
        require(self.verdicts.get(did, "") == "", "already resolved")
        d = self.disputes[dispute_id]

        q = d.question
        tier = d.tier

        if tier == _TIER_STRICT:
            verdict = self._resolve_strict(q)
        elif tier == _TIER_COMPARATIVE:
            verdict = self._resolve_comparative(q)
        else:
            verdict = self._resolve_non_comparative(q)

        self.verdicts[did] = verdict
        return verdict

    # -- STRICT: cheapest, strictest. Only fit for near-mechanical questions --
    def _resolve_strict(self, question: str) -> str:
        q = question

        def inner() -> str:
            data = gl.nondet.exec_prompt(
                f"""Answer the following dispute with a single constrained verdict.

QUESTION: {q}

Return ONLY strict JSON, no prose, no markdown:
{{ "verdict": "<exactly one of: yes, no, unclear>" }}""",
                response_format="json",
            )
            return json.dumps(data, sort_keys=True, separators=(",", ":"))

        agreed = gl.eq_principle.strict_eq(inner)
        parsed = json.loads(agreed)
        verdict = str(parsed["verdict"]).strip().lower()
        return verdict if verdict else "unclear"

    # -- COMPARATIVE: paraphrase-tolerant agreement on the verdict -----------
    def _resolve_comparative(self, question: str) -> str:
        q = question

        def inner() -> str:
            prompt = f"""You are ruling on a disputed question.

QUESTION: {q}

Return ONLY strict JSON, no prose, no markdown:
{{ "verdict": "<a short phrase, not a sentence>", "rationale": "<one sentence>" }}"""
            raw = gl.nondet.exec_prompt(prompt)
            data = parse_json_response(raw)
            verdict = str(data["verdict"]).strip()
            rationale = str(data.get("rationale", ""))[:280]
            return canonical({"verdict": verdict, "rationale": rationale})

        principle = (
            "Both results are verdicts on the same disputed question. They are "
            "EQUIVALENT if and only if the 'verdict' fields mean the same thing "
            "(synonyms and paraphrases are fine). The 'rationale' text may differ "
            "freely and must be ignored when comparing."
        )
        agreed = gl.eq_principle.prompt_comparative(inner, principle)
        parsed = json.loads(agreed)
        verdict = str(parsed["verdict"]).strip()
        return verdict if verdict else "unclear"

    # -- NON_COMPARATIVE: multi-lens scrutiny, leader rules, validators verify --
    def _resolve_non_comparative(self, question: str) -> str:
        q = question
        lenses = _LENSES

        def verification_input() -> str:
            # Deterministic: identical on leader and every validator. The
            # three lenses are fixed constants, not model output -- see the
            # module docstring's "DEVIATION" note for why this stands in for
            # CONTRACTS.md's literal "multi-source" wording.
            return canonical({"question": q, "lenses": list(lenses)})

        task = (
            "You are ruling on a high-stakes disputed question. The input JSON "
            "has 'question' and 'lenses' (a fixed list of analytical angles you "
            "must consider). Rule on the question taking EVERY listed lens into "
            "account. Output ONLY strict JSON: "
            '{"verdict": "<a short phrase, not a sentence>", "note": "<must '
            "reference how each lens was addressed, in one or two sentences per "
            'lens>"}.'
        )
        criteria = (
            "A trustworthy verdict has these properties: (1) 'note' explicitly "
            "addresses EVERY lens named in 'lenses' -- a ruling that ignores one "
            "is not trustworthy, regardless of how confident it sounds; (2) the "
            "'verdict' must not contradict any point raised under a lens in "
            "'note'; (3) if the lenses genuinely conflict with no resolution, "
            "'verdict' must say so explicitly rather than picking a side "
            "silently. Reject the verdict if 'note' skips a lens or the verdict "
            "contradicts its own note."
        )

        raw = gl.eq_principle.prompt_non_comparative(
            verification_input, task=task, criteria=criteria
        )
        parsed = json.loads(raw) if isinstance(raw, str) else raw
        verdict = str(parsed["verdict"]).strip()
        return verdict if verdict else "unclear"

    # -- treasury (pull pattern) ------------------------------------------------
    @gl.public.write
    def withdraw_treasury(self) -> int:
        require(gl.message.sender_address == self.owner, "only owner")
        amount = int(self.treasury)
        require(amount > 0, "treasury empty")
        send_native(self.owner, amount)
        self.treasury = u256(0)
        # Native GEN transfer is emitted before the ledger is cleared.
        return amount

    # -- reads --------------------------------------------------------------------
    @gl.public.view
    def count(self) -> int:
        return len(self.disputes)

    @gl.public.view
    def get(self, dispute_id: int) -> str:
        require(0 <= dispute_id < len(self.disputes), "no such dispute")
        d = self.disputes[dispute_id]
        verdict = self.verdicts.get(u256(dispute_id), "")
        return canonical(
            {
                "question": d.question,
                "stake": int(d.stake),
                "tier": d.tier,
                "resolved": verdict != "",
                "verdict": verdict,
            }
        )

    @gl.public.view
    def tier_for_stake(self, stake: int) -> str:
        return self._tier_for(int(stake))
