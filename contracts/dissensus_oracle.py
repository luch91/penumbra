# { "Depends": "py-genlayer:5jycge4q8k23462jtb0b9fyey1s9q928sz2nbrd9mg4sxqg2qng" }
"""
PENUMBRA -- I. ORACLES OF DOUBT -- 01

DissensusOracle -- an oracle that answers a question AND reports how much it
should be trusted, by measuring its own internal disagreement.

WHY IT IS UNUSUAL
  Every other oracle treats validator disagreement as a failure to be hidden.
  This one treats DISAGREEMENT AS THE PRODUCT. It answers a subjective or
  contested question and, alongside the answer, exposes a `dissensus` score in
  [0,1]: 0 means "every reasonable analyst agrees", 1 means "this is genuinely
  contested". Downstream contracts can read that score and refuse to act on
  answers that are too close to call. It is an epistemic humility primitive.

HOW CONSENSUS IS USED
  The non-deterministic block does NOT ask the model for one answer. It asks
  for a self-ensemble: K independent expert opinions, then a majority verdict
  and the fraction of experts who agreed with it (`agreement`). The contract
  stores `dissensus = 1 - agreement`.

  Consensus is reached with the COMPARATIVE equivalence principle. Each
  validator independently runs the same self-ensemble. The principle requires
  that validators agree on (a) the majority verdict and (b) the agreement ratio
  to within a tolerance. So two things must hold for a write to land: the model
  must reach a verdict, AND independent validators (running different LLMs) must
  concur on how *hard* the question was. A question that is hard in an unstable
  way -- where even the difficulty is unclear -- fails consensus and reverts.
  That failure is itself meaningful: the oracle declines to speak.

STATE DESIGN
  A pull-style archive: every resolved question is appended to `records` so the
  history of what was asked, what was decided, and how contested it was becomes
  a queryable on-chain corpus. `latest` indexes the most recent record id.

REUSE
  Wrap any high-stakes judgment ("is this transaction fraudulent?", "did the
  contractor deliver?") and gate execution on the stored `contested` category. Consumers should use that category rather than recomputing a threshold from a tolerated score.
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


@allow_storage
@dataclass
class Record:
    question: str
    verdict: str
    dissensus_milli: u256  # dissensus * 1000, stored as integer to stay exact
    sample_size: u256
    contested: bool


# A scale factor keeps probabilities exact on-chain. Floats are fine *inside* a
# nondet block, but state and comparisons stay integer to avoid any drift.
_MILLI = 1000


class DissensusOracle(gl.Contract):
    records: DynArray[Record]
    latest: u256
    ensemble_size: u256          # how many independent opinions to simulate
    tolerance_milli: u256        # allowed gap between validators on agreement
    contested_threshold_milli: u256

    def __init__(
        self,
        ensemble_size: int = 7,
        tolerance_milli: int = 250,
        contested_threshold_milli: int = 500,
    ):
        require(3 <= ensemble_size <= 25, "ensemble_size out of range")
        require(0 < tolerance_milli <= 500, "tolerance out of range")
        require(0 <= contested_threshold_milli <= 1000, "contested threshold out of range")
        self.ensemble_size = u256(ensemble_size)
        self.tolerance_milli = u256(tolerance_milli)
        self.contested_threshold_milli = u256(contested_threshold_milli)
        self.latest = u256(0)

    @gl.public.write
    def resolve(self, question: str) -> str:
        require(len(question.strip()) > 0, "empty question")

        # Read everything the nondet block needs into plain locals. The block may
        # not touch self/storage, so we close over these values.
        k = int(self.ensemble_size)
        tol = int(self.tolerance_milli)
        contested_threshold = int(self.contested_threshold_milli)

        def opinionate() -> str:
            prompt = f"""You are convening {k} INDEPENDENT domain experts to judge a question.
Each expert reasons separately. Do not let them converge artificially.

QUESTION: {question}

Return ONLY strict JSON, no prose, no markdown:
{{
  "verdict": "<the single answer the plurality of experts would give, lowercased, <= 6 words>",
  "agreement": <float 0..1 = fraction of the {k} experts who back that verdict>,
  "sample_size": {k}
}}
The verdict must be a concrete answer, never "it depends". `agreement` reflects
genuine spread of expert opinion: near 1.0 only when the answer is clear-cut."""
            raw = gl.nondet.exec_prompt(prompt)
            data = parse_json_response(raw)
            verdict = str(data["verdict"]).strip().lower()
            agreement = float(data["agreement"])
            agreement = max(0.0, min(1.0, agreement))
            agreement_milli = int(round(agreement * _MILLI))
            dissensus_milli = _MILLI - agreement_milli
            contested = dissensus_milli >= contested_threshold
            # Canonicalize: integer milli-units so strict structural fields match
            # and the comparative principle has a stable surface to judge.
            return canonical(
                {
                    "verdict": verdict,
                    "agreement_milli": agreement_milli,
                    "sample_size": k,
                    "contested": contested,
                }
            )

        principle = (
            "The two results describe the same expert poll. They are EQUIVALENT only if: "
            "(1) the 'verdict' fields mean the same thing (synonyms and paraphrases are fine), "
            f"and (2) the agreement_milli values differ by at most {tol}, and "
            "(3) the contested fields are identical. If the verdicts disagree, "
            "the agreement levels are far apart, or the action category differs, "
            "they are NOT equivalent."
        )
        agreed = gl.eq_principle.prompt_comparative(opinionate, principle)
        parsed = json.loads(agreed)

        verdict = str(parsed["verdict"])
        agreement_milli = int(parsed["agreement_milli"])
        contested = bool(parsed["contested"])
        expected_contested = (_MILLI - agreement_milli) >= contested_threshold
        require(contested == expected_contested, "contested category does not match score")
        dissensus_milli = _MILLI - agreement_milli

        rec = Record(
            question=question,
            verdict=verdict,
            dissensus_milli=u256(dissensus_milli),
            sample_size=u256(int(parsed["sample_size"])),
            contested=contested,
        )
        self.records.append(rec)
        self.latest = u256(len(self.records) - 1)
        return verdict

    # -- reads ----------------------------------------------------------------
    @gl.public.view
    def count(self) -> int:
        return len(self.records)

    @gl.public.view
    def get(self, record_id: int) -> str:
        require(0 <= record_id < len(self.records), "no such record")
        r = self.records[record_id]
        return canonical(
            {
                "question": r.question,
                "verdict": r.verdict,
                "dissensus_milli": int(r.dissensus_milli),
                "sample_size": int(r.sample_size),
                "contested": r.contested,
            }
        )

    @gl.public.view
    def latest_verdict(self) -> str:
        require(len(self.records) > 0, "no records yet")
        return self.get(int(self.latest))

    @gl.public.view
    def is_contested(self, record_id: int) -> bool:
        """Return the category agreed during resolution."""
        require(0 <= record_id < len(self.records), "no such record")
        return self.records[record_id].contested
