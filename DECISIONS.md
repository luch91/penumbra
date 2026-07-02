# DECISIONS — Penumbra

A running log of non-obvious decisions made while building this repo: what was
chosen, why, and what it rules out. This is not a changelog (git history covers
that) — it's the reasoning that isn't visible from reading the code alone.
Updated every session; newest entries at the top.

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
