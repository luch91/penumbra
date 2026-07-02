# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""
PENUMBRA -- VI. REFLEXION -- 15

ConsensusThermometer -- predicts whether validators would agree before paying
for an expensive decision, and routes to a fallback when they would not.

WHY IT IS UNUSUAL
  Every other Penumbra primitive spends a full consensus round to reach an
  answer, then reports how contested it was after the fact (see
  DissensusOracle). This one measures upfront, cheaply, whether a full round
  is even worth running. It never performs the real expensive analysis --
  it asks the model to introspect on a downsampled version of the task and
  predict its own eventual agreement. High predicted agreement unlocks the
  caller to go run the real (expensive) decision elsewhere; low predicted
  agreement routes to DEFERRED, signalling "don't bother yet, this needs a
  human or an appeal path instead". It is a cost-control primitive built out
  of the same self-knowledge trick DissensusOracle uses for the opposite
  purpose.

HOW CONSENSUS IS USED
  The non-deterministic block never runs the actual analysis -- it only asks
  the model to ESTIMATE how likely independent experts would agree on one,
  given a short read of the task. That estimate is a single float,
  `predicted_agreement`, canonicalized to milli-units.

  Consensus is reached with the COMPARATIVE equivalence principle: every
  validator runs its own independent estimate, and the principle requires
  the milli-unit values to land within `tolerance_milli` of each other. If
  even the *prediction* can't reach consensus, that failure propagates as an
  ordinary revert -- callers should treat a revert here the same as a
  DEFERRED route (something about this task resists exportable judgment).

  The FULL/DEFERRED routing decision itself is a plain deterministic integer
  comparison against `threshold_milli`, run after consensus has already
  settled on the predicted_agreement_milli value -- no further ambiguity
  once the nondet block returns.

STATE DESIGN
  A pull-style archive identical in shape to DissensusOracle's: every probe
  is appended to `probes` so the routing history is a queryable on-chain
  corpus (useful for auditing whether the threshold is well-calibrated over
  time). `latest` indexes the most recent probe. `task_hash` (sha256, taken
  deterministically outside the nondet block) is stored instead of the raw
  task text to keep records compact and to give callers a stable handle for
  correlating a probe with the task that triggered it, without re-storing
  potentially large task text on every call.

REUSE
  Wrap any consensus-heavy pipeline (DissensusOracle, ProofCarryingAnswer,
  SchellingResolver, or an external one) with `assess(task)` first; only pay
  for the real round when the route comes back FULL.
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


@allow_storage
@dataclass
class Probe:
    task_hash: str
    predicted_agreement_milli: u256
    routed_to: str


# A scale factor keeps probabilities exact on-chain. Floats are fine *inside* a
# nondet block, but state and comparisons stay integer to avoid any drift.
_MILLI = 1000


class ConsensusThermometer(gl.Contract):
    probes: DynArray[Probe]
    latest: u256
    threshold_milli: u256    # predicted_agreement_milli >= this routes to FULL
    tolerance_milli: u256    # allowed gap between validators' predicted_agreement

    def __init__(self, threshold_milli: int = 700, tolerance_milli: int = 200):
        require(0 < threshold_milli <= 1000, "threshold out of range")
        require(0 < tolerance_milli <= 500, "tolerance out of range")
        self.threshold_milli = u256(threshold_milli)
        self.tolerance_milli = u256(tolerance_milli)
        self.latest = u256(0)

    @gl.public.write
    def assess(self, task: str) -> str:
        require(len(task.strip()) > 0, "empty task")
        t = task.strip()
        # Deterministic and identical on every validator -- safe outside the
        # nondet block, unlike anything that touches an LLM or the network.
        task_hash = hashlib.sha256(t.encode()).hexdigest()
        tol = int(self.tolerance_milli)

        def probe() -> str:
            prompt = f"""You are a fast, cheap TRIAGE step, not the real analysis. Do NOT solve
the task below. Only predict how likely a panel of independent expert
validators would be to AGREE on an answer if they each analyzed it in full.

TASK: {t}

Consider: is this task factual and well-posed (agreement likely), or
subjective, ambiguous, or contested (agreement unlikely)? Base your estimate
on the nature of the task, not on solving it.

Return ONLY strict JSON, no prose, no markdown:
{{
  "predicted_agreement": <float 0..1, your estimate of the fraction of
    independent experts who would converge on the same answer>,
  "rationale": "<why, <= 20 words>"
}}"""
            raw = gl.nondet.exec_prompt(prompt)
            data = parse_json_response(raw)
            predicted = float(data["predicted_agreement"])
            predicted = max(0.0, min(1.0, predicted))
            # Canonicalize: integer milli-units so the comparative principle has
            # a stable, exact surface to judge (see NON-DETERMINISM rule 3).
            return canonical(
                {"predicted_agreement_milli": int(round(predicted * _MILLI))}
            )

        principle = (
            "The two results are estimates of how likely independent experts would "
            "agree on the same task. They are EQUIVALENT only if the "
            f"'predicted_agreement_milli' values differ by at most {tol}."
        )
        agreed = gl.eq_principle.prompt_comparative(probe, principle)
        parsed = json.loads(agreed)
        predicted_milli = int(parsed["predicted_agreement_milli"])

        # Deterministic routing decision -- no ambiguity left once consensus on
        # predicted_agreement_milli has already been reached above.
        route = "FULL" if predicted_milli >= int(self.threshold_milli) else "DEFERRED"

        rec = Probe(
            task_hash=task_hash,
            predicted_agreement_milli=u256(predicted_milli),
            routed_to=route,
        )
        self.probes.append(rec)
        self.latest = u256(len(self.probes) - 1)
        return route

    # -- reads ----------------------------------------------------------------
    @gl.public.view
    def count(self) -> int:
        return len(self.probes)

    @gl.public.view
    def get(self, probe_id: int) -> str:
        require(0 <= probe_id < len(self.probes), "no such probe")
        p = self.probes[probe_id]
        return canonical(
            {
                "task_hash": p.task_hash,
                "predicted_agreement_milli": int(p.predicted_agreement_milli),
                "routed_to": p.routed_to,
            }
        )

    @gl.public.view
    def last_probe(self) -> str:
        require(len(self.probes) > 0, "no probes yet")
        return self.get(int(self.latest))
