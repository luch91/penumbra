# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""
PENUMBRA -- VII. CHRONOMANCY -- 18

SemanticDeadman -- a dead-man's switch that releases on genuine SEMANTIC
inactivity, not a missed timestamp ping.

WHY IT IS UNUSUAL
  A mechanical dead-man's switch only knows one fact: did check_in() get
  called before a deadline. That is trivially wrong for its real purpose --
  someone can be alive and simply forget to click a button, or a script can
  fake a heartbeat forever. This contract instead points at a real public
  activity source (a profile, a feed, a repo) and asks the network to judge
  whether there is genuine, ongoing public activity there. The switch only
  releases when consensus agrees the person has actually gone dark.

HOW CONSENSUS IS USED
  `poke()`'s non-deterministic block fetches the liveness source and asks the
  model to decide, given the last confirmed-alive activity snapshot and the
  policy the owner stated at deploy time, whether the source shows genuine
  activity that has visibly advanced since then. Consensus uses the
  COMPARATIVE principle on an action-bound `outcome` category and the next
  baseline. Every validator independently re-fetches the source and
  re-judges. A release requires agreement on `INACTIVE`, while `ACTIVE`
  requires agreement on the factual meaning of the new baseline. A fetch
  failure is a separate `FETCH_FAILED` outcome and cannot release funds.

  ASSUMPTION (forced by a live-confirmed runner gap, documented in DECISIONS.md
  2026-07-01): CONTRACTS.md's one-liner spec names a `last_alive_ts` field, and
  the SDK's published API text documents `gl.message.datetime: str`. Neither
  exists to lean on here -- a live isolation deploy on this pinned runner proved
  `gl.message` exposes only `chain_id`, `contract_address`, `origin_address`,
  `sender_address`, and `value`; accessing `.datetime` raises
  `AttributeError: 'MessageType' object has no attribute 'datetime'`. There is
  NO clock, timestamp, or block-number accessor available at all on this
  runner. So this contract cannot and does not track elapsed time. Instead,
  "alive" is judged purely by CONTENT DIFFING: the last confirmed-alive check
  stores a short LLM-produced description of the activity it observed (a
  snapshot), and each `poke()` asks the model whether the freshly fetched
  source shows genuine activity that has visibly ADVANCED since that snapshot
  -- not whether a clock has ticked. The snapshot is returned as the
  consensus-bound `baseline` and cannot be replaced by an unverified validator
  output. This is arguably a better fit for "semantic
  inactivity, not a missed timestamp ping" than a timestamp comparison would
  have been anyway.

STATE & MONEY DESIGN
  A single escrowed treasury (funded via a separate payable `fund()`, matching
  the pattern in JailbreakBounty/SchellingResolver) that flips exactly once
  from owner-controlled to beneficiary-claimable. `check_in()` is the cheap
  deterministic path -- the owner can always reset the switch directly, no LLM
  call needed. `poke()` is the expensive semantic path -- anyone can call it
  (so the beneficiary isn't dependent on the owner's cooperation), and it only
  moves state when consensus agrees on the `INACTIVE` category. `FETCH_FAILED`
  leaves the treasury, release flag, claimable balance, and baseline unchanged.
  Release uses the PULL pattern: `claim()` withdraws separately from `poke()`.

REUSE
  Inheritance and estate triggers, key-rotation fallback when a co-signer goes
  dark, abandoned-treasury recovery, "this maintainer disappeared" escalation
  for on-chain project funds.

## Runner verification
  This contract's non-deterministic block calls `gl.nondet.web.render(url,
  mode="text")` -- one of the surfaces marked unverified in
  docs/claude-code-prompts.md ("Mark the unverified surfaces"). The exact call
  is isolated on the line tagged `# VERIFY:` inside `poke()`. Confirm in Studio:
  (1) `render()` returns a plain `str` of visible text, not a wrapper object;
  (2) a real profile/feed URL renders enough content for the model to judge
  activity, rather than an empty shell (many pages are JS-rendered -- `mode=
  "html"` may be needed instead of `"text"` for such sources; this has not been
  tested against a real target site). If `poke()` reverts with a Python
  TypeError instead of a clean revert, the render() return shape differs from
  what's assumed here.

  Unlike JailbreakBounty/SchellingResolver, `poke()` and `check_in()` are both
  plain (non-payable) writes, so -- unlike those two contracts -- the full
  LLM-judgment path here CAN be exercised end-to-end via the `genlayer` CLI
  without the payable-value limitation. Only `fund()` needs Studio's browser UI.

  CONFIRMED live (2026-07-01): `gl.message` on this pinned runner exposes only
  `chain_id`, `contract_address`, `origin_address`, `sender_address`, `value`
  -- no `.datetime`, no block number, no clock of any kind. Do not reintroduce
  a `gl.message.datetime` read into this contract without re-verifying the
  runner has changed.
"""

from genlayer import *
import json

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



@gl.evm.contract_interface
class _NativeRecipient:
    class View:
        pass

    class Write:
        pass


def send_native(recipient: Address, amount: int) -> None:
    _NativeRecipient(recipient).emit_transfer(value=u256(amount))

class SemanticDeadman(gl.Contract):
    owner: Address
    beneficiary: Address
    liveness_url: str
    liveness_policy: str          # plain-language description of what "alive" looks like
    last_alive_snapshot: str      # LLM-produced description of last-observed activity; "" = no baseline yet
    treasury: u256
    released: bool
    claimable: TreeMap[Address, u256]

    def __init__(self, beneficiary: Address, liveness_url: str, liveness_policy: str):
        b = beneficiary if isinstance(beneficiary, Address) else Address(beneficiary)
        require(
            b != Address("0x0000000000000000000000000000000000000000"),
            "beneficiary required",
        )
        require(len(liveness_url.strip()) > 0, "liveness_url required")
        require(len(liveness_policy.strip()) > 0, "liveness_policy required")
        self.owner = gl.message.sender_address
        self.beneficiary = b
        self.liveness_url = liveness_url
        self.liveness_policy = liveness_policy
        self.last_alive_snapshot = ""
        self.treasury = u256(0)
        self.released = False

    # -- funding --------------------------------------------------------------
    @gl.public.write.payable
    def fund(self) -> None:
        require(not self.released, "already released")
        self.treasury = u256(int(self.treasury) + int(gl.message.value))

    # -- cheap deterministic path --------------------------------------------
    @gl.public.write
    def check_in(self) -> None:
        """The owner resets the switch directly. No LLM call, no ambiguity.
        Clears any stored snapshot so the next poke() re-establishes a fresh
        baseline rather than judging against stale context."""
        require(gl.message.sender_address == self.owner, "only owner")
        require(not self.released, "already released")
        self.last_alive_snapshot = ""

    # -- expensive semantic path ----------------------------------------------
    @gl.public.write
    def poke(self) -> bool:
        """Anyone may call this -- the beneficiary should not depend on the
        owner's cooperation to eventually trigger a real check."""
        require(not self.released, "already released")

        url = self.liveness_url
        policy = self.liveness_policy
        last_snapshot = self.last_alive_snapshot

        def judge_liveness() -> str:
            # VERIFY: gl.nondet.web.render shape is unverified on this runner --
            # see "## Runner verification" in the module docstring.
            #
            # A fetch failure (dead domain, DNS failure, disallowed TLD, etc.)
            # raises inside render() rather than returning content -- confirmed
            # live via gl.nondet.NondetException (e.g. {'causes':
            # ['TLD_FORBIDDEN'], ...}). An uncaught raise here would abort the
            # whole poke() transaction instead of being read as evidence the
            # source has gone dark, so it becomes a separate FETCH_FAILED
            # outcome and cannot release funds.
            try:
                content = gl.nondet.web.render(url, mode="text")
            except Exception as e:
                return canonical(
                    {
                        "outcome": "FETCH_FAILED",
                        "baseline": last_snapshot,
                        "reason": f"fetch failed: {e}"[:280],
                    }
                )
            baseline_note = (
                f'PREVIOUSLY OBSERVED ACTIVITY (the last confirmed-alive baseline): "{last_snapshot}"'
                if last_snapshot
                else "PREVIOUSLY OBSERVED ACTIVITY: none recorded yet -- this is the first check "
                "since the switch was armed or last reset by the owner."
            )
            prompt = f"""You are assessing whether a person or project is still
genuinely active, for a dead-man's-switch contract. There is NO clock or
timestamp available to you or to this contract -- you must judge liveness
purely from the CONTENT of the source, comparing it against what was
previously observed.

LIVENESS POLICY (stated by the switch's owner, describes what counts as being
"alive"): {policy}

{baseline_note}

CONTENT FETCHED FROM THE LIVENESS SOURCE ({url}):
---
{content[:6000]}
---

Judge whether this content shows genuine activity consistent with the policy
that has visibly ADVANCED beyond the previously observed baseline (a new post,
a new commit, a changed status -- not just the same static page repeating what
was already known). If there is no baseline yet, judge whether the content
shows ANY genuine current activity consistent with the policy. Be conservative:
an unchanged page counts as INACTIVE. A fetch error is not an inactivity
finding because it cannot establish the source state.

Return ONLY strict JSON, no prose, no markdown:
{{ "outcome": "ACTIVE"|"INACTIVE", "baseline": "<short factual description of the most recent activity observed; repeat the previous baseline for INACTIVE>", "reason": "<one sentence>" }}"""
            raw = gl.nondet.exec_prompt(prompt)
            verdict = parse_json_response(raw)
            outcome = str(verdict["outcome"]).upper()
            require(outcome in ("ACTIVE", "INACTIVE"), "invalid liveness outcome")
            baseline = str(verdict.get("baseline", ""))[:400]
            if outcome == "ACTIVE":
                require(len(baseline.strip()) > 0, "active result needs baseline")
            reason = str(verdict.get("reason", ""))[:280]
            return canonical(
                {"outcome": outcome, "baseline": baseline, "reason": reason}
            )

        principle = (
            "Both results judge whether a liveness source shows genuine ongoing "
            "activity for a dead-man's-switch check. The outcome is action-bound: "
            "ACTIVE, INACTIVE, and FETCH_FAILED are distinct and cannot be treated "
            "as equivalent. ACTIVE results are equivalent only when their baseline "
            "descriptions communicate the same factual latest activity. INACTIVE "
            "and FETCH_FAILED results must preserve the supplied previous baseline. "
            "The baseline is consensus-bound state, not ignorable metadata. Reason "
            "text may differ freely and must be ignored."
        )
        agreed = gl.eq_principle.prompt_comparative(judge_liveness, principle)
        result = json.loads(agreed)
        outcome = str(result["outcome"]).upper()
        require(
            outcome in ("ACTIVE", "INACTIVE", "FETCH_FAILED"),
            "invalid agreed liveness outcome",
        )
        agreed_baseline = str(result.get("baseline", ""))[:400]

        if outcome == "ACTIVE":
            # Consensus confirms the trail is warm. Store the new baseline.
            require(len(agreed_baseline.strip()) > 0, "active result needs baseline")
            self.last_alive_snapshot = agreed_baseline
            return False

        if outcome == "FETCH_FAILED":
            # No source state was established. Preserve every escrow-related
            # field and the prior baseline so an outage cannot release funds.
            require(agreed_baseline == last_snapshot, "failure changed baseline")
            return False

        # An inactive finding does not establish a replacement baseline.
        require(agreed_baseline == last_snapshot, "inactive changed baseline")

        # Consensus agrees the source has gone cold. Release, once, forever.
        self.released = True
        payout = int(self.treasury)
        self.treasury = u256(0)
        if payout > 0:
            self.claimable[self.beneficiary] = u256(
                int(self.claimable.get(self.beneficiary, u256(0))) + payout
            )
        return True

    # -- disbursement (pull pattern) ------------------------------------------
    @gl.public.write
    def claim(self) -> int:
        who = gl.message.sender_address
        owed = int(self.claimable.get(who, u256(0)))
        require(owed > 0, "nothing to claim")
        send_native(who, owed)
        self.claimable[who] = u256(0)
        # Native GEN transfer is emitted before the ledger is cleared.
        return owed

    # -- reads ----------------------------------------------------------------
    @gl.public.view
    def status(self) -> str:
        return canonical(
            {
                "owner": self.owner.as_hex,
                "beneficiary": self.beneficiary.as_hex,
                "liveness_url": self.liveness_url,
                "liveness_policy": self.liveness_policy,
                "last_alive_snapshot": self.last_alive_snapshot,
                "treasury": int(self.treasury),
                "released": self.released,
            }
        )

    @gl.public.view
    def claimable_of(self, who: Address) -> int:
        # `who` may already arrive as a native Address (address-shaped calldata
        # is auto-decoded regardless of a `str` type hint) -- wrapping an
        # already-Address value in Address(...) crashes on this runner.
        addr = who if isinstance(who, Address) else Address(who)
        return int(self.claimable.get(addr, u256(0)))
