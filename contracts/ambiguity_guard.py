# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""
PENUMBRA -- II. ASYMMETRIC RITES -- 02

AmbiguityGuard -- a drop-in wrapper that returns a verdict or ABSTAIN, never a
confident-sounding answer to a question that is not safe to answer confidently.

WHY IT IS UNUSUAL
  Most oracles are graded on always producing an answer. This one is graded on
  knowing when NOT to. It is a fail-safe gate: compose it in front of a
  governance action, a liquidation, or a moderation call, and let it refuse to
  unlock the real action when the underlying question is genuinely contested
  or underspecified. Silence, here, is a first-class outcome, not an error.

HOW CONSENSUS IS USED (AND WHY IT DEVIATES FROM THE CATALOG SPEC'S WORDING)
  CONTRACTS.md describes this primitive's consensus move as "a comparative
  principle that treats 'leader answered X, validator would answer ABSTAIN'
  as non-equivalent; persistent non-equivalence collapses to a stored
  ABSTAIN." Taken literally, that would mean: let `gl.eq_principle.prompt_comparative`
  itself fail to reach consensus across validator rotations, and catch that
  failure inside the contract to substitute ABSTAIN. That mechanism is NOT
  something this repo has verified is catchable -- every other primitive that
  depends on prompt_comparative reaching consensus treats a persistent
  disagreement as an ordinary transaction revert (see DissensusOracle,
  ConsensusThermometer), and CLAUDE.md is explicit that inventing a new,
  unverified nondeterminism pattern is the single most expensive mistake in
  this codebase. So this contract reuses DissensusOracle's PROVEN ensemble
  trick instead, which delivers the same product (a verdict or ABSTAIN,
  never a shaky guess) through a mechanism already confirmed live:

    1. The nondet block convenes an internal ensemble of K independent
       experts and asks for (a) the option the plurality would pick, and
       (b) `commit_fraction`: the share of the K experts who would commit to
       that option rather than call the question too unclear to answer.
    2. Consensus is reached with COMPARATIVE, keyed on the option string
       AND `commit_fraction_milli` within `tolerance_milli` -- validators
       running independent ensembles (possibly different LLMs) must
       independently agree both on the leading option and on how confident
       the poll was. A question that's contested in an unstable way -- where
       even the confidence level is unclear -- fails consensus and reverts,
       exactly like DissensusOracle's dissensus measurement.
    3. Once consensus lands, a plain DETERMINISTIC comparison decides the
       stored status: `commit_fraction_milli >= abstain_threshold_milli`
       stores the leading option (verbatim, matched case-insensitively
       against the caller-supplied option list); otherwise it stores the
       literal string "ABSTAIN". A leading option that fails to match any
       caller-supplied option (a model straying off the allowed list) also
       forces ABSTAIN -- a purely deterministic defensive check, no new
       nondeterminism.

  The net behavior matches the spec's intent exactly (never a confident
  answer to an unanswerable question) while staying inside proven territory.

STATE DESIGN
  A pull-style archive identical in shape to DissensusOracle's: every
  judgment is appended to `records`, `latest` indexes the most recent one,
  `last_status` mirrors the most recent verdict/ABSTAIN for the cheap
  `did_abstain()` check the spec calls for, and `abstain_count` tracks how
  often the guard actually fired.

  `options` is accepted as a single comma-separated string, not a list --
  no contract in this repo has exercised a list-typed calldata argument, and
  this keeps the argument surface inside the proven `str`/`u256` territory
  documented in CLAUDE.md's "Storage types" section.

REUSE
  Compose in front of governance, liquidation, or moderation calls: call
  `judge(question, options)` first, then gate the real action on
  `did_abstain() == False`.
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


ABSTAIN = "ABSTAIN"


@allow_storage
@dataclass
class JudgeRecord:
    question: str
    status: str  # one of the caller's options, verbatim, or the literal ABSTAIN
    confidence_milli: u256  # fraction of the ensemble that committed to `status`


# A scale factor keeps probabilities exact on-chain. Floats are fine *inside* a
# nondet block, but state and comparisons stay integer to avoid any drift.
_MILLI = 1000


class AmbiguityGuard(gl.Contract):
    records: DynArray[JudgeRecord]
    latest: u256
    last_status: str
    abstain_count: u256
    ensemble_size: u256           # how many independent opinions to simulate
    abstain_threshold_milli: u256 # commit_fraction_milli below this -> ABSTAIN
    tolerance_milli: u256         # allowed gap between validators on commit_fraction

    def __init__(
        self,
        ensemble_size: int = 7,
        abstain_threshold_milli: int = 600,
        tolerance_milli: int = 250,
    ):
        require(3 <= ensemble_size <= 25, "ensemble_size out of range")
        require(0 < abstain_threshold_milli <= 1000, "abstain_threshold out of range")
        require(0 < tolerance_milli <= 500, "tolerance out of range")
        self.ensemble_size = u256(ensemble_size)
        self.abstain_threshold_milli = u256(abstain_threshold_milli)
        self.tolerance_milli = u256(tolerance_milli)
        self.last_status = ""
        self.abstain_count = u256(0)
        self.latest = u256(0)

    @gl.public.write
    def judge(self, question: str, options: str) -> str:
        require(len(question.strip()) > 0, "empty question")
        opts = [o.strip() for o in options.split(",") if o.strip()]
        require(len(opts) >= 2, "need at least two comma-separated options")

        # Read everything the nondet block needs into plain locals. The block may
        # not touch self/storage, so we close over these values.
        q = question.strip()
        k = int(self.ensemble_size)
        tol = int(self.tolerance_milli)
        threshold = int(self.abstain_threshold_milli)
        opts_str = ", ".join(opts)

        def opinionate() -> str:
            prompt = f"""You are convening {k} INDEPENDENT domain experts to judge a question.
Each expert reasons separately. Do not let them converge artificially.

QUESTION: {q}
OPTIONS (each expert must pick exactly one, verbatim): {opts_str}

An expert who genuinely cannot responsibly commit to one option for this
specific question should be counted as UNDECIDED rather than guessing.

Return ONLY strict JSON, no prose, no markdown:
{{
  "leading_option": "<the OPTIONS entry, verbatim, picked by the plurality>",
  "commit_fraction": <float 0..1 = fraction of the {k} experts who committed
    to leading_option rather than answering UNDECIDED>
}}
Be honest: commit_fraction near 1.0 only when the question is clear-cut given
the options; low when it is ambiguous, underspecified, or genuinely contested."""
            raw = gl.nondet.exec_prompt(prompt)
            data = parse_json_response(raw)
            leading = str(data["leading_option"]).strip()
            commit = float(data["commit_fraction"])
            commit = max(0.0, min(1.0, commit))
            commit_milli = int(round(commit * _MILLI))
            matched = next((o for o in opts if o.lower() == leading.lower()), None)
            status = matched if matched is not None and commit_milli >= threshold else ABSTAIN
            return canonical(
                {
                    "leading_option": leading,
                    "commit_fraction_milli": commit_milli,
                    "status": status,
                }
            )

        principle = (
            "The two results describe the same expert poll over the same fixed "
            "OPTIONS list. They are EQUIVALENT only if: (1) the 'leading_option' "
            "fields are the identical option string, and (2) the "
            f"'commit_fraction_milli' values differ by at most {tol}, and the "
            "'status' fields must be identical. If the leading options differ, "
            "the commit levels are far apart, or the action status differs, they "
            "are NOT equivalent."
        )
        agreed = gl.eq_principle.prompt_comparative(opinionate, principle)
        parsed = json.loads(agreed)
        leading = str(parsed["leading_option"])
        commit_milli = int(parsed["commit_fraction_milli"])
        status = str(parsed["status"])
        require(status == ABSTAIN or status in opts, "invalid status")

        # The status was part of the comparative result. Validate it against the
        # score and option list, then use that agreed category as the action.
        matched = None
        for o in opts:
            if o.lower() == leading.lower():
                matched = o
                break

        expected_status = matched if matched is not None and commit_milli >= threshold else ABSTAIN
        require(status == expected_status, "status does not match consensus score")
        if status == ABSTAIN:
            self.abstain_count = u256(int(self.abstain_count) + 1)

        rec = JudgeRecord(
            question=q, status=status, confidence_milli=u256(commit_milli)
        )
        self.records.append(rec)
        self.latest = u256(len(self.records) - 1)
        self.last_status = status
        return status

    # -- reads ----------------------------------------------------------------
    @gl.public.view
    def did_abstain(self) -> bool:
        require(len(self.records) > 0, "no judgments yet")
        return self.last_status == ABSTAIN

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
                "status": r.status,
                "confidence_milli": int(r.confidence_milli),
            }
        )

    @gl.public.view
    def status(self) -> str:
        return canonical(
            {
                "last_status": self.last_status,
                "abstain_count": int(self.abstain_count),
                "count": len(self.records),
            }
        )
