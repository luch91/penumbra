# { "Depends": "py-genlayer:5jycge4q8k23462jtb0b9fyey1s9q928sz2nbrd9mg4sxqg2qng" }
"""
PENUMBRA -- V. CORROBORATION -- 12

CorroborationOracle -- accepts a fact only when independent web sources agree
on it, and publishes the corroboration ratio alongside the value.

WHY IT IS UNUSUAL
  A single-source oracle is only as honest as the one page it reads. This
  contract instead treats corroboration itself as the product: it fetches N
  caller-named sources, asks the network to extract what each source says
  about a question, and only accepts a value when enough of those sources
  agree. Sources that disagree drag the ratio below the caller's threshold
  and the write reverts -- the oracle would rather say nothing than launder
  a single source's claim as consensus.

HOW CONSENSUS IS USED
  The non-deterministic block fetches every source URL, asks the model to
  extract, per source, what value it supports for the question, and to
  report how many of the sources AGREE with the plurality value. Consensus
  is reached with the COMPARATIVE principle: every validator independently
  re-fetches the same URLs (passed as arguments, so identical on every node)
  and re-extracts, so agreement on `value` and `ratio_milli` (to within
  tolerance) requires INDEPENDENT corroboration across BOTH axes -- the
  sources must agree with each other, AND the validators must agree that
  they do. Once that consensus lands, a plain DETERMINISTIC comparison
  decides whether `ratio_milli` clears the caller's `threshold_milli`; if it
  does not, the write reverts rather than storing a low-confidence fact.

STATE DESIGN
  A pull-style append-only archive identical in shape to DissensusOracle's:
  every accepted fact is appended to `facts`, `latest` indexes the most
  recent one. Nothing is stored for a corroboration attempt that fails the
  threshold -- the deterministic require() reverts before any append.

DEVIATIONS FROM THE LITERAL CATALOG SPEC
  `urls` is accepted as a single comma-separated string, not a list -- no
  contract in this repo has exercised a list-typed calldata argument (see
  AmbiguityGuard's `options` for the precedent). Comma is safe here since
  URLs do not contain commas, unlike ConstitutionalContract's `|`-delimited
  `core_principles`, which chose a different delimiter because principles
  are full sentences that may contain commas.

REUSE
  Price/score/event oracles that must not trust a single endpoint; any
  on-chain fact that should only be recorded when multiple independent
  primary sources say the same thing.

## Runner verification
  This is a NEW call site for `gl.nondet.web.render(url, mode="text")` --
  the surface was first confirmed live in `SemanticDeadman.poke()`, but each
  new call site should be re-verified rather than assumed. A fetch failure
  (dead domain, DNS failure, disallowed TLD) raises an uncaught
  `NondetException` instead of returning content -- confirmed live in
  SemanticDeadman via a deliberately dead URL. The per-source fetch here is
  wrapped in `try/except` inside the nondet closure for exactly that reason:
  one bad URL among several must degrade that source's evidence, not abort
  the whole transaction. If `establish()` reverts with a raw Python
  exception instead of a clean `require()` message, check whether the
  `render()` return shape or the fetch-failure exception type has changed.
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
class Fact:
    question: str
    value: str
    ratio_milli: u256
    sources_count: u256


# A scale factor keeps ratios exact on-chain. Floats are fine *inside* a
# nondet block, but state and comparisons stay integer to avoid any drift.
_MILLI = 1000


class CorroborationOracle(gl.Contract):
    facts: DynArray[Fact]
    latest: u256
    threshold_milli: u256   # minimum ratio_milli required to accept and store
    tolerance_milli: u256   # allowed gap between validators on ratio_milli

    def __init__(self, threshold_milli: int = 700, tolerance_milli: int = 200):
        require(0 < threshold_milli <= 1000, "threshold out of range")
        require(0 < tolerance_milli <= 500, "tolerance out of range")
        self.threshold_milli = u256(threshold_milli)
        self.tolerance_milli = u256(tolerance_milli)
        self.latest = u256(0)

    @gl.public.write
    def establish(self, question: str, urls: str) -> str:
        q = (question if isinstance(question, str) else "").strip()
        require(len(q) > 0, "empty question")
        raw_urls = urls if isinstance(urls, str) else ""
        url_list = [u.strip() for u in raw_urls.split(",") if u.strip()]
        require(2 <= len(url_list) <= 8, "need 2 to 8 comma-separated urls")

        # Read everything the nondet block needs into plain locals. The block may
        # not touch self/storage, so we close over these values.
        tol = int(self.tolerance_milli)
        threshold = int(self.threshold_milli)
        total = len(url_list)

        def corroborate() -> str:
            sources_block_parts = []
            for i, u in enumerate(url_list):
                # VERIFY: gl.nondet.web.render shape/failure mode is a new call
                # site here -- see "## Runner verification" in the module
                # docstring. A fetch failure raises rather than returning
                # content (confirmed elsewhere in this repo via
                # gl.nondet.NondetException), so it is caught explicitly and
                # treated as unsupportive evidence rather than aborting the
                # whole establish() transaction.
                try:
                    content = gl.nondet.web.render(u, mode="text")
                    snippet = content[:3000] if content else "[EMPTY PAGE]"
                except Exception as e:
                    snippet = f"[FETCH FAILED: {e}]"[:200]
                sources_block_parts.append(
                    f"SOURCE {i + 1} ({u}):\n---\n{snippet}\n---"
                )
            sources_block = "\n\n".join(sources_block_parts)

            prompt = f"""You are corroborating a fact across INDEPENDENT web sources.

QUESTION: {q}

There are {total} sources below. A source that failed to fetch or is empty
supports NO value and must count against agreement, not be ignored.

{sources_block}

Determine the single value the PLURALITY of sources supports as the answer to
the question (a short phrase, not a sentence). Then count how many of the
{total} sources actually support that plurality value (a failed/empty source
never counts as supporting).

Return ONLY strict JSON, no prose, no markdown:
{{ "value": "<short plurality value>", "agreeing_count": <int 0..{total}> }}"""
            raw = gl.nondet.exec_prompt(prompt)
            data = parse_json_response(raw)
            value = str(data["value"]).strip()
            agreeing = int(data["agreeing_count"])
            agreeing = max(0, min(total, agreeing))
            ratio_milli = (agreeing * _MILLI) // total
            accepted = ratio_milli >= threshold
            return canonical(
                {
                    "value": value,
                    "ratio_milli": ratio_milli,
                    "sources_count": total,
                    "accepted": accepted,
                }
            )

        principle = (
            "The two results corroborate the same question across the same "
            "fixed set of sources. They are EQUIVALENT if and only if: (1) the "
            "'value' fields mean the same thing (synonyms and paraphrases are "
            f"fine), and (2) the 'ratio_milli' values differ by at most {tol}, "
            "and the 'accepted' fields must be identical. If the values disagree, "
            "the ratios are far apart, or the acceptance decision differs, they are "
            "NOT equivalent."
        )
        agreed = gl.eq_principle.prompt_comparative(corroborate, principle)
        parsed = json.loads(agreed)

        value = str(parsed["value"])
        ratio_milli = int(parsed["ratio_milli"])
        sources_count = int(parsed["sources_count"])
        accepted = bool(parsed["accepted"])
        expected_accepted = ratio_milli >= threshold
        require(accepted == expected_accepted, "acceptance does not match ratio")
        require(accepted, "insufficient corroboration across sources")

        self.facts.append(
            Fact(
                question=q,
                value=value,
                ratio_milli=u256(ratio_milli),
                sources_count=u256(sources_count),
            )
        )
        self.latest = u256(len(self.facts) - 1)
        return value

    # -- reads ----------------------------------------------------------------
    @gl.public.view
    def count(self) -> int:
        return len(self.facts)

    @gl.public.view
    def get(self, fact_id: int) -> str:
        require(0 <= fact_id < len(self.facts), "no such fact")
        f = self.facts[fact_id]
        return canonical(
            {
                "question": f.question,
                "value": f.value,
                "ratio_milli": int(f.ratio_milli),
                "sources_count": int(f.sources_count),
            }
        )

    @gl.public.view
    def latest_fact(self) -> str:
        require(len(self.facts) > 0, "no facts yet")
        return self.get(int(self.latest))
