# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""
PENUMBRA · VII. CHRONOMANCY · 18

SemanticDeadman — a dead-man's switch that releases on genuine SEMANTIC
inactivity, not a missed timestamp ping.

WHY IT IS UNUSUAL
  A mechanical dead-man's switch only knows one fact: did check_in() get
  called before a deadline. That is trivially wrong for its real purpose —
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
  COMPARATIVE principle keyed on a single `alive` boolean: every validator
  independently re-fetches the source and re-judges, so a release requires
  INDEPENDENT agreement that the trail has gone cold — not one validator's
  stale cache or one model's hallucinated read of the page.

  ASSUMPTION (forced by a live-confirmed runner gap, documented in DECISIONS.md
  2026-07-01): CONTRACTS.md's one-liner spec names a `last_alive_ts` field, and
  the SDK's published API text documents `gl.message.datetime: str`. Neither
  exists to lean on here — a live isolation deploy on this pinned runner proved
  `gl.message` exposes only `chain_id`, `contract_address`, `origin_address`,
  `sender_address`, and `value`; accessing `.datetime` raises
  `AttributeError: 'MessageType' object has no attribute 'datetime'`. There is
  NO clock, timestamp, or block-number accessor available at all on this
  runner. So this contract cannot and does not track elapsed time. Instead,
  "alive" is judged purely by CONTENT DIFFING: the last confirmed-alive check
  stores a short LLM-produced description of the activity it observed (a
  snapshot), and each `poke()` asks the model whether the freshly fetched
  source shows genuine activity that has visibly ADVANCED since that snapshot
  — not whether a clock has ticked. This is arguably a better fit for "semantic
  inactivity, not a missed timestamp ping" than a timestamp comparison would
  have been anyway.

STATE & MONEY DESIGN
  A single escrowed treasury (funded via a separate payable `fund()`, matching
  the pattern in JailbreakBounty/SchellingResolver) that flips exactly once
  from owner-controlled to beneficiary-claimable. `check_in()` is the cheap
  deterministic path — the owner can always reset the switch directly, no LLM
  call needed. `poke()` is the expensive semantic path — anyone can call it
  (so the beneficiary isn't dependent on the owner's cooperation), and it only
  moves state when consensus agrees the source itself proves continued life.
  Release uses the PULL pattern: `claim()` withdraws separately from `poke()`.

REUSE
  Inheritance and estate triggers, key-rotation fallback when a co-signer goes
  dark, abandoned-treasury recovery, "this maintainer disappeared" escalation
  for on-chain project funds.

## Runner verification
  This contract's non-deterministic block calls `gl.nondet.web.render(url,
  mode="text")` — one of the surfaces marked unverified in
  docs/claude-code-prompts.md ("Mark the unverified surfaces"). The exact call
  is isolated on the line tagged `# VERIFY:` inside `poke()`. Confirm in Studio:
  (1) `render()` returns a plain `str` of visible text, not a wrapper object;
  (2) a real profile/feed URL renders enough content for the model to judge
  activity, rather than an empty shell (many pages are JS-rendered — `mode=
  "html"` may be needed instead of `"text"` for such sources; this has not been
  tested against a real target site). If `poke()` reverts with a Python
  TypeError instead of a clean revert, the render() return shape differs from
  what's assumed here.

  Unlike JailbreakBounty/SchellingResolver, `poke()` and `check_in()` are both
  plain (non-payable) writes, so — unlike those two contracts — the full
  LLM-judgment path here CAN be exercised end-to-end via the `genlayer` CLI
  without the payable-value limitation. Only `fund()` needs Studio's browser UI.

  CONFIRMED live (2026-07-01): `gl.message` on this pinned runner exposes only
  `chain_id`, `contract_address`, `origin_address`, `sender_address`, `value`
  — no `.datetime`, no block number, no clock of any kind. Do not reintroduce
  a `gl.message.datetime` read into this contract without re-verifying the
  runner has changed.
"""

from genlayer import *
import json

# ── PENUMBRA helpers ──────────────────────────────────────────────────────────
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
    # on this runner (confirmed by isolation testing) — ask the model for JSON as
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
# ──────────────────────────────────────────────────────────────────────────────


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

    # ── funding ──────────────────────────────────────────────────────────────
    @gl.public.write.payable
    def fund(self) -> None:
        require(not self.released, "already released")
        self.treasury = u256(int(self.treasury) + int(gl.message.value))

    # ── cheap deterministic path ────────────────────────────────────────────
    @gl.public.write
    def check_in(self) -> None:
        """The owner resets the switch directly. No LLM call, no ambiguity.
        Clears any stored snapshot so the next poke() re-establishes a fresh
        baseline rather than judging against stale context."""
        require(gl.message.sender_address == self.owner, "only owner")
        require(not self.released, "already released")
        self.last_alive_snapshot = ""

    # ── expensive semantic path ──────────────────────────────────────────────
    @gl.public.write
    def poke(self) -> bool:
        """Anyone may call this — the beneficiary should not depend on the
        owner's cooperation to eventually trigger a real check."""
        require(not self.released, "already released")

        url = self.liveness_url
        policy = self.liveness_policy
        last_snapshot = self.last_alive_snapshot

        def judge_liveness() -> str:
            # VERIFY: gl.nondet.web.render shape is unverified on this runner —
            # see "## Runner verification" in the module docstring.
            #
            # A fetch failure (dead domain, DNS failure, disallowed TLD, etc.)
            # raises inside render() rather than returning content — confirmed
            # live via gl.nondet.NondetException (e.g. {'causes':
            # ['TLD_FORBIDDEN'], ...}). An uncaught raise here would abort the
            # whole poke() transaction instead of being read as evidence the
            # source has gone dark, so it is treated as NOT alive explicitly.
            try:
                content = gl.nondet.web.render(url, mode="text")
            except Exception as e:
                return canonical(
                    {"alive": False, "snapshot": "", "reason": f"fetch failed: {e}"[:280]}
                )
            baseline_note = (
                f'PREVIOUSLY OBSERVED ACTIVITY (the last confirmed-alive baseline): "{last_snapshot}"'
                if last_snapshot
                else "PREVIOUSLY OBSERVED ACTIVITY: none recorded yet — this is the first check "
                "since the switch was armed or last reset by the owner."
            )
            prompt = f"""You are assessing whether a person or project is still
genuinely active, for a dead-man's-switch contract. There is NO clock or
timestamp available to you or to this contract — you must judge liveness
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
a new commit, a changed status — not just the same static page repeating what
was already known). If there is no baseline yet, judge whether the content
shows ANY genuine current activity consistent with the policy. Be conservative:
an unchanged page, a parked domain, or a fetch error all count as NOT alive.

Return ONLY strict JSON, no prose, no markdown:
{{ "alive": <true|false>, "snapshot": "<short factual description of the most recent activity observed, to serve as the next baseline; empty string if not alive>", "reason": "<one sentence>" }}"""
            raw = gl.nondet.exec_prompt(prompt)
            verdict = parse_json_response(raw)
            alive = bool(verdict["alive"])
            snapshot = str(verdict.get("snapshot", ""))[:400]
            reason = str(verdict.get("reason", ""))[:280]
            return canonical({"alive": alive, "snapshot": snapshot, "reason": reason})

        principle = (
            "Both results judge whether a liveness source shows genuine ongoing "
            "activity for a dead-man's-switch check. They are EQUIVALENT if and "
            "only if their 'alive' boolean is the same. The 'snapshot' and "
            "'reason' text may differ freely and must be ignored when comparing."
        )
        agreed = gl.eq_principle.prompt_comparative(judge_liveness, principle)
        result = json.loads(agreed)
        alive = bool(result["alive"])

        if alive:
            # Consensus confirms the trail is warm. Store the new baseline.
            self.last_alive_snapshot = str(result.get("snapshot", ""))[:400]
            return False

        # Consensus agrees the source has gone cold. Release, once, forever.
        self.released = True
        payout = int(self.treasury)
        self.treasury = u256(0)
        if payout > 0:
            self.claimable[self.beneficiary] = u256(
                int(self.claimable.get(self.beneficiary, u256(0))) + payout
            )
        return True

    # ── disbursement (pull pattern) ──────────────────────────────────────────
    @gl.public.write
    def claim(self) -> int:
        who = gl.message.sender_address
        owed = int(self.claimable.get(who, u256(0)))
        require(owed > 0, "nothing to claim")
        self.claimable[who] = u256(0)
        # INTEGRATION HOOK: disburse native GEN/ERC-20 `owed` to `who` here; the
        # internal ledger above is authoritative and already debited.
        return owed

    # ── reads ────────────────────────────────────────────────────────────────
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
        # is auto-decoded regardless of a `str` type hint) — wrapping an
        # already-Address value in Address(...) crashes on this runner.
        addr = who if isinstance(who, Address) else Address(who)
        return int(self.claimable.get(addr, u256(0)))
