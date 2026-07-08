# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""
PENUMBRA -- VIII. MARKETS OF MEANING -- 20

RealitySettledMarket -- a binary (YES/NO) market that settles itself from
primary web sources, and REFUNDS everyone rather than guess when those
sources do not clearly determine the answer.

WHY IT IS UNUSUAL
  A prediction market is only as trustworthy as its oracle, and the usual
  failure mode is a confidently-wrong settlement on a question reality never
  actually answered. This market treats "the sources don't agree" as a
  first-class outcome, not an edge case: when the resolution sources conflict
  or are too weak to determine YES vs NO, it settles to REFUND and returns
  every bettor's own stake, instead of flipping a coin and paying one side
  from the other. It would rather unwind the market than launder ambiguity as
  a verdict. This is the last primitive in the catalog and it composes two
  patterns already proven live elsewhere in this repo:
    * the ambiguity guard (AmbiguityGuard): a confidence measurement that
      converts "not safe to answer" into an explicit abstain, here REFUND;
    * the guarded web fetch (CorroborationOracle / SemanticDeadman): every
      source URL is fetched inside try/except so one dead source degrades the
      evidence rather than aborting the settlement.

HOW CONSENSUS IS USED
  `settle()`'s non-deterministic block fetches every resolution URL (each in
  its own try/except -- see the fetch-guard note below), then asks the model
  to judge whether the market question resolves YES or NO given what the
  sources actually say, AND to report a confidence: how strongly the sources
  DETERMINE that outcome (near 1.0 only when sources are clear and agree; low
  when they conflict, are silent, or failed to load). Consensus uses the
  COMPARATIVE principle keyed on BOTH the outcome string and
  `confidence_milli` (within tolerance): validators each independently
  re-fetch the same URLs (passed via stored state, identical on every node)
  and re-judge, so agreement requires both that the sources point the same way
  AND that the validators agree on how clearly they do. Once consensus lands,
  a plain DETERMINISTIC gate decides settlement: an outcome of YES or NO whose
  `confidence_milli` clears `abstain_threshold_milli` settles that way;
  anything else -- an UNCLEAR outcome, or a genuine YES/NO whose confidence is
  below threshold -- collapses to REFUND. This is exactly AmbiguityGuard's
  proven "measure the confidence, then decide deterministically" shape, reused
  for a market instead of a lone judgment.

STATE & MONEY DESIGN
  Bets are an append-only `DynArray[Bet]`, each carrying its bettor, side, and
  staked value; `yes_pool` / `no_pool` track the running totals so reads are
  cheap. At settlement the payout is credited to a PULL-payment ledger
  (`claimable`, drained by `redeem()`) -- the same pattern SchellingResolver
  uses, never pushing native value from inside the settle path:
    * YES or NO wins: the WHOLE pool (yes_pool + no_pool) is split across the
      winning-side bettors in proportion to each one's stake. Integer floor
      division means the sum credited never exceeds the pool (any sub-unit
      dust stays locked rather than risking an over-payment -- the ledger is
      the authority, and it can only under-credit, never over-credit).
    * REFUND: every bettor is credited exactly their own stake back.
  DEGENERATE-MARKET GUARD: if the judged winning side has an empty pool (e.g.
  everyone bet YES but reality resolved NO, so no one is on the winning side),
  there is no winner to pay and the outcome is overridden to REFUND -- keeping
  the invariant "stored outcome == REFUND if and only if everyone got their
  own stake back" exact.

DEVIATIONS FROM THE LITERAL CATALOG SPEC
  `resolution_urls` is a single comma-separated string, not a list -- no
  contract in this repo has exercised a list-typed calldata argument (see
  CorroborationOracle's `urls` and AmbiguityGuard's `options` for the
  precedent; comma is safe since URLs contain none). The spec's `outcome enum`
  is stored as a canonical `str` ("", "YES", "NO", "REFUND"), since this runner
  has no native enum storage type.

REUSE
  Self-resolving prediction markets, parametric insurance / event escrows, any
  binary payout that must settle from primary sources but must refuse to pay
  out on a question reality left genuinely unsettled.

## Runner verification
  This is a NEW call site for `gl.nondet.web.render(url, mode="text")` -- the
  surface is confirmed live in SemanticDeadman, CorroborationOracle,
  ProvenanceAttestor, and CanaryTripwire, but per CLAUDE.md each new call site
  is re-verified rather than assumed. A fetch failure (dead domain, DNS
  failure, disallowed TLD) raises an uncaught `NondetException` instead of
  returning content, so every `render()` here is wrapped in try/except inside
  the nondet closure: a bad URL degrades that source to "[FETCH FAILED]" (which
  the prompt is told counts AGAINST a confident outcome, pushing toward REFUND)
  rather than aborting settlement. If `settle()` reverts with a raw Python
  traceback instead of a clean `require()` message, check whether the
  `render()` return shape or the fetch-failure exception type has changed.
  `bet()` is `@gl.public.write.payable`; recall `genlayer write` (CLI v0.39.2)
  cannot send value (hardcodes value: 0n), so the real bet/settle/redeem money
  path is exercised via gltest's `.transact(value=N)`, not the raw CLI.
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


YES = "YES"
NO = "NO"
REFUND = "REFUND"
UNSETTLED = ""

# A scale factor keeps confidences exact on-chain. Floats are fine *inside* a
# nondet block, but state and comparisons stay integer to avoid any drift.
_MILLI = 1000


@allow_storage
@dataclass
class Bet:
    bettor: Address
    side: str  # YES or NO, verbatim
    stake: u256


class RealitySettledMarket(gl.Contract):
    question: str
    resolution_urls: str          # comma-separated; identical on every validator
    yes_pool: u256
    no_pool: u256
    outcome: str                  # UNSETTLED / YES / NO / REFUND
    confidence_milli: u256        # confidence recorded at settlement
    bets: DynArray[Bet]
    claimable: TreeMap[Address, u256]
    abstain_threshold_milli: u256  # confidence below this -> REFUND
    tolerance_milli: u256          # allowed gap between validators on confidence

    def __init__(
        self,
        question: str,
        resolution_urls: str,
        abstain_threshold_milli: int = 600,
        tolerance_milli: int = 250,
    ):
        q = (question if isinstance(question, str) else "").strip()
        raw_urls = resolution_urls if isinstance(resolution_urls, str) else ""
        url_list = [u.strip() for u in raw_urls.split(",") if u.strip()]
        require(len(q) > 0, "empty question")
        require(2 <= len(url_list) <= 8, "need 2 to 8 comma-separated resolution urls")
        require(0 < abstain_threshold_milli <= 1000, "abstain_threshold out of range")
        require(0 < tolerance_milli <= 500, "tolerance out of range")
        self.question = q
        self.resolution_urls = ",".join(url_list)
        self.abstain_threshold_milli = u256(abstain_threshold_milli)
        self.tolerance_milli = u256(tolerance_milli)
        self.yes_pool = u256(0)
        self.no_pool = u256(0)
        self.outcome = UNSETTLED
        self.confidence_milli = u256(0)

    # -- betting -------------------------------------------------------------
    @gl.public.write.payable
    def bet(self, side: str) -> int:
        require(self.outcome == UNSETTLED, "market already settled")
        s = (side if isinstance(side, str) else "").strip().upper()
        require(s in (YES, NO), "side must be YES or NO")
        stake = int(gl.message.value)
        require(stake > 0, "stake required")

        self.bets.append(
            Bet(bettor=gl.message.sender_address, side=s, stake=u256(stake))
        )
        if s == YES:
            self.yes_pool = u256(int(self.yes_pool) + stake)
        else:
            self.no_pool = u256(int(self.no_pool) + stake)
        return len(self.bets) - 1

    # -- settlement ----------------------------------------------------------
    @gl.public.write
    def settle(self) -> str:
        require(self.outcome == UNSETTLED, "already settled")
        require(len(self.bets) > 0, "no bets to settle")

        # Pull everything the nondet block needs into locals; it may not touch
        # self/storage.
        q = self.question
        url_list = [u for u in self.resolution_urls.split(",") if u]
        total_sources = len(url_list)
        tol = int(self.tolerance_milli)

        def judge() -> str:
            source_parts = []
            for i, u in enumerate(url_list):
                # VERIFY: gl.nondet.web.render shape/failure mode -- new call
                # site here (see "## Runner verification"). A fetch failure
                # raises rather than returning content, so it is caught and
                # rendered as a failed source that counts against confidence,
                # never aborting the whole settle() transaction.
                try:
                    content = gl.nondet.web.render(u, mode="text")
                    snippet = content[:3000] if content else "[EMPTY PAGE]"
                except Exception as e:
                    snippet = f"[FETCH FAILED: {e}]"[:200]
                source_parts.append(f"SOURCE {i + 1} ({u}):\n---\n{snippet}\n---")
            sources_block = "\n\n".join(source_parts)

            prompt = f"""You are settling a binary YES/NO market from primary sources.

QUESTION (resolves YES or NO): {q}

There are {total_sources} sources below. A source that failed to fetch or is
empty determines NOTHING and must lower your confidence, not be ignored.

{sources_block}

Decide whether the sources resolve the question YES or NO, and how strongly
they DETERMINE that answer. If the sources conflict with each other, are
silent on the question, or are too weak to settle it, say so with a LOW
confidence and outcome "UNCLEAR" -- do not guess a side to seem decisive.

Return ONLY strict JSON, no prose, no markdown:
{{
  "outcome": "YES" | "NO" | "UNCLEAR",
  "confidence": <float 0..1 = how strongly the sources determine the outcome>
}}"""
            raw = gl.nondet.exec_prompt(prompt)
            data = parse_json_response(raw)
            out = str(data["outcome"]).strip().upper()
            if out not in (YES, NO):
                out = "UNCLEAR"
            conf = float(data["confidence"])
            conf = max(0.0, min(1.0, conf))
            # Canonicalize: integer milli-units so strict structural fields match
            # and the comparative principle has a stable surface to judge.
            return canonical(
                {"outcome": out, "confidence_milli": int(round(conf * _MILLI))}
            )

        principle = (
            "Both results settle the same YES/NO market from the same fixed set "
            "of sources. They are EQUIVALENT if and only if: (1) the 'outcome' "
            "fields are the identical token (YES, NO, or UNCLEAR), and (2) the "
            f"'confidence_milli' values differ by at most {tol}. If the outcomes "
            "differ, or the confidences are far apart, they are NOT equivalent."
        )
        agreed = gl.eq_principle.prompt_comparative(judge, principle)
        parsed = json.loads(agreed)
        judged = str(parsed["outcome"]).strip().upper()
        conf_milli = int(parsed["confidence_milli"])

        # Deterministic settlement gate -- consensus on (outcome, confidence)
        # is already reached; no ambiguity remains here. Anything that is not a
        # confident YES/NO becomes REFUND.
        if judged in (YES, NO) and conf_milli >= int(self.abstain_threshold_milli):
            final = judged
        else:
            final = REFUND

        yes_total = int(self.yes_pool)
        no_total = int(self.no_pool)
        pool = yes_total + no_total
        win_pool = yes_total if final == YES else (no_total if final == NO else 0)

        # Degenerate-market guard: a judged winner with no stake on its side has
        # no one to pay -> fall back to REFUND so the outcome/payout invariant
        # stays exact.
        if final in (YES, NO) and win_pool == 0:
            final = REFUND

        if final == REFUND:
            for i in range(len(self.bets)):
                b = self.bets[i]
                self.claimable[b.bettor] = u256(
                    int(self.claimable.get(b.bettor, u256(0))) + int(b.stake)
                )
        else:
            for i in range(len(self.bets)):
                b = self.bets[i]
                if b.side == final:
                    payout = (int(b.stake) * pool) // win_pool
                    self.claimable[b.bettor] = u256(
                        int(self.claimable.get(b.bettor, u256(0))) + payout
                    )

        self.outcome = final
        self.confidence_milli = u256(conf_milli)
        return final

    # -- disbursement (pull pattern) -----------------------------------------
    @gl.public.write
    def redeem(self) -> int:
        require(self.outcome != UNSETTLED, "not settled yet")
        who = gl.message.sender_address
        owed = int(self.claimable.get(who, u256(0)))
        require(owed > 0, "nothing to redeem")
        self.claimable[who] = u256(0)
        # INTEGRATION HOOK: disburse native GEN/ERC-20 `owed` to `who` here; the
        # internal ledger above is authoritative and already debited.
        return owed

    # -- reads ---------------------------------------------------------------
    @gl.public.view
    def count(self) -> int:
        return len(self.bets)

    @gl.public.view
    def get(self, index: int) -> str:
        require(0 <= index < len(self.bets), "no such bet")
        b = self.bets[index]
        return canonical(
            {
                "bettor": b.bettor.as_hex,
                "side": b.side,
                "stake": int(b.stake),
            }
        )

    @gl.public.view
    def is_settled(self) -> bool:
        return self.outcome != UNSETTLED

    @gl.public.view
    def settled_outcome(self) -> str:
        require(self.outcome != UNSETTLED, "not settled yet")
        return self.outcome

    @gl.public.view
    def claimable_of(self, who: Address) -> int:
        # `who` may already arrive as a native Address (address-shaped calldata
        # is auto-decoded regardless of a `str` type hint) -- wrapping an
        # already-Address value in Address(...) crashes on this runner.
        addr = who if isinstance(who, Address) else Address(who)
        return int(self.claimable.get(addr, u256(0)))

    @gl.public.view
    def status(self) -> str:
        return canonical(
            {
                "question": self.question,
                "resolution_urls": self.resolution_urls,
                "yes_pool": int(self.yes_pool),
                "no_pool": int(self.no_pool),
                "outcome": self.outcome,
                "confidence_milli": int(self.confidence_milli),
                "bets": len(self.bets),
            }
        )
