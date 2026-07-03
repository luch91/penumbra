# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""
PENUMBRA -- III. SEMANTIC MACHINES -- 06

IntentLock -- access control whose key is a plain-language policy, not an
address allow-list. An action unlocks iff consensus judges it satisfies the
policy, with an optional one-shot nonce so a granted permission can be
scoped to fire exactly once.

WHY IT IS UNUSUAL
  Ordinary access control checks membership in a fixed set (an allow-list,
  a role, a signature). This primitive checks CONFORMANCE to a written
  policy instead: "withdrawals under 100 tokens to addresses that have
  interacted with this contract before are allowed", "only publish content
  that does not name a private individual". The rule lives in prose, not in
  code, so it can be understood, audited, and amended by non-programmers,
  while still being enforced by the same validator set that secures every
  other write in this contract.

HOW CONSENSUS IS USED
  `policy` and the caller's requested `action` are both deterministic
  input -- fully known before any nondet block runs, and identical on every
  validator. That is exactly the case CLAUDE.md recommends the
  NON_COMPARATIVE equivalence principle for: the leader decides
  grant/deny, and validators don't re-derive the decision independently
  (which would risk validators disagreeing over a genuinely borderline
  policy call) -- they verify the leader's verdict against explicit
  criteria (does the action clearly satisfy every requirement in the
  policy, with no unaddressed restriction). This mirrors
  ProofCarryingAnswer's verifier shape exactly: input arrives as plain
  arguments/state, not fresh model output, so the cheap-verify half of the
  hard/easy asymmetry applies.

  The grant/deny decision itself defaults to DENY on ambiguity -- the
  `criteria` explicitly reject a verdict that grants access despite any
  unaddressed restriction, which is the conservative posture an access
  control primitive must take (a false negative just means "try a clearer
  request"; a false positive is a security hole).

STATE DESIGN
  A pull-style `DynArray[Grant]` archive records every request (granted or
  denied) as an audit trail -- unlike ProofCarryingAnswer's "rejection
  leaves no trace" philosophy, a permissioning system benefits from logging
  denials too, so operators can see what was asked for and refused.
  `used_nonces` is a `TreeMap[str, u256]` "1 + index" existence map (the
  proven dedupe pattern used throughout this repo) keyed on
  `sha256(requester || action || nonce)`, burned only when a nonce-scoped
  request is actually GRANTED -- a denied attempt with the same nonce can
  be retried, since nothing was granted to replay. An empty nonce means "no
  one-shot binding requested" and the action can be re-requested freely.

REUSE
  Permissioning for treasury actions, content publishing, or agent
  tool-use: gate a real action on `request(action, nonce)` returning true,
  and use a nonce whenever the granted permission should only fire once
  (e.g. a specific withdrawal or a specific publish).
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
# ------------------------------------------------------------------------------


@allow_storage
@dataclass
class Grant:
    requester: Address
    action: str
    nonce: str
    granted: bool


class IntentLock(gl.Contract):
    owner: Address
    policy: str
    grants: DynArray[Grant]
    used_nonces: TreeMap[str, u256]   # sha256(requester|action|nonce) -> 1 + index

    def __init__(self, policy: str = ""):
        self.owner = gl.message.sender_address
        self.policy = policy.strip()

    @gl.public.write
    def set_policy(self, text: str) -> None:
        require(gl.message.sender_address == self.owner, "only owner can set the policy")
        t = text.strip()
        require(len(t) > 0, "empty policy")
        self.policy = t

    @gl.public.write
    def request(self, action: str, nonce: str) -> bool:
        pol = self.policy
        require(len(pol) > 0, "no policy set")
        # An empty-string calldata argument can arrive decoded as a non-str type
        # (observed: int) rather than "" -- see CLAUDE.md's "Addresses" note for
        # the same class of issue with Address args. Coerce defensively instead
        # of trusting the str type hint.
        act = (action if isinstance(action, str) else "").strip()
        require(len(act) > 0, "empty action")

        sender = gl.message.sender_address
        n = (nonce if isinstance(nonce, str) else "").strip()
        nonce_key = ""
        if len(n) > 0:
            nonce_key = hashlib.sha256((sender.as_hex + "|" + act + "|" + n).encode()).hexdigest()
            require(int(self.used_nonces.get(nonce_key, u256(0))) == 0, "nonce already used")

        def verification_input() -> str:
            # Fully deterministic: identical on the leader and every validator,
            # since policy/action are plain state and calldata, not fresh model
            # output. The principle does the judging, not re-derivation.
            return canonical({"policy": pol, "action": act})

        task = (
            "You are enforcing an access-control POLICY written in plain language "
            "against a specific requested ACTION. Decide whether the ACTION is "
            "permitted under the POLICY. Output ONLY strict JSON: "
            '{"granted": <true|false>, "reason": "<<=20 words>"}.'
        )
        criteria = (
            "A trustworthy verdict has these properties: (1) 'granted' is true ONLY "
            "if the ACTION clearly and unambiguously satisfies every requirement "
            "stated in the POLICY -- default to false on any ambiguity, missing "
            "detail, or partial match; (2) the POLICY's plain wording governs, not "
            "what a reasonable action might generally be allowed to do; (3) an "
            "ACTION that violates ANY stated restriction in the POLICY must be "
            "denied even if it satisfies other parts. Reject a verdict that grants "
            "access despite an unaddressed restriction in the POLICY."
        )
        raw = gl.eq_principle.prompt_non_comparative(verification_input, task=task, criteria=criteria)
        verdict = json.loads(raw) if isinstance(raw, str) else raw
        granted = bool(verdict["granted"])

        self.grants.append(Grant(requester=sender, action=act, nonce=n, granted=granted))
        if granted and len(nonce_key) > 0:
            self.used_nonces[nonce_key] = u256(len(self.grants))
        return granted

    # -- reads ------------------------------------------------------------------
    @gl.public.view
    def get_policy(self) -> str:
        return self.policy

    @gl.public.view
    def count(self) -> int:
        return len(self.grants)

    @gl.public.view
    def get(self, index: int) -> str:
        require(0 <= index < len(self.grants), "no such grant")
        g = self.grants[index]
        return canonical(
            {
                "requester": g.requester.as_hex,
                "action": g.action,
                "nonce": g.nonce,
                "granted": g.granted,
            }
        )

    @gl.public.view
    def last_grant(self) -> str:
        require(len(self.grants) > 0, "no requests yet")
        return self.get(len(self.grants) - 1)

    @gl.public.view
    def nonce_used(self, who: Address, action: str, nonce: str) -> bool:
        addr = who if isinstance(who, Address) else Address(who)
        key = hashlib.sha256((addr.as_hex + "|" + action.strip() + "|" + nonce.strip()).encode()).hexdigest()
        return int(self.used_nonces.get(key, u256(0))) > 0
