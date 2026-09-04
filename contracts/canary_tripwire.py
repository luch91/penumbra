# { "Depends": "py-genlayer:5jycge4q8k23462jtb0b9fyey1s9q928sz2nbrd9mg4sxqg2qng" }
"""
PENUMBRA -- V. CORROBORATION -- 14

CanaryTripwire -- watch a web source for a plain-language condition and flip
on consensus that it has occurred, firing a callback to another contract on
first trip.

WHY IT IS UNUSUAL
  This is an on-chain alert whose trigger condition is prose, not a price
  feed threshold: "the maintainer posted an outage notice," "the peg
  discussion turned to depeg," "the announcement page confirms the
  deadline passed." The network itself watches the source and judges the
  condition; nothing trips on one party's say-so. It is also the first
  primitive in this repo to actually ATTEMPT the cross-contract WRITE
  surface (firing a callback), which CLAUDE.md has, until now, listed as
  completely unexercised -- see "## Runner verification" below.

HOW CONSENSUS IS USED
  `poll()`'s non-deterministic block fetches the watched source (guarded
  against fetch failure, reusing SemanticDeadman/CorroborationOracle/
  ProvenanceAttestor's proven try/except pattern) and asks the model whether
  the stated condition is met. Consensus uses the COMPARATIVE principle
  keyed on a single `condition_met` boolean, matching CONTRACTS.md's spec
  exactly: every validator independently re-fetches the source and
  re-judges, so a trip requires INDEPENDENT agreement that the condition
  now holds -- not one validator's stale cache or one model's hallucinated
  read of the page. This mirrors SemanticDeadman's `poke()` almost exactly,
  with the boolean's meaning inverted (armed -> tripped, instead of
  alive -> released).

STATE DESIGN
  A one-shot switch: `armed` gates `poll()`, `tripped` is sticky and
  idempotent (`poll()` after tripping just returns `true` without re-fetching
  or re-firing). `arm()` may be called again by the owner before the first
  trip (to fix a mistaken condition or callback address), but never after.

REUSE
  On-chain alerts: depeg watch, governance-deadline watch, outage detection,
  any downstream contract that needs to react the moment consensus agrees a
  real-world condition has occurred.

## Runner verification
  Reuses the try/except-around-`gl.nondet.web.render` guard (SemanticDeadman,
  CorroborationOracle, ProvenanceAttestor) at a fourth confirmed call site.

  The callback fire is isolated in `_fire_callback`, tagged `# VERIFY:`. This
  is the FIRST cross-contract WRITE (`gl.get_contract_at(addr).emit()...`)
  attempted anywhere in this repo -- CLAUDE.md lists this as "completely
  unexercised" prior to this contract. ASSUMPTION (this contract's own
  convention, since CONTRACTS.md leaves the callback's method shape open):
  the callback target must expose `on_trip(condition: str) -> None`, the
  same "one well-known method name" convention MirrorAudit uses for
  `status()`. See `contracts/fixtures/tripwire_callback_stub.py`, the
  throwaway target used to pin this shape in tests.

  KNOWN RISK, inherited from CLAUDE.md's "Known blockers": calling
  `gl.get_contract_at` on an address with NO deployed contract code at all
  has been observed (informally, once) to HANG rather than cleanly revert.
  `arm()` cannot safely defend against this -- probing whether an address
  has code would require the same risky call. Callers MUST only ever
  `arm()` with an address that is confirmed to be an already-deployed
  contract exposing `on_trip`. This contract does not and cannot enforce
  that at the type level. Every automated test in this repo that exercises
  the real trip+callback path deploys a real fixture contract first and
  uses its live address -- never a synthetic or EOA address -- specifically
  to avoid triggering this failure mode inside a test run.

  If `_fire_callback` raises a CATCHABLE exception (e.g. an application-level
  error inside a well-behaved target), it is swallowed and `tripped` stays
  committed -- the trip itself is the authoritative on-chain fact; callback
  delivery is best-effort, matching the pull-payment/integration-hook
  precedent in JailbreakBounty and SemanticDeadman. If the target does not
  implement `on_trip` at all, MirrorAudit's docstring already documents that
  this surfaces as an UNCATCHABLE runner-level dispatch fault, not a Python
  exception -- in that case the try/except here does NOT catch it, and the
  whole `poll()` transaction (including the `tripped` write) reverts
  cleanly instead.
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


class CanaryTripwire(gl.Contract):
    owner: Address
    url: str
    condition: str
    callback: Address
    armed: bool
    tripped: bool

    def __init__(self, url: str):
        u = (url if isinstance(url, str) else "").strip()
        require(len(u) > 0, "url required")
        self.owner = gl.message.sender_address
        self.url = u
        self.condition = ""
        self.callback = Address("0x0000000000000000000000000000000000000000")
        self.armed = False
        self.tripped = False

    @gl.public.write
    def arm(self, condition: str, callback: Address) -> None:
        require(gl.message.sender_address == self.owner, "only owner")
        require(not self.tripped, "already tripped")
        cond = (condition if isinstance(condition, str) else "").strip()
        require(len(cond) > 0, "condition required")
        cb = callback if isinstance(callback, Address) else Address(callback)
        require(
            cb != Address("0x0000000000000000000000000000000000000000"),
            "callback required",
        )
        self.condition = cond
        self.callback = cb
        self.armed = True

    @gl.public.write
    def poll(self) -> bool:
        require(self.armed, "not armed")
        if self.tripped:
            return True

        url = self.url
        condition = self.condition

        def judge_condition() -> str:
            try:
                content = gl.nondet.web.render(url, mode="text")
            except Exception as e:
                return canonical(
                    {"condition_met": False, "reason": f"fetch failed: {e}"[:280]}
                )
            prompt = f"""You are watching a web source on behalf of an on-chain
tripwire. Decide whether the CONDITION below is currently met by the
CONTENT fetched from the source. Be conservative: an unrelated page, a
fetch that returned nothing useful, or content that only partially
resembles the condition all count as NOT met.

CONDITION: {condition}

CONTENT FETCHED FROM THE SOURCE ({url}):
---
{content[:6000] if content else "[EMPTY PAGE]"}
---

Return ONLY strict JSON, no prose, no markdown:
{{ "condition_met": <true|false>, "reason": "<one sentence>" }}"""
            raw = gl.nondet.exec_prompt(prompt)
            verdict = parse_json_response(raw)
            met = bool(verdict["condition_met"])
            reason = str(verdict.get("reason", ""))[:280]
            return canonical({"condition_met": met, "reason": reason})

        principle = (
            "Both results judge whether the same plain-language condition is "
            "currently met by the same web source. They are EQUIVALENT if and "
            "only if their 'condition_met' boolean is the same. The 'reason' "
            "text may differ freely and must be ignored when comparing."
        )
        agreed = gl.eq_principle.prompt_comparative(judge_condition, principle)
        result = json.loads(agreed)
        met = bool(result["condition_met"])

        if not met:
            return False

        self.tripped = True
        self._fire_callback()
        return True

    # -- the cross-contract write, isolated so a shape mismatch is one line to fix --
    def _fire_callback(self) -> None:
        # VERIFY: first cross-contract WRITE attempted in this repo -- see
        # "## Runner verification" in the module docstring for the known
        # hang-on-invalid-address risk and the uncatchable-dispatch-fault
        # caveat inherited from MirrorAudit's cross-contract READ findings.
        try:
            other = gl.get_contract_at(self.callback)
            other.emit().on_trip(self.condition)
        except Exception:
            # Best-effort notification: the trip itself is the authoritative
            # on-chain fact (readable via status()) even if delivery to the
            # callback fails for a catchable reason. An uncatchable dispatch
            # fault (target lacks on_trip) is NOT caught here and reverts
            # the whole poll() transaction instead -- see docstring.
            pass

    # -- reads ----------------------------------------------------------------
    @gl.public.view
    def status(self) -> str:
        return canonical(
            {
                "owner": self.owner.as_hex,
                "url": self.url,
                "condition": self.condition,
                "callback": self.callback.as_hex,
                "armed": self.armed,
                "tripped": self.tripped,
            }
        )
