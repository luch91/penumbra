# { "Depends": "py-genlayer:5jycge4q8k23462jtb0b9fyey1s9q928sz2nbrd9mg4sxqg2qng" }
"""
PENUMBRA -- II. ASYMMETRIC RITES -- 04

PolyglotConsensus -- accepts a claim in any language and reaches agreement on
its MEANING across translations, not its exact wording.

WHY IT IS UNUSUAL
  Ordinary oracles treat a heterogeneous validator set (different LLMs, quite
  possibly with different native-language strengths) as noise to be
  suppressed. This one turns that diversity into the mechanism itself: the
  comparative principle is written to be explicitly translation-invariant, so
  validators are being asked to agree on PROPOSITION, not phrasing or source
  language. A claim submitted in Japanese and one submitted in French should
  both normalize to comparable English propositions if they assert the same
  thing, and the network's job is to confirm that convergence, not to referee
  which language is "correct".

HOW CONSENSUS IS USED
  Two different consensus moves are used for two different jobs:

  1. submit(text) -- COMPARATIVE. The nondet block does not translate
     mechanically; it asks the model to extract the single normalized-English
     PROPOSITION the source text asserts, plus a best-guess source language
     tag (informational only, never gated on). The principle instructs
     validators that two normalizations are equivalent iff they assert the
     same underlying claim, regardless of original language, wording, or
     sentence structure -- exactly the "different words, same meaning" case
     CLAUDE.md names as the canonical use of prompt_comparative. Each
     validator re-runs the normalization independently (possibly with a
     different underlying model); persistent disagreement about what a claim
     even MEANS is a genuine signal and reverts the write, same as
     DissensusOracle's philosophy.

  2. same_meaning(id_a, id_b) -- NON_COMPARATIVE, a deliberate departure from
     CONTRACTS.md's one-line spec (which only names the comparative move for
     this primitive). By the time two propositions are both already stored,
     comparing them is a different shape of problem: the input (two fixed
     English strings pulled from chain state) is byte-identical on every
     node, so there is nothing left to disagree about except whether "same
     meaning" holds. That is precisely the asymmetric-verification case
     CLAUDE.md recommends non_comparative for -- cheap to check, and it
     avoids paying for a second full translation/ensemble round just to
     compare two already-normalized strings. The leader judges; validators
     verify the judgment against explicit criteria (shared subject,
     predicate, and polarity -- not just shared topic).

STATE DESIGN
  CONTRACTS.md's spec line describes state as a bare `TreeMap[str, str]` of
  claim-hash -> normalized proposition. That alone cannot serve the API this
  contract actually exposes (`proposition_id` as a sequential handle,
  `same_meaning(id_a, id_b)` keyed on those handles) or preserve the original
  text/detected language for audit. So, like every other flagship in this
  repo, state is a pull-style archive: `propositions` is an append-only
  DynArray, `seen` is a `TreeMap[str, u256]` from SHA-256(source text) to
  1+index for O(1) dedupe (ProofCarryingAnswer's pattern), and `latest`
  indexes the most recent entry. Resubmitting byte-identical text returns the
  existing id without spending another consensus round; resubmitting the same
  MEANING in a different language is intentionally NOT deduped automatically
  -- that judgment call belongs to same_meaning(), called explicitly.

REUSE
  A language-agnostic input layer for any multilingual dApp: normalize on
  submit, then call same_meaning() to dedupe or cluster claims that arrived
  in different languages before acting on them.
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
class Proposition:
    original_text: str
    normalized: str
    detected_language: str
    text_hash: str


class PolyglotConsensus(gl.Contract):
    propositions: DynArray[Proposition]
    seen: TreeMap[str, u256]   # sha256(original_text) -> 1 + index, for dedupe
    latest: u256

    def __init__(self):
        self.latest = u256(0)

    @gl.public.write
    def submit(self, text: str) -> int:
        require(len(text.strip()) > 0, "empty text")
        t = text.strip()
        text_hash = hashlib.sha256(t.encode()).hexdigest()

        existing = int(self.seen.get(text_hash, u256(0)))
        if existing > 0:
            return existing - 1

        def normalize() -> str:
            prompt = f"""You are a precise multilingual analyst. Read the SOURCE TEXT below,
in whatever language it is written, and extract the single underlying
proposition (claim) it asserts.

SOURCE TEXT: {t}

Return ONLY strict JSON, no prose, no markdown:
{{
  "proposition": "<the claim, restated in clear, literal ENGLISH, <= 40 words,
    stripped of rhetorical flourish -- state exactly what is being asserted>",
  "detected_language": "<best-guess ISO-639-1 code or English name of the
    SOURCE TEXT's language, lowercased>"
}}
Two texts in different languages that assert the same fact must normalize to
propositions a reader would recognize as the same claim."""
            raw = gl.nondet.exec_prompt(prompt)
            data = parse_json_response(raw)
            proposition = str(data["proposition"]).strip()
            language = str(data.get("detected_language", "unknown")).strip().lower()
            require(len(proposition) > 0, "model returned empty proposition")
            # Canonicalize: stable key order so the comparative principle judges
            # a consistent structural surface across validators.
            return canonical({"proposition": proposition, "detected_language": language})

        principle = (
            "The two results are English normalizations of the SAME source text, "
            "produced independently and possibly by different models. They are "
            "EQUIVALENT only if the 'proposition' fields assert the same underlying "
            "claim -- same subject, same predicate, same polarity -- regardless of "
            "the original language, exact wording, or sentence structure. Minor "
            "phrasing differences alone do NOT make them non-equivalent. Propositions "
            "that differ in what is actually being claimed, or that disagree on true/ "
            "false, ARE non-equivalent. 'detected_language' is informational and is "
            "NOT part of the equivalence judgment."
        )
        agreed = gl.eq_principle.prompt_comparative(normalize, principle)
        parsed = json.loads(agreed)
        proposition = str(parsed["proposition"])
        language = str(parsed["detected_language"])

        prop = Proposition(
            original_text=t,
            normalized=proposition,
            detected_language=language,
            text_hash=text_hash,
        )
        self.propositions.append(prop)
        idx = len(self.propositions) - 1
        self.seen[text_hash] = u256(idx + 1)
        self.latest = u256(idx)
        return idx

    @gl.public.write
    def same_meaning(self, id_a: int, id_b: int) -> bool:
        require(0 <= id_a < len(self.propositions), "no such proposition (a)")
        require(0 <= id_b < len(self.propositions), "no such proposition (b)")
        if id_a == id_b:
            return True

        prop_a = self.propositions[id_a].normalized
        prop_b = self.propositions[id_b].normalized

        def verification_input() -> str:
            # Fully deterministic: identical on the leader and every validator,
            # since both strings are already-agreed chain state, not fresh model
            # output. The principle does the judging, not re-derivation.
            return canonical({"proposition_a": prop_a, "proposition_b": prop_b})

        task = (
            "The input JSON has 'proposition_a' and 'proposition_b', two English "
            "statements already normalized from (possibly different-language) source "
            "claims. Decide whether they assert the SAME underlying proposition. "
            "Output ONLY strict JSON: "
            '{"same_meaning": <true|false>, "confidence": <float 0..1>, '
            '"reason": "<<=20 words>"}.'
        )
        criteria = (
            "A trustworthy verdict has these properties: (1) 'same_meaning' is true "
            "ONLY if both propositions would be judged true or false together under "
            "any reasonable interpretation -- they must share subject, predicate, and "
            "polarity, not merely topic; (2) superficial overlap (same topic, "
            "different claim, different scope, different quantity) must be scored "
            "false; (3) 'confidence' reflects how clear-cut the comparison was. "
            "Reject a verdict that calls two propositions equivalent while a stated "
            "distinction in scope, quantity, or polarity is left unaddressed."
        )
        raw = gl.eq_principle.prompt_non_comparative(
            verification_input, task=task, criteria=criteria
        )
        verdict = json.loads(raw) if isinstance(raw, str) else raw
        return bool(verdict["same_meaning"])

    # -- reads ----------------------------------------------------------------
    @gl.public.view
    def count(self) -> int:
        return len(self.propositions)

    @gl.public.view
    def get(self, proposition_id: int) -> str:
        require(0 <= proposition_id < len(self.propositions), "no such proposition")
        p = self.propositions[proposition_id]
        return canonical(
            {
                "original_text": p.original_text,
                "normalized": p.normalized,
                "detected_language": p.detected_language,
                "text_hash": p.text_hash,
            }
        )

    @gl.public.view
    def id_for_text(self, text: str) -> int:
        """Dedupe lookup: -1 if this exact source text has never been submitted."""
        digest = hashlib.sha256(text.strip().encode()).hexdigest()
        existing = int(self.seen.get(digest, u256(0)))
        return existing - 1
