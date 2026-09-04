# { "Depends": "py-genlayer:5jycge4q8k23462jtb0b9fyey1s9q928sz2nbrd9mg4sxqg2qng" }
"""
PENUMBRA -- V. CORROBORATION -- 13

ProvenanceAttestor -- attest that a specific source supports (or does not
support) a specific claim, recording the exact supporting span.

WHY IT IS UNUSUAL
  Citation chains are usually asserted, not checked: someone links a claim to
  a source and everyone trusts the link is honest. This contract instead asks
  the network itself to fetch the source and judge whether it actually backs
  the claim, and to name the exact span of text doing the backing. A citation
  that does not survive this check never becomes a permanent attestation.

HOW CONSENSUS IS USED
  CONTRACTS.md's one-line spec names `non_comparative` for this primitive.
  Built with `comparative` instead -- a deliberate deviation, documented here
  and in DECISIONS.md. `non_comparative` means the LEADER alone produces the
  result (here: fetches the url and extracts a span) and validators only
  audit that result against fixed criteria; they never independently fetch
  anything. For family V ("trustless web, verified across sources"), a
  single leader-controlled fetch defeats the entire point -- a dishonest or
  unlucky leader could fabricate a supporting span from a page nobody else
  ever reads, and validators would have no independent basis to catch it.
  CorroborationOracle and CanaryTripwire, this primitive's siblings in the
  same family, both use `comparative` for exactly this reason. So here too:
  each validator independently fetches the SAME url (guarded against fetch
  failure -- see below) and independently judges support + extracts a span;
  the principle requires agreement on the `supports` boolean, and -- only
  when both sides say the source supports the claim -- requires the spans to
  reference the same underlying fact (paraphrase-tolerant, not byte-exact).
  Independent, cross-fetched agreement is the actual trustless-provenance
  guarantee; one leader's unverified read is not.

STATE DESIGN
  An append-only `DynArray[Attestation]` audit trail that records EVERY
  attempt, not just the ones that support the claim -- a source that was
  checked and found NOT to support a claim is itself useful provenance data
  (the anti-misinformation reuse case explicitly wants "we checked, it does
  not hold up" on record, not just silence). `span_hash` content-addresses
  the agreed supporting span (empty hash when `supports` is false); the full
  span text is also kept for readability, matching ProofCarryingAnswer's
  `proof_digest` + human-readable fields pattern.

REUSE
  Citation chains, fact provenance, anti-misinformation rails -- anywhere a
  claim needs to point at a specific, checked piece of evidence rather than
  an assertion of "trust me, it's in there somewhere."

## Runner verification
  Reuses SemanticDeadman's proven try/except-around-`gl.nondet.web.render`
  guard (see CLAUDE.md "Known blockers") at a second confirmed call site
  (CorroborationOracle was the first). The call is isolated in `_fetch()`,
  tagged `# VERIFY:` at its use inside the nondet closure. Confirm in Studio
  or via CLI: a real, reachable URL should produce a non-trivial `content`
  string feeding the prompt; a dead/unreachable URL should route to the
  `[FETCH FAILED: ...]` branch and still resolve cleanly (supports=false, no
  transaction abort) rather than reverting the whole call.
"""

from genlayer import *
import json
import hashlib
from dataclasses import dataclass

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


@allow_storage
@dataclass
class Attestation:
    claim: str
    url: str
    supports: bool
    span: str
    span_hash: str


class ProvenanceAttestor(gl.Contract):
    attestations: DynArray[Attestation]
    latest: u256

    def __init__(self):
        pass

    @gl.public.write
    def attest(self, claim: str, url: str) -> bool:
        c = (claim if isinstance(claim, str) else "").strip()
        u = (url if isinstance(url, str) else "").strip()
        require(len(c) > 0, "empty claim")
        require(len(u) > 0, "empty url")

        def check_provenance() -> str:
            try:
                content = gl.nondet.web.render(u, mode="text")  # VERIFY: see docstring
                fetch_note = ""
            except Exception as e:
                content = ""
                fetch_note = f"[FETCH FAILED: {e}]"[:200]

            if fetch_note:
                # A source that cannot be fetched at all cannot support anything.
                return canonical({"supports": False, "span": ""})

            prompt = f"""You are checking whether a web source supports a specific
claim, for an on-chain provenance attestation.

CLAIM: {c}

SOURCE CONTENT (fetched from {u}):
---
{content[:6000] if content else "[EMPTY PAGE]"}
---

Determine whether the source content genuinely supports the claim. Be
conservative: a source that is merely related, or that discusses the topic
without actually backing the specific claim, does NOT support it. If it does
support the claim, extract the SHORTEST exact span of the source text (a
direct quote, not a paraphrase) that does the supporting.

Return ONLY strict JSON, no prose, no markdown:
{{ "supports": <true|false>, "span": "<exact quoted span from the source, or empty string if not supporting>" }}"""
            raw = gl.nondet.exec_prompt(prompt)
            data = parse_json_response(raw)
            supports = bool(data["supports"])
            span = str(data.get("span", "")).strip()[:600] if supports else ""
            return canonical({"supports": supports, "span": span})

        principle = (
            "Both results judge whether the same web source supports the same "
            "claim. They are EQUIVALENT if and only if: (1) the 'supports' "
            "booleans match, AND (2) when both are true, the 'span' fields "
            "quote or closely paraphrase the same underlying fact or passage "
            "from the source (exact wording may differ, but they must point "
            "at the same supporting content, not different parts of the "
            "source or unrelated text). If the booleans disagree, or both "
            "support the claim but via clearly different content, they are "
            "NOT equivalent."
        )
        agreed = gl.eq_principle.prompt_comparative(check_provenance, principle)
        parsed = json.loads(agreed)

        supports = bool(parsed["supports"])
        span = str(parsed.get("span", ""))
        span_hash = hashlib.sha256(span.encode()).hexdigest() if span else ""

        self.attestations.append(
            Attestation(claim=c, url=u, supports=supports, span=span, span_hash=span_hash)
        )
        self.latest = u256(len(self.attestations) - 1)
        return supports

    # -- reads --------------------------------------------------------------------
    @gl.public.view
    def count(self) -> int:
        return len(self.attestations)

    @gl.public.view
    def get(self, index: int) -> str:
        require(0 <= index < len(self.attestations), "no such attestation")
        a = self.attestations[index]
        return canonical(
            {
                "claim": a.claim,
                "url": a.url,
                "supports": a.supports,
                "span": a.span,
                "span_hash": a.span_hash,
            }
        )

    @gl.public.view
    def latest_attestation(self) -> str:
        require(len(self.attestations) > 0, "no attestations yet")
        return self.get(int(self.latest))
