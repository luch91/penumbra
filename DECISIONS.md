# DECISIONS — Penumbra

A running log of non-obvious decisions made while building this repo: what was
chosen, why, and what it rules out. This is not a changelog (git history covers
that) — it's the reasoning that isn't visible from reading the code alone.
Updated every session; newest entries at the top.

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
