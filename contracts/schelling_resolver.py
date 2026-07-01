# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""
PENUMBRA · IV. ADVERSARIA · 10

SchellingResolver — resolves a subjective question by paying whoever matched
the crowd's focal answer. A Keynesian beauty contest done with semantic
clustering instead of numeric guesses.

WHY IT IS UNUSUAL
  Classic Schelling-point games need a human tally to find the focal point,
  or a numeric answer simple enough to bucket mechanically. This contract lets
  the focal point be FREE TEXT — "blue", "the sky", "azure-ish" all belong to
  the same cluster — and has the network itself agree on which submissions
  cluster together, not just what any single submission means.

HOW CONSENSUS IS USED
  The non-deterministic block hands every submitted answer to the model and
  asks it to identify the single largest semantic cluster, returning the
  cluster as a sorted list of submission indices. Consensus uses the
  COMPARATIVE equivalence principle keyed on that index set: each validator
  independently re-clusters the same submissions, and the principle requires
  the winning index SET to match exactly (wording used to describe the
  cluster is irrelevant). A clustering that only one model would produce does
  not clear consensus and the resolution reverts — exactly like a jailbreak
  that only works on one model, an unstable Schelling point is not a Schelling
  point.

STATE & MONEY DESIGN
  Submissions are an append-only `DynArray[Submission]`; each carries its own
  staked value. `resolve()` computes the total pool from every submission
  (winners and losers alike — the losers' stakes ARE the winners' prize) and
  splits it evenly across the winning indices via the PULL-payment pattern:
  `claimable` is credited, `claim()` withdraws separately.

REUSE
  Decentralized labeling, subjective dispute resolution, any "what does the
  crowd actually think" coordination problem where the answer is prose, not
  a number.

## Runner verification
  `submit()` is `@gl.public.write.payable` and requires `gl.message.value > 0`
  as the stake. `genlayer write` (CLI v0.39.2) hardcodes `value: 0n` on every
  call, so `submit()` cannot be driven to a real success via the CLI — every
  CLI-issued `submit()` reverts on "stake required" by construction, which
  means `resolve()`'s live LLM-clustering path has NOT been exercised end to
  end here. Verify via Studio's browser UI (has a value field on write calls)
  before relying on this contract with real funds. See CLAUDE.md's "Known
  blockers & open verification gaps" for the underlying CLI limitation.
"""

from genlayer import *
import json
from dataclasses import dataclass

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


@allow_storage
@dataclass
class Submission:
    submitter: Address
    answer: str
    stake: u256


class SchellingResolver(gl.Contract):
    submissions: DynArray[Submission]
    winners: DynArray[u256]           # winning submission indices, set once
    claimable: TreeMap[Address, u256]
    resolved: bool
    min_submissions: u256

    def __init__(self, min_submissions: int = 2):
        require(min_submissions >= 2, "need at least 2 submissions to find a cluster")
        self.min_submissions = u256(min_submissions)
        self.resolved = False

    # ── submission ──────────────────────────────────────────────────────────
    @gl.public.write.payable
    def submit(self, answer: str) -> int:
        require(not self.resolved, "submissions closed")
        require(len(answer.strip()) > 0, "empty answer")
        require(int(gl.message.value) > 0, "stake required")
        sub = Submission(
            submitter=gl.message.sender_address,
            answer=answer,
            stake=u256(int(gl.message.value)),
        )
        self.submissions.append(sub)
        return len(self.submissions) - 1

    # ── resolution ──────────────────────────────────────────────────────────
    @gl.public.write
    def resolve(self) -> str:
        require(not self.resolved, "already resolved")
        n = len(self.submissions)
        require(n >= int(self.min_submissions), "not enough submissions")

        # Pull everything the nondet block needs into locals; it may not touch
        # self/storage.
        answers = [self.submissions[i].answer for i in range(n)]

        def cluster() -> str:
            listing = "\n".join(f"{i}: {a}" for i, a in enumerate(answers))
            prompt = f"""You are finding the Schelling point in a set of submitted answers:
the single LARGEST group of submissions that assert essentially the same
thing. Minor wording differences belong to the same group; different
substantive answers do not.

SUBMITTED ANSWERS (0-indexed):
{listing}

Return ONLY strict JSON, no prose, no markdown:
{{
  "winning_indices": [<sorted list of the integer indices in the largest group>]
}}"""
            raw = gl.nondet.exec_prompt(prompt)
            data = parse_json_response(raw)
            idxs = sorted({int(i) for i in data["winning_indices"] if 0 <= int(i) < n})
            return canonical({"winning_indices": idxs})

        principle = (
            "Both results identify the winning Schelling-point cluster from the same "
            "list of submitted answers. They are EQUIVALENT if and only if the sets of "
            "'winning_indices' are identical (order doesn't matter). The wording used "
            "to describe or justify the cluster is irrelevant; only index membership "
            "matters. If the two results disagree on which indices belong, they are "
            "NOT equivalent."
        )
        agreed = gl.eq_principle.prompt_comparative(cluster, principle)
        parsed = json.loads(agreed)
        idxs = [int(i) for i in parsed["winning_indices"]]
        require(len(idxs) > 0, "no winning cluster identified")

        total_pool = 0
        for i in range(n):
            total_pool += int(self.submissions[i].stake)
        share = total_pool // len(idxs)

        for i in idxs:
            self.winners.append(u256(i))
            who = self.submissions[i].submitter
            self.claimable[who] = u256(int(self.claimable.get(who, u256(0))) + share)

        self.resolved = True
        return canonical({"winning_indices": idxs, "share": share})

    # ── disbursement (pull pattern) ────────────────────────────────────────────
    @gl.public.write
    def claim(self) -> int:
        who = gl.message.sender_address
        owed = int(self.claimable.get(who, u256(0)))
        require(owed > 0, "nothing to claim")
        self.claimable[who] = u256(0)
        # INTEGRATION HOOK: disburse native GEN/ERC-20 `owed` to `who` here; the
        # internal ledger above is authoritative and already debited.
        return owed

    # ── reads ────────────────────────────────────────────────────────────────────
    @gl.public.view
    def count(self) -> int:
        return len(self.submissions)

    @gl.public.view
    def get(self, index: int) -> str:
        require(0 <= index < len(self.submissions), "no such submission")
        s = self.submissions[index]
        return canonical(
            {
                "submitter": s.submitter.as_hex,
                "answer": s.answer,
                "stake": int(s.stake),
            }
        )

    @gl.public.view
    def is_resolved(self) -> bool:
        return self.resolved

    @gl.public.view
    def winning_indices(self) -> str:
        require(self.resolved, "not resolved yet")
        return canonical({"winning_indices": [int(w) for w in self.winners]})

    @gl.public.view
    def claimable_of(self, who: Address) -> int:
        # `who` may already arrive as a native Address (address-shaped calldata
        # is auto-decoded regardless of a `str` type hint) — wrapping an
        # already-Address value in Address(...) crashes on this runner.
        addr = who if isinstance(who, Address) else Address(who)
        return int(self.claimable.get(addr, u256(0)))
