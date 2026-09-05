# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""
PENUMBRA -- III. SEMANTIC MACHINES -- 07

SemanticDiffLedger -- a versioned document where the unit of change is
MEANING, not bytes. A proposed edit only bumps the version if consensus
judges it materially different from the current text; a typo fix, a
reformat, or a rephrasing that preserves the same obligations is treated as
a no-op, not a new version.

WHY IT IS UNUSUAL
  Ordinary version control (and ordinary on-chain document registries) treat
  every byte-diff as a new version, which makes the changelog noisy and
  makes "what actually changed" a manual reading exercise. This primitive
  inverts that: it asks the network to judge substance, not syntax. Two
  texts that differ in every character but assert the same rights,
  obligations, and scope are the SAME version here; two texts that differ by
  one clause but change who owes what are a NEW version.

HOW CONSENSUS IS USED
  `current` (already-agreed chain state) and `new_text` (fresh calldata) are
  both deterministic and identical on every validator, but the JUDGMENT of
  whether they differ materially is not mechanical -- it is exactly the kind
  of genuinely interpretive call DissensusOracle's philosophy is built
  around. So this uses the COMPARATIVE equivalence principle, not
  non_comparative: each validator independently judges "materially
  different?" over the same fixed (current, new_text) pair, and the
  principle requires validators to agree on the verdict and on how
  confident the call was, within a tolerance -- the same milli-unit
  integer-tolerance idiom used throughout this repo (see DissensusOracle,
  PolyglotConsensus). A materiality call that's contested in an unstable
  way -- where even different LLMs can't converge on whether a change
  matters -- fails consensus and reverts, exactly like an ordinary
  prompt_comparative disagreement elsewhere in this repo. That failure is
  itself meaningful: a document edit whose materiality is genuinely unclear
  should not silently land as either accepted or ignored.

  Once consensus lands: a MATERIAL verdict updates `current`, appends a
  snapshot, and bumps the version -- a plain deterministic sequence with no
  further ambiguity. A COSMETIC verdict changes nothing at all: `current`
  stays exactly as it was, no snapshot is appended, and `propose()` returns
  false. The proposed cosmetic text is not silently merged in; only the
  network's own explicit consensus that a change occurred is allowed to
  change chain state.

STATE DESIGN
  `snapshots` is a pull-style, append-only `DynArray[Snapshot]` archive; the
  constructor seeds it with the initial text as version 0 (genesis), so
  `snapshot(v)` can always answer "what did version v actually say" without
  needing `current` to be re-derived. `doc_version` (not `version`, to avoid
  colliding with the `version()` read method -- the same
  state-field/method-name split already used for `last_status`/`status()`
  in AmbiguityGuard) tracks the current version number. `current` mirrors
  the text of the latest snapshot for O(1) access without an index lookup.

REUSE
  On-chain changelogs, license/terms tracking, or spec governance: propose
  edits freely, and let the network's own judgment of materiality decide
  what counts as a real revision worth recording.
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
class Snapshot:
    doc_version: u256
    text: str


# A scale factor keeps probabilities exact on-chain. Floats are fine *inside* a
# nondet block, but state and comparisons stay integer to avoid any drift.
_MILLI = 1000


class SemanticDiffLedger(gl.Contract):
    current: str
    snapshots: DynArray[Snapshot]
    doc_version: u256
    tolerance_milli: u256   # allowed gap between validators' confidence

    def __init__(self, initial_text: str = "", tolerance_milli: int = 250):
        t = (initial_text if isinstance(initial_text, str) else "").strip()
        require(len(t) > 0, "empty initial text")
        require(0 < tolerance_milli <= 500, "tolerance out of range")
        self.current = t
        self.doc_version = u256(0)
        self.tolerance_milli = u256(tolerance_milli)
        self.snapshots.append(Snapshot(doc_version=u256(0), text=t))

    @gl.public.write
    def propose(self, new_text: str) -> bool:
        # Empty-string calldata args can decode as a non-str type on this
        # runner (confirmed live in IntentLock) -- coerce defensively.
        nt = (new_text if isinstance(new_text, str) else "").strip()
        require(len(nt) > 0, "empty proposed text")

        old = self.current
        tol = int(self.tolerance_milli)

        def judge() -> str:
            prompt = f"""You are auditing a proposed edit to a living document for whether it is
a MATERIAL change or a COSMETIC one.

CURRENT TEXT: {old}

PROPOSED TEXT: {nt}

A change is MATERIAL if it alters any right, obligation, party, amount,
scope, deadline, or outcome that a reader would rely on. A change is
COSMETIC if it only affects wording, formatting, grammar, or emphasis
without changing what the text actually commits anyone to.

Return ONLY strict JSON, no prose, no markdown:
{{
  "material": <true|false>,
  "confidence": <float 0..1 = how clear-cut this call is>
}}"""
            raw = gl.nondet.exec_prompt(prompt)
            data = parse_json_response(raw)
            material = bool(data["material"])
            confidence = max(0.0, min(1.0, float(data.get("confidence", 0.0))))
            # Canonicalize: integer milli-units so the comparative principle has
            # a stable, exact surface to judge (see NON-DETERMINISM rule 3).
            return canonical(
                {"material": material, "confidence_milli": int(round(confidence * _MILLI))}
            )

        principle = (
            "The two results judge whether the SAME proposed edit (fixed CURRENT "
            "and PROPOSED text, identical on every validator) is a material or "
            "cosmetic change, produced independently and possibly by different "
            "models. They are EQUIVALENT only if the 'material' fields match, and "
            f"the 'confidence_milli' values differ by at most {tol}. If one "
            "validator calls it material and another calls it cosmetic, or the "
            "confidence levels are far apart, they are NOT equivalent."
        )
        agreed = gl.eq_principle.prompt_comparative(judge, principle)
        parsed = json.loads(agreed)
        material = bool(parsed["material"])

        if not material:
            # Cosmetic: nothing changes. The proposed text is not merged in --
            # only an explicit MATERIAL verdict is allowed to mutate state.
            return False

        self.current = nt
        self.doc_version = u256(int(self.doc_version) + 1)
        self.snapshots.append(Snapshot(doc_version=self.doc_version, text=nt))
        return True

    # -- reads ------------------------------------------------------------------
    @gl.public.view
    def version(self) -> int:
        return int(self.doc_version)

    @gl.public.view
    def get_current(self) -> str:
        return self.current

    @gl.public.view
    def count(self) -> int:
        return len(self.snapshots)

    @gl.public.view
    def snapshot(self, v: int) -> str:
        require(0 <= v < len(self.snapshots), "no such version")
        s = self.snapshots[v]
        return canonical({"version": int(s.doc_version), "text": s.text})
