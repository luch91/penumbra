# DECISIONS — Penumbra

A running log of non-obvious decisions made while building this repo: what was
chosen, why, and what it rules out. This is not a changelog (git history covers
that) — it's the reasoning that isn't visible from reading the code alone.
Updated every session; newest entries at the top.

---

## 2026-07-04 — ProvenanceAttestor (V.13) deviates from CONTRACTS.md's non_comparative to comparative; a wrong-conda-env ImportError looked like the SynSent flakiness at first

**Decision.** Built `ProvenanceAttestor.attest(claim, url)` with `comparative`,
not the `non_comparative` CONTRACTS.md's one-line spec names. Each validator
independently fetches the SAME url (guarded try/except, reusing
SemanticDeadman/CorroborationOracle's pattern) and independently judges
`supports` + extracts a `span`; the principle requires agreement on
`supports`, and -- only when both sides say the source supports the claim --
requires the spans to reference the same underlying fact (paraphrase-
tolerant). State is an append-only `DynArray[Attestation]` that records
EVERY attempt, including non-supporting ones, not just successes.

**Why.** `non_comparative` means the LEADER ALONE produces the result
(fetches, extracts) and validators only audit that result against fixed
criteria -- they never independently fetch anything themselves. For family V
("trustless web, verified across sources"), that would let a single
dishonest or unlucky leader fabricate a supporting span from a page nobody
else ever reads, with no independent basis for validators to catch it. This
primitive's siblings in the same family -- `CorroborationOracle` (built) and
`CanaryTripwire` (next) -- both use `comparative` for exactly this reason
per their own catalog specs; treating `ProvenanceAttestor` as an
exception (per its catalog entry) would have been internally inconsistent
with the family's stated purpose, so it was corrected to match its
siblings. This is the same category of judgment call as SemanticDiffLedger's
comparative-over-apparent-non_comparative decision (2026-07-03): CONTRACTS.md
is a product description, and the actual consensus-move choice has to serve
the primitive's real trust guarantee, not just pattern-match the one-liner.

Live-verified end to end before writing gltest: deployed to studionet
(`0xbfa8E2182deFC5fd707C82A73719592ef541270f`), then `attest("Water boils at
100 degrees Celsius at sea level", "https://en.wikipedia.org/wiki/Boiling_point")`
-- SUCCESS, MAJORITY_AGREE, leader's `eq_outputs` showed a genuine extracted
quoting span ("water boils at 100 degC, rounded from scientific precision of
99.97 degC..."), `supports:true`; `count()`/`get(0)` confirmed the
attestation was archived with a real `span_hash`. Then `attest("The moon is
made of cheese", "https://<a-deliberately-unreachable-.invalid-domain>")` --
SUCCESS (not a revert or hang), 4/5 agree, resolved cleanly to
`supports:false, span:"", span_hash:""` -- confirming the fetch-failure
guard works at this contract's call site too (the third confirmed site
after SemanticDeadman and CorroborationOracle).

**Also found this session:** the first `gltest` attempt produced a real
(non-flaky) `ImportError: cannot import name 'Buffer' from 'collections.abc'`
that superficially resembled the SynSent-hang/timeout flakiness documented
for `CorroborationOracle` the same day -- an empty output file with a
process that appeared to exit quickly. Root cause: the `gltest` command was
launched from a bare Bash shell, which resolves the miniconda3 BASE conda
env's Python (3.11.4), not the dedicated `genlayer` env (Python 3.12.13)
every prior successful run in this repo actually used -- `genlayer_py`
depends on `collections.abc.Buffer`, a Python 3.12+ stdlib addition absent
from 3.11. Fixed by explicitly `conda activate genlayer` before invoking
`gltest`; the re-run (correct env) passed 6/6 cleanly (265.79s).

**How to apply.** (1) When a catalog spec's consensus move conflicts with
what a primitive's own family/purpose actually requires for trustlessness,
follow the family's intent and document the deviation, rather than
following the literal one-liner -- check this against the primitive's
siblings in the same family first. (2) Before concluding a `gltest` failure
is environment flakiness (SynSent hang, connection timeout, etc.), actually
read the log content -- a real Python traceback (ImportError, in this case)
looks similar at a glance (empty-seeming output, quick process exit) but is
a completely different, deterministic failure that retrying without fixing
will reproduce every time. Always `conda activate genlayer` and confirm
`python --version` is 3.12.x before running `gltest` in this repo.

---

## 2026-07-04 — CorroborationOracle (V.12) reuses SemanticDeadman's web-fetch guard at a new call site; a genuine TCP SynSent hang required a kill-and-retry, not just a re-run

**Decision.** Built `CorroborationOracle.establish(question, urls)` matching
CONTRACTS.md's spec with `comparative` on a two-field result
(`{value, ratio_milli}`) extracted from N independently-fetched sources,
followed by a deterministic `require(ratio_milli >= threshold_milli)` gate
after consensus resolves -- the same "deterministic gate after the nondet
block settles" shape as SemanticDiffLedger's version bump and
AmbiguityGuard's status routing, applied here to accept/revert instead of
routing. Two implementation choices worth recording:
1. `urls` is a comma-delimited `str`, not a `DynArray[str]` -- reusing
   AmbiguityGuard's proven list-typed-calldata workaround a third time.
2. Every `gl.nondet.web.render()` call inside the nondet closure is wrapped
   in its own `try/except`, converting a fetch failure into a
   `"[FETCH FAILED: ...]"` snippet fed to the LLM rather than an uncaught
   `NondetException` that would abort the whole transaction -- reusing
   `SemanticDeadman.poke()`'s guard unchanged.

**Why.** CLAUDE.md is explicit that a proven pattern still needs its own
live confirmation at each new call site -- `SemanticDeadman`'s guard being
correct doesn't automatically mean `CorroborationOracle`'s usage of the
same primitive is correct, since the surrounding closure, prompt shape, and
failure handling differ. This was worth verifying deliberately rather than
assuming it "should just work."

Live-verified end to end before writing gltest: deployed two instances
against the same fixed (question, urls) pair -- a Wikipedia boiling-point
question against two Wikipedia pages -- with `threshold_milli=700` and
`threshold_milli=300` respectively. Both independently reproduced
`ratio_milli=500` (the LLM counted only 1 of 2 sources as an explicit
"agreeing" source, even though both pages restate the same value). The
700-threshold instance reverted correctly (majority-agreed deterministic
rollback, `"insufficient corroboration across sources"`, 3 agree/1
disagree/1 idle); the 300-threshold instance succeeded, returned
`"100 degC"`, and `count()`/`get(0)` confirmed the fact was genuinely
archived. Having the same real-world input reproduce identically twice is
what made it safe to write gltest assertions pinning both the low-threshold
-success and high-threshold-revert paths off one fixed (question, urls)
pair, rather than gambling on live LLM/web variance for each.

`gltest --network studionet tests/test_corroboration_oracle.py`: first
attempt hung mid-suite -- not the previously-known
RemoteDisconnected/ConnectionAbortedError/timeout flakiness (those surface
as Python exceptions and just need a retry), but a genuine TCP-level stall:
the process's CPU time showed zero growth across two consecutive ~5-minute
polls. `Get-NetTCPConnection -OwningProcess <pid>` confirmed a connection
stuck in `SynSent` state -- the handshake itself never completed. Unlike
exception-based flakiness, a stuck-but-alive process doesn't clear on its
own; had to `Stop-Process -Force` the stalled PIDs before re-running from
scratch. The clean re-run passed 7/7 (317.98s), including the test that had
shown a bare "F" in the killed first run (no traceback was ever captured
for it, since the process was killed mid-test rather than completing) --
strongly indicating the original failure was a downstream artifact of the
same network stall, not a real assertion failure, since a genuine bug in a
deterministic revert-path test would not have cleared on a clean retry with
zero code changes.

**How to apply.** When a `gltest` run appears to hang (not error out), check
CPU-time growth across two multi-minute polls before waiting longer -- flat
CPU time is a signal to check `Get-NetTCPConnection` for a `SynSent`-stuck
handshake and kill-and-retry, not to keep polling passively (unlike the
previously-known exception-based flakiness, which does clear with a plain
retry). Do not treat a single "F" from a run that was subsequently killed as
evidence of a real bug -- rerun clean first, since pytest's failure detail
is only written at the end of a completed session.

---

## 2026-07-03 — ConstitutionalContract (III.08) makes `core` immutable by simply never writing to it, and reuses AmbiguityGuard's delimited-string workaround for a second list-shaped parameter

**Decision.** Built `ConstitutionalContract` matching CONTRACTS.md's spec
with no consensus-move deviation (`non_comparative` on deterministic
`(core_principles, proposed_amendment)` input, the same shape as
IntentLock's `request()`). Two implementation choices worth recording:
1. `core: DynArray[str]` is populated once in `__init__` and there is no
   method anywhere in the contract -- owner-gated or otherwise -- that
   writes to it again. Immutability here is not a comment or a convention;
   it's the literal absence of a code path that could mutate it.
2. The constructor takes `core_principles: str` delimited by `|`, not a
   `DynArray[str]` argument as the spec's State line implies -- reusing
   AmbiguityGuard's proven workaround for list-typed calldata (no contract
   in this repo has ever exercised an actual list argument). Chose `|`
   instead of AmbiguityGuard's comma because core principles are full
   sentences that may themselves contain commas, where `options` in
   AmbiguityGuard were short single-word/phrase choices.

**Why.** CONTRACTS.md's spec is a product description, not an
implementation contract -- consistent with every prior deviation this
session (AmbiguityGuard, PolyglotConsensus, SemanticCommitReveal,
SemanticDiffLedger). Here the deviation is purely mechanical (still no
list-argument risk taken) and doesn't need justifying in the contract's own
docstring beyond a short note, unlike AmbiguityGuard's or
SemanticCommitReveal's deviations, which changed product-visible behavior
(state shape a caller would actually query).

Live-verified end to end before writing gltest: CLI deploy with one core
principle ("no treasury spend without a member vote") and empty initial
body; `propose_amendment()` with a DIRECT, explicit contradiction of that
principle ("the treasurer may unilaterally spend... at their sole
discretion") -- ACCEPTED, `accepted: false`, `body` confirmed unchanged;
`propose_amendment()` with an unrelated, clearly consistent clause (meeting
schedule) -- ACCEPTED, `accepted: true`, `body` correctly grew to
`"Amendment 2: ..."` (amendment count is 1-based off the full amendments
archive, not a separate "accepted count"). `gltest --network studionet
tests/test_constitutional_contract.py`: 7/7 passed cleanly on the first
attempt (336.40s), no flakiness.

**How to apply.** When a spec's State line implies a list-typed
constructor or method argument, default to the `|`-or-comma-delimited
`str` workaround (pick the delimiter based on whether the list items are
short tokens like AmbiguityGuard's `options`, or full sentences like this
contract's `core_principles`) rather than attempting an actual list
argument, until list-typed calldata is verified live somewhere in this
repo.

---

## 2026-07-03 — SemanticDiffLedger (III.07) uses comparative even though both compared texts are deterministic input, unlike IntentLock

**Decision.** Built `SemanticDiffLedger.propose()` with the `comparative`
equivalence principle CONTRACTS.md's spec names, even though `current`
(chain state) and `new_text` (calldata) are both deterministic and
identical on every validator -- the same input shape that led IntentLock's
`request()` to use `non_comparative` instead. Did not deviate here.

**Why.** The two contracts' judgments differ in kind, not just degree.
IntentLock's grant/deny call can be checked against explicit, mostly
mechanical criteria ("does this action satisfy every requirement in this
policy"), which is exactly the leader-decides/validators-verify shape
`non_comparative` is for. "Is this edit material or cosmetic" is a more
open-ended, genuinely interpretive judgment -- closer to DissensusOracle's
"how contested is this" than to a policy-compliance check. Letting each
validator independently re-derive the materiality verdict (comparative)
means real disagreement between different LLMs about whether a change
matters becomes a visible, meaningful signal (a revert) rather than being
smoothed over by one leader's opinion merely surviving a criteria check.
Also matches CONTRACTS.md's literal spec for this contract, so no deviation
needed to be justified or documented in the contract's own docstring beyond
explaining the choice.

Live-verified end to end before writing gltest: CLI deploy, `propose()`
with a starkly material edit (rent doubled, due date moved) -- ACCEPTED,
MAJORITY_AGREE, `version` correctly bumped 0->1, `current`/`snapshot(1)`
updated to the new text; then `propose()` with a purely cosmetic edit
(trailing whitespace only, which normalizes to byte-identical text after
`.strip()`) -- ACCEPTED, and `version`/`count` confirmed completely
unchanged (1 and 2 respectively), proving the cosmetic path leaves state
untouched rather than silently merging the proposed text.
`gltest --network studionet tests/test_semantic_diff_ledger.py`: 5/5
passed cleanly on the first attempt (186.51s), no flakiness.

**How to apply.** When a future primitive's spec names a consensus move
that seems structurally similar to one already built with a *different*
move (as this looked similar to IntentLock's non_comparative on
first glance), check whether the JUDGMENT itself is mechanical/
criteria-checkable (favor non_comparative) or genuinely interpretive/
contestable (favor comparative) rather than pattern-matching on "both
inputs are deterministic" alone -- that property alone doesn't decide which
move fits.

---

## 2026-07-03 — IntentLock (III.06) found and fixed a new empty-string calldata bug; three gltest runs needed for a clean pass, purely from network flakiness

**Decision.** Built `IntentLock` per spec with no state-shape or
consensus-move deviations (unlike SemanticCommitReveal/AmbiguityGuard/
PolyglotConsensus) -- `non_comparative` on deterministic `(policy, action)`
input is exactly what CONTRACTS.md's one-liner describes, and
`DynArray[Grant]` + `TreeMap[str, u256]` is the same proven archive/dedupe
idiom used throughout the repo. But live CLI smoke-testing caught a real
bug: `request(action, nonce)` called via `genlayer write <addr> request
--args "some action" ""` crashed on every validator with `AttributeError:
'int' object has no attribute 'strip'` at `nonce.strip()`. The empty-string
argument was decoded as a non-`str` type, not `""`. Fixed by applying the
exact same defensive pattern CLAUDE.md already documents for `Address`
arguments (`addr = who if isinstance(who, Address) else Address(who)`) to
both `action` and `nonce`: `act = (action if isinstance(action, str) else
"").strip()`.

**Why.** This is a new instance of a known CLASS of bug (GenVM/CLI doing
its own type inference on calldata rather than respecting the Python type
hint), not a new class of bug -- but it had never surfaced before because
no prior contract accepted a `str` parameter that a legitimate caller (or a
test asserting a revert-on-empty-input guard) would ever pass as literally
`""`. `IntentLock`'s nonce is optional-by-design ("empty nonce = no
one-shot binding"), which is exactly the shape that exposes this. Caught
early because CLAUDE.md's own testing philosophy (live CLI smoke test
BEFORE trusting gltest, and always checking `execution_result` rather than
just `status_name: ACCEPTED`) is what surfaced it: the write showed
`ACCEPTED`/`MAJORITY_AGREE` (validators unanimously agreeing the call
errors is still a form of consensus), and only a follow-up `get(0)` read
reverting with "no such grant" revealed the write hadn't actually
succeeded. Re-running the identical call with a non-empty nonce (`"abc123"`)
confirmed the fix was specific to the empty-string case, not a general
`nonce` handling problem, before touching the contract.

Separately: the first two full `gltest --network studionet
tests/test_intent_lock.py` runs each had exactly one failure (10/11), never
the same test twice, and both failures were pure connection-layer errors
(`RemoteDisconnected` on a `get_policy()` read after a successful deploy;
`ConnectionAbortedError [WinError 10053]` during a deploy's receipt-polling)
with zero contract-logic assertion failures across either run. The third
full run passed 11/11 cleanly (367.60s). This matches the exact
network-flakiness signature already documented and closed out on
2026-07-03 for SchellingResolver/ProofCarryingAnswer -- not a new pattern,
just a recurrence.

**How to apply.** (1) Any future `str` parameter that legitimately accepts
`""` (an optional field, a sentinel-for-unset convention, or is deliberately
tested with an empty-input revert case) needs the `isinstance(x, str)`
defensive coercion, not just parameters that happen to look like addresses.
(2) When CLI smoke-testing, never trust `status_name: ACCEPTED` /
"Write operation successfully executed" alone -- always check
`execution_result` (`SUCCESS` vs `ERROR`) inside the receipt, or read back
state afterward, before declaring a write verified. (3) A `gltest` run that
fails exactly one test with a connection-layer exception (not an assertion
error) is not evidence of a contract bug on its own -- retry up to twice
before investigating further, consistent with the existing flakiness
guidance.

---

## 2026-07-03 — SemanticCommitReveal (III.05) replaces timestamps with a phase state machine and a mutable TreeMap with two append-only DynArrays

**Decision.** Built `SemanticCommitReveal` diverging from CONTRACTS.md's
spec on two state-shape points while keeping its consensus description
exactly as written:
1. No "reveal window timestamps." Phase is an explicit two-state machine
   (`COMMIT` -> `REVEAL`) advanced by one owner-only deterministic call,
   `open_reveal_phase()`.
2. No single `TreeMap[Address, Commit]`. State is two independent,
   append-only `DynArray` archives (`commits`, `reveals`), each paired with
   its own `TreeMap[Address, u256]` "1 + index" existence map.

**Why.** (1) CLAUDE.md's "Known blockers" section already confirmed live
(an isolation probe dumping `dir(gl.message)`) that this runner has NO
clock, timestamp, or block-number accessor at all -- `gl.message.datetime`
doesn't exist. `SemanticDeadman` was already redesigned around this exact
finding; this is the same fix applied to a second primitive. (2) No
contract in this repo has verified a `TreeMap` keyed to an `@allow_storage`
dataclass VALUE live (every proven TreeMap use is a scalar `u256`), AND no
contract has ever written to an existing `DynArray` index
(`self.arr[i] = x`) -- every DynArray in every flagship is strictly
append-only. The spec's single mutable record implies both of those at
once. Rather than combine two unverified patterns, this contract used two
independently-proven ones: `commits`/`committer_index` mirrors
ProofCarryingAnswer's `seen` dedupe exactly, and adding a second archive
(`reveals`/`reveal_index`) mirrors SchellingResolver's
`submissions`/`winners` split. "Already revealed" is now "does a `reveals`
entry exist for this address" instead of reading a mutable field back out
of the original commit.

The consensus-move description in CONTRACTS.md's spec, by contrast, needed
NO deviation: the deterministic `sha256(intent + salt) == hash` check
really is what binds the commit phase, and `comparative` really is what
judges intent-vs-statement, exactly as written. This is unlike
AmbiguityGuard's and PolyglotConsensus's deviations, which touched the
consensus move itself -- this one is purely a state-shape substitution.

Live-verified end to end before writing gltest: CLI deploy, `commit()` on a
sha256 hash (ACCEPTED, all 5 validators AGREE -- fully deterministic, no
LLM reached), `open_reveal_phase()` (ACCEPTED), `reveal()` with matching
intent/salt/statement (ACCEPTED, MAJORITY_AGREE via the comparative round),
then `get_reveal(0)` confirming `accepted: true` with the correct
statement, `phase_now()` returning `REVEAL`, `count()`/`reveal_count()`
both `1`. `gltest --network studionet tests/test_semantic_commit_reveal.py`:
first attempt hit a single `RemoteDisconnected` on a plain `count()` read
inside an otherwise-passing test (9/10, matching the known transient TLS
flakiness pattern, not a contract issue -- the LLM reveal in that same test
had already succeeded before the read failed); full re-run passed 10/10
cleanly (370.76s), including that exact test on retry.

**How to apply.** Any future primitive whose catalog spec implies "one
record, updated in place, keyed by address" should default to this
dual-archive shape (N independent append-only `DynArray`s + `TreeMap[K,
u256]` index maps, one pair per logical "phase" or "field group" that gets
written at a different time) rather than attempting in-place `DynArray`
mutation or a TreeMap of a compound dataclass value, until one of those two
patterns is actually verified live in this repo.

---

## 2026-07-03 — Remaining-11 build order chosen: proven-pattern primitives first, shared-guard batch second, novel mechanisms last

**Decision.** After PolyglotConsensus shipped, chose this order for the
remaining primitives rather than the catalog's numeric order: (1) re-verify
SchellingResolver/ProofCarryingAnswer (debt cleanup, zero design risk), (2)
finish Semantic Machines (SemanticCommitReveal -> IntentLock ->
SemanticDiffLedger -> ConstitutionalContract -- all self-contained,
single-move consensus on patterns already proven), (3) the `gl.nondet.web.*`
trio (CorroborationOracle, ProvenanceAttestor, CanaryTripwire) as one batch,
since they share the one known risk (NondetException-on-fetch-failure,
already guarded in SemanticDeadman) and solving it once pays off three
times, (4) EscalatingVerdict (orchestrates multiple already-proven moves),
(5) AdversarialReview and EquivalenceRegistry last among the "new" builds --
AdversarialReview stages two advocates inside one leader block (nothing in
the repo does that yet) and EquivalenceRegistry's "other contracts fetch and
apply" a principle risks needing cross-contract **WRITE** calls, the one
surface CLAUDE.md still marks completely unexercised, (6) RealitySettledMarket
absolute last, since it composes AmbiguityGuard's ambiguity-refusal pattern
with the web-fetch trio's corroboration pattern and benefits most from both
already being battle-tested.

**Why.** Under the "make no mistakes" directive, front-loading certainty
matters more than following the catalog's arbitrary numbering. Every
primitive built so far in this session has needed at least one deliberate
deviation from its literal one-line CONTRACTS.md spec (see AmbiguityGuard,
PolyglotConsensus, and SemanticCommitReveal's entries below) precisely
because the spec describes a product guarantee, not a verified
implementation. Doing the two riskiest, most novel mechanisms
(AdversarialReview's dual-advocate staging, EquivalenceRegistry's likely
cross-contract WRITE need) dead last means eight more contracts' worth of
precedent will exist by the time either is attempted, instead of hitting
their design uncertainty early with the least context to resolve it.

**How to apply.** If this order needs to change (e.g. a user explicitly
wants a specific primitive next), that's fine -- this is a default, not a
constraint. But absent an explicit request, prefer finishing a family of
self-contained, single-move primitives before touching cross-contract WRITE
or multi-agent staging, since those are the two surfaces this repo has the
least live verification on.

---

## 2026-07-03 — SchellingResolver and ProofCarryingAnswer re-verified clean; 2026-07-02's TLS flakiness confirmed as a one-session network incident, not a recurring risk

**Decision.** Re-ran `gltest --network studionet` against both suites with no
code changes. `SchellingResolver`: 7/7 passed (265.06s), including the four
payable-path tests that had never completed on 2026-07-02
(`test_focal_cluster_wins_and_pool_splits`, `test_double_resolve_reverts`,
`test_claim_without_balance_reverts`, `test_resolve_requires_minimum_submissions`).
`ProofCarryingAnswer`: 4/4 passed (137.28s). Both moved from "Still open" to
"Fixed and reverified end-to-end" in CLAUDE.md; the standalone "Session-level
network/TLS flakiness" bullet was removed from CLAUDE.md's "Still open" list
since it described a resolved, one-time incident rather than a standing risk
to design around.

**Why.** 2026-07-02's session hit a family of TLS errors
(`SSLV3_ALERT_ILLEGAL_PARAMETER`, `SSLV3_ALERT_BAD_RECORD_MAC`, `[SSL]
record layer failure`, `RemoteDisconnected`) against `studio.genlayer.com`
specifically on these two suites' payable-path tests, while other suites ran
clean immediately before and after. That session already ruled out a hard
outage or contract regression (a raw `requests.post()` succeeded mid-episode,
partial tests within the affected suites passed cleanly during it). This
session's clean re-run on the first attempt for both suites, with zero
retries needed, confirms that diagnosis: it was transient
connection-reuse/keep-alive flakiness under `gltest`'s rapid polling loop,
not a property of these contracts or of studionet generally.

**How to apply.** If a future `gltest` run against ANY suite in this repo
hits a burst of TLS/connection errors concentrated on specific tests while
other suites run clean nearby in time, don't chase a contract-side fix --
retry the affected suite once or twice first. Only escalate to suspecting a
real regression if the same suite fails identically on a clean re-run with no
code changes in between, which has not happened here.

---

## 2026-07-02 — PolyglotConsensus (II.04) mixes comparative (submit) with non_comparative (same_meaning), diverging from CONTRACTS.md's single-move spec

**Decision.** Built `PolyglotConsensus` with two different consensus moves
for its two write methods, not one:
- `submit(text)` uses `gl.eq_principle.prompt_comparative` with a
  translation-invariant principle: each validator independently normalizes
  the source text to an English proposition, and the principle judges
  equivalence on asserted meaning (subject/predicate/polarity), not exact
  wording or source language.
- `same_meaning(id_a, id_b)` uses `gl.eq_principle.prompt_non_comparative`
  instead. By the time two propositions are already stored, the input (two
  fixed English strings read from chain state) is byte-identical on every
  node -- there's nothing left to disagree about except whether "same
  meaning" holds, which is exactly the asymmetric-verification case
  CLAUDE.md recommends `non_comparative` for. Also avoids paying for a
  second full ensemble/translation round just to compare two already-
  normalized strings.

Also decided state is a pull-style `DynArray[Proposition]` archive +
`TreeMap[str, u256]` SHA-256 dedupe map (ProofCarryingAnswer's pattern), not
the bare `TreeMap[str, str]` claim-hash -> normalized-proposition map
CONTRACTS.md's one-line spec names.

**Why.** CONTRACTS.md's spec for this contract (#4) only names the
comparative move and a bare `TreeMap[str, str]`. Neither is sufficient for
the API the spec itself requires: `submit(text) -> proposition_id` and
`same_meaning(id_a, id_b)` both need sequential integer handles, which a
bare hash-keyed TreeMap can't produce, and preserving `original_text` /
`detected_language` for audit needs more than a single string value. This
mirrors the same gap found in AmbiguityGuard's spec (see the entry below):
CONTRACTS.md's one-liners describe product behavior, not a literal
implementation contract. Reusing DynArray+seen (ProofCarryingAnswer) for
storage, and non_comparative for same_meaning (ProofCarryingAnswer's
verification-input pattern again) stays inside proven territory rather than
inventing new state or consensus shapes.

Live-verified end to end before writing gltest: CLI deploy (ACCEPTED),
`submit("The sky is blue.")` (ACCEPTED, MAJORITY_AGREE) normalized to
`{"normalized":"The sky is blue.","detected_language":"en"}`; then
`submit("Le ciel est bleu.")` (ACCEPTED) normalized to the *identical*
English proposition `"The sky is blue."` with `detected_language:"fr"` --
direct live confirmation the translation-invariant principle works, not
just a syntactic pass. `same_meaning(0, 1)` (ACCEPTED) is the first live
confirmation in this repo of `prompt_non_comparative` being used purely as
a judgment call over two already-stored strings, with no new state written.
`gltest --network studionet tests/test_polyglot_consensus.py`: 9/9 passed
cleanly in one run (431.07s), no flakes, no retries needed.

**How to apply.** A primitive whose CONTRACTS.md spec names only one
consensus move may legitimately need a second one for a different method on
the same contract -- pick the move per call-site based on whether the input
is fresh model output (comparative/non-comparative leader-does-the-work) or
already-agreed deterministic chain state (non_comparative is cheaper and
sufficient). Don't force every write in a contract through the single move
the one-line spec happens to mention.

---

## 2026-07-02 — AmbiguityGuard (II.02) reuses DissensusOracle's ensemble trick instead of the catalog's literal "let consensus itself fail" wording

**Decision.** Built `AmbiguityGuard` so the ABSTAIN decision is a
deterministic threshold compare (`commit_fraction_milli >=
abstain_threshold_milli`, plus a defensive check that the model's chosen
option is actually one of the caller-supplied options) run *after*
`gl.eq_principle.prompt_comparative` has already reached consensus on an
internal ensemble poll -- not by relying on the runtime itself failing to
reach consensus when "the leader answers X but a validator would abstain."

**Why.** CONTRACTS.md's spec for this contract (#2) literally describes the
consensus move as treating "leader answered X, validator would answer
ABSTAIN" as non-equivalent, with "persistent non-equivalence collapses to a
stored ABSTAIN." Taken at face value, that requires catching a
prompt_comparative consensus failure inside the contract and substituting a
value -- a mechanism no contract in this repo has used or verified, and
CLAUDE.md is explicit that every other primitive treats persistent
prompt_comparative disagreement as an ordinary uncaught revert (see
DissensusOracle, ConsensusThermometer, both confirmed live this way). Rather
than invent an unverified pattern to match the spec's prose exactly, reused
DissensusOracle's proven ensemble-poll technique (K independent internal
opinions, integer milli-unit fraction, comparative principle with a
tolerance band) and moved the "should this even count as an answer"
decision to a deterministic post-consensus threshold. This delivers the
same product guarantee (never a confident answer to an unanswerable
question) through a path already confirmed to work on this runner.

Also decided `options` is a single comma-separated string parameter, not a
list -- no contract in this repo has yet exercised a list-typed calldata
argument, and CLAUDE.md's "Storage types" cautions are specifically about
untested storage/argument shapes on this runner. Parsing a delimited string
inside the write method keeps the argument surface inside proven `str`
territory.

Live-verified end to end before writing gltest: CLI deploy (ACCEPTED), a
`judge("Is 7 a prime number?", "yes,no")` write (ACCEPTED, 3/5 validators
AGREE), then `get(0)`/`did_abstain()` reads confirmed the exact expected
shape (`status: "yes"`, `confidence_milli: 1000`, `did_abstain: false`).
`gltest --network studionet tests/test_ambiguity_guard.py`: 7/7 passed
cleanly in one run (343.45s), including both the low- and
high-abstain-threshold edge-case tests -- no flakes, no retries needed.

**How to apply.** When a future CONTRACTS.md spec's "Consensus" prose
describes a mechanism this repo hasn't verified (e.g. relying on
prompt_comparative's own rotation-exhaustion path, or a list-typed calldata
argument), don't build toward the literal prose -- check whether an already
-verified pattern (ensemble + threshold, `non_comparative` on
deterministic input, etc.) delivers the same product guarantee, and
document the substitution in the contract's docstring like this one does.
The spec describes behavior, not implementation.

---

## 2026-07-02 — ConsensusThermometer (VI.15) built self-contained, no cross-contract calls needed

**Decision.** Built `ConsensusThermometer` per its CONTRACTS.md spec exactly:
`assess(task) -> route` runs a cheap `comparative` probe that predicts (never
performs) the agreement a full analysis would reach, then a plain
deterministic threshold compare on the already-agreed
`predicted_agreement_milli` decides `FULL` vs `DEFERRED`. No
`gl.get_contract_at` calls of any kind, read or write.

**Why.** CLAUDE.md's build queue entry for this contract (written in an
earlier session) speculated it might "depend on `gl.get_contract_at` reads"
and might need to exercise the still-unverified `.emit()` write surface.
That turned out to be an assumption from the family name ("Reflexion")
rather than something the actual CONTRACTS.md spec (#15) requires -- the
spec's State/API/Consensus fields describe a fully self-contained archive
contract, identical in shape to `DissensusOracle` (same milli-unit
`comparative` pattern, same `DynArray` + `latest` index archive), just
predicting agreement instead of measuring it after the fact. Followed the
formal spec rather than the speculative build-queue note.

Live-verified end to end before writing gltest: CLI deploy (ACCEPTED,
MAJORITY_AGREE), `assess()` write (ACCEPTED after one round of rotation --
normal `prompt_comparative` behavior, not a bug), then `last_probe()`/
`count()` reads confirmed correct shape (`task_hash` a 64-char sha256 hex
digest, `predicted_agreement_milli` in `[0,1000]`, `routed_to` matching the
threshold comparison). `gltest --network studionet
tests/test_consensus_thermometer.py`: 6/6 passed cleanly in one run, no
network flakiness this time (contrast with the ProofCarryingAnswer/
SchellingResolver episode earlier the same day).

**How to apply.** Cross-contract `.emit()` writes remain genuinely
unverified in this repo -- this contract did not end up being the one that
tests it. The next contract that actually needs a cross-contract write
(rather than just belonging to a family whose name suggests
self-reflection) is still the one to confirm that surface first, per
CLAUDE.md's "Known blockers." Don't infer a contract's technical
dependencies from its family/thematic grouping in CONTRACTS.md -- read the
State/API fields, which are the actual spec.

---

## 2026-07-02 — Full gltest sweep across all 6 contracts: ASCII fix holds, JailbreakBounty payable path confirmed, session hit real network flakiness on 2 suites

**Decision.** Ran `gltest --network studionet` against all six contracts to
confirm the 2026-07-01 ASCII fix (see entry below) generalizes across the
whole repo, per explicit request. Final results:

- `DissensusOracle`: 4/4 PASSED (clean).
- `MirrorAudit`: 5/5 PASSED + isolation test 1/1 PASSED (verified earlier
  this session, unchanged).
- `SemanticDeadman`: 6/6 PASSED (verified earlier this session, unchanged).
- `JailbreakBounty`: 5/5 PASSED (clean) — **first-ever confirmation of the
  payable-fund path end-to-end.** `gltest`'s `.transact(value=N)` can send
  real payable value where the `genlayer` CLI cannot. Confirms `fund()`
  accepts and accumulates real value, and the owner-reclaim-then-withdraw
  pull-payment flow works with real funds. The break-to-challenger-payout
  path remains unconfirmed (no test forces the LLM to judge an attempt as a
  successful jailbreak).
- `SchellingResolver`: 2/7 passed cleanly across two full-suite attempts
  (`test_deploys_empty`, `test_submit_requires_stake` — both deterministic
  structural tests, confirming no code regression); the other 5, all on the
  payable/resolve path, were blocked by network flakiness both times. Left
  open, needs re-running.
- `ProofCarryingAnswer`: 4 attempts, 0 clean passes (1 test passed on one
  attempt, isolated) — entirely blocked by network flakiness. Left open,
  needs re-running.

**Why.** Mid-sweep, `gltest` runs against `ProofCarryingAnswer` and
`SchellingResolver` started intermittently failing with a family of TLS
errors (`SSLV3_ALERT_ILLEGAL_PARAMETER`, `SSLV3_ALERT_BAD_RECORD_MAC`,
`[SSL] record layer failure`, `RemoteDisconnected`) against
`studio.genlayer.com` — distinct from the DNS-resolution blips noted
elsewhere in this file. Ruled out as a hard outage or a code regression on
several grounds: a single raw `requests.post()` to the same endpoint
succeeded cleanly mid-episode; `DissensusOracle` and `JailbreakBounty` both
ran fully clean immediately before the flaky window opened; and a subset of
tests within the affected suites (2/7 `SchellingResolver`, 1/4
`ProofCarryingAnswer` on one attempt) also passed cleanly during the
episode. The pattern looks like connection-reuse/keep-alive breakage under
`gltest`'s rapid polling loop, not a server-side or contract-side problem.
Retried each blocked suite once or twice (never more, to avoid burning
cycles chasing a session-local network condition) before deciding to leave
them open rather than claim false confirmation.

Also confirmed a local environment gotcha along the way: this Bash tool's
shell does not persist `conda activate genlayer` across tool calls — a
`gltest` invocation without re-activating in the same command resolves to
the bare miniconda Python 3.11.4, which fails immediately with
`ImportError: cannot import name 'Buffer' from 'collections.abc'` (that ABC
was added in 3.12). Not a gltest or contract bug; just needs
`source .../conda.sh && conda activate genlayer && gltest ...` in one
command every time.

**How to apply.** The ASCII fix is now confirmed to generalize across all 6
contracts, not just the 2 verified on 2026-07-01 — no further action needed
there. `SchellingResolver` and `ProofCarryingAnswer` need a straight
re-run of `gltest --network studionet tests/test_schelling_resolver.py` and
`tests/test_proof_carrying_answer.py` in a future session once network
conditions are normal; no code changes are indicated by anything seen this
session. If a future `gltest` run hits the same TLS/connection error family,
retry once or twice and move on — don't chase it indefinitely, and don't
mistake it for a contract regression just because a "trivial" structural
test (like `test_deploys_empty`) happens to be the one that failed first.

---

## 2026-07-01 — gltest actually works now: root cause was non-ASCII characters, not funding or connectivity

**Decision.** Stripped every non-ASCII character (middle dot `.`, em dash `--`,
ellipsis `...`, box-drawing divider `-`) from every file under `contracts/`
(all 6 primitives plus the test fixture), replacing each with a plain-ASCII
equivalent. `README.md`/`CONTRACTS.md`/`CLAUDE.md`/`docs/*.md` keep their
normal typography, since they are never sent through the code path that
breaks.

**Why.** The previous entry (below) and CLAUDE.md both originally guessed
gltest's "Failed to get schema from all clients" failure was a
client-connectivity/configuration gap. That guess was wrong. The real cause,
found by reading `gltest`'s own source
(`gltest/contracts/contract_factory.py::_get_schema_with_fallback`) and
reproducing it directly: the schema-fetch call
(`client.get_contract_schema_for_code(contract_code=...)`) raises
`UnicodeEncodeError: 'ascii' codec can't encode characters ...` the instant
the contract's source contains ANY non-ASCII character. Proved this precisely
by deploying two versions of the same fixture via gltest — one containing a
single em dash (failed every time, same error) and one that was pure ASCII
(passed cleanly). `gltest`'s own internal logger, which would have surfaced
this immediately as a per-client warning, is `disabled = True` by default
(`gltest/logging.py`) — that's why three separate debugging attempts (config
fix, env-var fix, the funding guess) all only ever saw the generic top-level
`ValueError` with zero clue why.

  Every contract in this repo used an em dash, a middle dot (in the
  `PENUMBRA . <family> . <number>` header line), box-drawing dividers (in the
  `# -- section --` comments, 164-406 occurrences PER FILE), and one ellipsis
  throughout its docstring — meaning `gltest` had never actually worked
  against any real Penumbra contract before this was found, regardless of
  which contract was being tested. This wasn't a MirrorAudit-specific problem
  at all.

  Verified the fix works, not just compiles: added a root `conftest.py` that
  un-disables gltest's logger (so a future regression shows the real
  per-client error instead of the opaque top-level `ValueError`), then ran
  `gltest --network studionet` for real against two different contracts'
  full suites: `test_mirror_audit.py` (5/5 passed, including the live
  LLM-judgment conformance tests) and `test_semantic_deadman.py` (6/6 passed;
  2 initial failures were a transient DNS blip resolving
  `studio.genlayer.com`, confirmed by an immediate clean retry — not a
  regression).

**How to apply.** Any new contract file (family AmbiguityGuard onward) must
stay pure ASCII in its source, including test fixtures under
`contracts/fixtures/`. This is now the single most likely way a new contract
would silently break `gltest` while still passing `py_compile` and every
`genlayer` CLI smoke test (the CLI path doesn't go through this schema-fetch
call, so it never surfaced the bug all session). Before assuming a fresh
gltest failure is a connectivity/funding/account issue again, check for
non-ASCII characters first — `python3 -c "print([c for c in open(f).read() if ord(c)>127])"`
is enough to confirm in one line.

---

## 2026-07-01 — MirrorAudit: confirmed cross-contract reads, found an uncatchable dispatch fault, and a gltest infra gap

**Decision.** Before writing `MirrorAudit`, ran a live isolation test first
(same methodology as every other unverified surface in this repo): deployed a
throwaway stub target contract (`get_label() -> str`, `get_count() -> int`)
and a probe contract that calls
`gl.get_contract_at(addr).view().<method>()` against it. Confirmed the untyped
proxy returns the value DIRECTLY — a plain `str`/`int`, not a wrapper — exactly
as CLAUDE.md's "Contract-to-contract" convention already assumed but had never
tested. Built `MirrorAudit` on top of that with `_read_target_status()`
expecting the target to expose `status() -> str` (an explicit, documented
assumption, since CONTRACTS.md's one-liner spec doesn't name a method
convention), and live-tested `audit()` against a real deployed `SemanticDeadman`
instance with both a true and a deliberately false spec — both judged
correctly.

**Why.** This is the first time any contract in this repo has actually
exercised `gl.get_contract_at`, previously flagged as the single
least-verified surface here. Confirming it live (rather than trusting the SDK
docs, which have been wrong five separate times already this repo) was
necessary before shipping a contract whose entire purpose depends on it.

  A second finding, NOT anticipated: auditing a target that does not
  implement `status()` at all does not surface through the `try/except`
  wrapped around the proxy call as a clean custom message. It fails as an
  uncatchable runner-level dispatch fault
  (`ValueError: call to private method
  <function Contract.__handle_undefined_method__...>`), raised while GenVM
  resolves the method against the TARGET's own execution context — a
  different, less recoverable failure mode than `gl.nondet.web.render`'s
  catchable `NondetException` (see the entry below). The outcome is still
  safe (every validator agrees the call errors, the transaction reverts
  cleanly, `count()` confirmed unchanged afterward), just with an ugly
  traceback instead of a friendly message. The contract's docstring originally
  claimed the try/except would handle this cleanly; that claim was corrected
  the moment live testing proved it false, rather than left in place.

  A third, informal and unconfirmed observation: probing `gl.get_contract_at`
  against a synthetic address with NO deployed contract at all (not a real
  target, not even a nonexistent-method case) caused a write transaction to
  never reach a terminal status — the CLI timed out waiting for `ACCEPTED`.
  This was not reproduced deliberately enough to treat as a confirmed rule,
  but it's a real enough signal that "audit an arbitrary, unverified address"
  should be treated as a possible-hang risk, not just a possible-revert risk,
  until someone deliberately confirms or refutes it.

  A fourth, separate finding while trying to run `gltest` for the first time
  in this repo's history: `gltest.config.yaml`'s `studionet:` key had no
  value, which YAML parses as `null`, but gltest requires every network entry
  to be a dict — fixed to `studionet: {}`. Deeper problem, NOT fixed, and
  CORRECTED here after an initial wrong guess: every attempted deploy via
  `gltest` itself fails with `ValueError: Failed to get schema from all
  clients (default, hosted studio, and local)`. The first draft of this entry
  guessed this was because gltest's `default_account` fixture generates a
  fresh, unfunded keypair with no GEN for gas — Judith corrected this: studionet
  does not require gas fees at all, and this repo's own `genlayer` CLI account
  sat at 0 GEN through every successful deploy this session, which already
  disproved the guess before it was even checked against gltest's source.
  Reading `gltest/contracts/contract_factory.py::_get_schema_with_fallback`
  confirms the real mechanism: it fetches the schema from the contract's
  SOURCE CODE via `get_contract_schema_for_code(...)`, independent of any
  account balance, tried against three separately-configured clients
  ("default", "hosted studio", "local") in turn. All three failed here — the
  actual cause is an unconfirmed client-connectivity/configuration gap in this
  shell, not a funding gap. This repo's actual verification path remains the
  live `genlayer` CLI, not `gltest`, until the real cause is found.

**How to apply.** Any future contract using `gl.get_contract_at` for reads can
now cite this entry as confirmation the read shape works — no need to
re-isolate that specific question. But: (1) never assume a target implements
whatever method you call — wrap it, but know the wrap won't always produce a
clean message; (2) never audit or read from a caller-supplied, unverified
address without accepting the (unconfirmed but observed) hang risk; (3) don't
assume studionet needs GEN/gas for anything other than an actual `payable`
value transfer — it doesn't, and this repo has now disproven the opposite
guess twice. (The gltest failure mentioned above as a "client-connectivity
gap" was itself a wrong guess, corrected two entries up — it was a non-ASCII
encoding bug, not connectivity.)

---

## 2026-07-01 — SemanticDeadman: `gl.message.datetime` doesn't exist on this runner; switched to content-diffing

**Decision.** `SemanticDeadman` was first written to pass `gl.message.datetime`
(last-confirmed-alive and current, as opaque strings) into the LLM prompt,
planning to let the model judge elapsed time semantically rather than parsing
it in Python. Deploying that version live immediately reverted with
`AttributeError: 'MessageType' object has no attribute 'datetime'`. A
throwaway isolation probe (`dir(gl.message)`, deployed and read live) confirmed
this pinned runner's `gl.message` exposes ONLY `chain_id`, `contract_address`,
`origin_address`, `sender_address`, `value` — no datetime, no block number, no
clock at all, despite `.datetime` being documented in the SDK's own published
API text. The contract was redesigned to drop time entirely: `last_alive_ts`
became `last_alive_snapshot`, a short LLM-produced description of the most
recent observed activity, and `poke()` now asks the model whether the freshly
fetched source has visibly ADVANCED beyond that stored snapshot — pure content
diffing, no clock involved anywhere.

**Why.** There was no fallback option once the isolation probe confirmed the
attribute truly does not exist (this isn't a format-uncertainty problem to
work around, it's a nonexistent API on this runner). Content-diffing turned
out to fit the contract's own thesis better anyway: "semantic inactivity, not
a missed timestamp ping" is arguably more honest without a clock at all — a
timestamp comparison would have been a slightly-dressed-up heartbeat check,
whereas asking "has this source's observable content moved forward" is the
actually-semantic version of liveness.

  A second bug surfaced only by live-testing the release path with a
  deliberately dead URL: `gl.nondet.web.render()` raises an uncaught
  `NondetException` on fetch failure (confirmed cause: `TLD_FORBIDDEN` for a
  `.invalid` test domain; a second test against a resolvable-but-nonexistent
  `.com` domain also triggered the same uncaught-exception path) — the
  original code let this propagate and abort the whole `poke()` transaction,
  even though the prompt text already claimed "a fetch error counts as NOT
  alive." Fixed by wrapping the `render()` call in `try/except` inside the
  nondet closure and returning `{"alive": false, ...}` directly on failure,
  never reaching the LLM. Re-verified live: `poke()` against a genuinely dead
  `.com` domain now cleanly returns `true` (released) instead of crashing.

**How to apply.** Do not reintroduce `gl.message.datetime`, or assume any
clock/timestamp/block-number accessor exists, anywhere in this repo without
re-running the exact same isolation probe first (deploy a throwaway contract
that dumps `dir(gl.message)`, read it live) — the SDK's published docs are not
reliable evidence that an attribute exists on this pinned runner build; only a
live deploy is. Separately: any contract that calls `gl.nondet.web.render`/
`.get` inside a nondet closure must wrap the call in `try/except` and decide
deliberately what a fetch failure should mean for consensus, rather than
letting an uncaught `NondetException` abort the transaction — add this to the
"Mark the unverified surfaces" checklist for every future web-fetching
contract (CorroborationOracle, ProvenanceAttestor, CanaryTripwire,
RealitySettledMarket all touch this same surface).

---

## Template for new entries

```
## YYYY-MM-DD — <short title>

**Decision.** <what was chosen>

**Why.** <the reasoning, especially if it overrides an obvious/naive default>

**How to apply.** <when this should/shouldn't generalize to future contracts>
```
