# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""
PENUMBRA -- IV. ADVERSARIA -- 11

AdversarialReview -- decide a contested claim by staging a debate inside the
leader's own reasoning, rather than asking for a single unopposed judgment.

WHY IT IS UNUSUAL
  Every other judgment-style primitive in this repo (DissensusOracle,
  AmbiguityGuard, ConsensusThermometer) asks the model for its opinion
  directly. This one forces the model to argue BOTH sides first -- generate
  the strongest good-faith case for the claim and the strongest good-faith
  case against it -- before ruling. Debate-as-consensus: a verdict that had
  to survive its own steelmanned opposition is a stronger signal than one
  that was never made to argue with itself.

HOW CONSENSUS IS USED
  The claim alone is the deterministic input -- identical on the leader and
  every validator. The `non_comparative` principle's `task` instructs the
  leader to construct both cases AND rule on them in one call; the
  `criteria` define what makes that whole package trustworthy: both cases
  must be genuine and substantive (no strawmanning either side), the ruling
  must actually follow from comparing them (stated in the rationale, not
  asserted), and the margin must not contradict its own rationale. Validators
  audit the leader's full package against these criteria; they never stage
  their own debate. This is the correct move (not `comparative`) because the
  input is byte-identical everywhere -- there is nothing to disagree about
  except whether the leader's debate-and-ruling holds up, which is exactly
  what non_comparative verifies.

STATE DESIGN
  An append-only `DynArray[Case]` ledger: the claim, the winning side, a
  margin in milli-units (0 = a coin-flip-close call, 1000 = a rout), and
  content-addressed digests of both the pro and con cases the leader
  produced. The full case text is returned transiently from `adjudicate()`
  but not stored on-chain -- the same "digest on-chain, full text off-chain"
  pattern ProofCarryingAnswer uses for its proof, which lets anyone who
  saved the original response verify it wasn't altered without paying
  storage for prose on every ruling.

REUSE
  Grant review, content appeals, any "steelman both sides" decision where a
  ruling should be forced to survive its own best counter-argument first.
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


def parse_json_response(text: str) -> dict:
    value = text.strip()
    if value.startswith("```"):
        lines = value.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        value = "\n".join(lines).strip()
    return json.loads(value)
# ------------------------------------------------------------------------------


@allow_storage
@dataclass
class Case:
    claim: str
    winner: str
    margin_milli: u256
    pro_case_hash: str
    con_case_hash: str


class AdversarialReview(gl.Contract):
    cases: DynArray[Case]

    def __init__(self):
        pass

    @gl.public.write
    def adjudicate(self, claim: str) -> str:
        c = (claim if isinstance(claim, str) else "").strip()
        require(len(c) > 0, "empty claim")

        def verification_input() -> str:
            # Fully deterministic: identical on leader and every validator.
            return canonical({"claim": c})

        task = (
            "You are staging an adversarial debate to decide a contested claim. "
            "The input JSON has a 'claim'. Construct the STRONGEST good-faith "
            "case FOR the claim (pro) and the STRONGEST good-faith case AGAINST "
            "it (con) -- steelman both sides, do not strawman either one. Then "
            "rule which side actually wins and by what margin. Output ONLY "
            "strict JSON: "
            '{"winner": "<pro|con>", "margin_milli": <int 0..1000>, '
            '"pro_case": "<the strongest case for the claim>", '
            '"con_case": "<the strongest case against the claim>", '
            '"rationale": "<one or two sentences on why the winning side '
            'prevails over the losing one>"}.'
        )
        criteria = (
            "A trustworthy verdict has these properties: (1) both 'pro_case' "
            "and 'con_case' are genuine, substantive arguments -- reject if "
            "either is missing, trivial, or an obvious strawman of its side; "
            "(2) 'winner' must follow from actually comparing the two cases in "
            "'rationale', not be asserted without support; (3) 'margin_milli' "
            "must reflect how decisively the winning case beat the losing one "
            "-- near 0 for a close call, near 1000 for a rout -- and must not "
            "contradict what 'rationale' describes (e.g. claiming a landslide "
            "while the rationale describes a close call is untrustworthy). "
            "Reject the verdict if any of these fail."
        )

        raw = gl.eq_principle.prompt_non_comparative(
            verification_input, task=task, criteria=criteria
        )
        verdict = parse_json_response(raw) if isinstance(raw, str) else raw

        winner = str(verdict["winner"]).strip().lower()
        require(winner in ("pro", "con"), "verdict did not name pro or con as winner")
        margin = max(0, min(1000, int(verdict.get("margin_milli", 0))))
        pro_case = str(verdict.get("pro_case", ""))
        con_case = str(verdict.get("con_case", ""))
        pro_hash = hashlib.sha256(pro_case.encode()).hexdigest()
        con_hash = hashlib.sha256(con_case.encode()).hexdigest()

        self.cases.append(
            Case(
                claim=c,
                winner=winner,
                margin_milli=u256(margin),
                pro_case_hash=pro_hash,
                con_case_hash=con_hash,
            )
        )
        return winner

    # -- reads --------------------------------------------------------------------
    @gl.public.view
    def count(self) -> int:
        return len(self.cases)

    @gl.public.view
    def get(self, index: int) -> str:
        require(0 <= index < len(self.cases), "no such case")
        c = self.cases[index]
        return canonical(
            {
                "claim": c.claim,
                "winner": c.winner,
                "margin_milli": int(c.margin_milli),
                "pro_case_hash": c.pro_case_hash,
                "con_case_hash": c.con_case_hash,
            }
        )
