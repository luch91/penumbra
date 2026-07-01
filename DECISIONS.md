# DECISIONS — Penumbra

A running log of non-obvious decisions made while building this repo: what was
chosen, why, and what it rules out. This is not a changelog (git history covers
that) — it's the reasoning that isn't visible from reading the code alone.
Updated every session; newest entries at the top.

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
attempt to fix gltest's client-connectivity gap as a side quest inside an
unrelated contract's build — it's a standalone infra task, tracked here and in
CLAUDE.md's "Known blockers" so it isn't lost; (4) don't assume studionet
needs GEN/gas for anything other than an actual `payable` value transfer —
it doesn't, and this repo has now disproven the opposite guess twice.

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
