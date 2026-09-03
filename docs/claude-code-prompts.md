# Claude Code prompts for Penumbra

Paste the batch prompt below into Claude Code from the repo root. A reusable single-contract template follows it.

---

## Batch 2 kickoff (paste this)

```
Read README.md, CONTRACTS.md, and DECISIONS.md in full before writing anything.
reading: it documents ten bugs that passed py_compile cleanly and only broke
on a live deploy. Do not reproduce them.
Then read the existing catalog contracts and PenumbraGate as the style and correctness reference:
contracts/dissensus_oracle.py, contracts/jailbreak_bounty.py,
contracts/proof_carrying_answer.py, contracts/schelling_resolver.py,
contracts/semantic_deadman.py, contracts/mirror_audit.py. Match their
structure, comment density, and the deterministic/non-deterministic
discipline exactly.

Build the next primitive:

  1. ConsensusThermometer   (family VI)  -- cheap agreement pre-check, routes to a fallback when low

This depends on gl.get_contract_at READS, which are now confirmed live (see
DECISIONS.md documents the runner-specific cross-contract view() behavior
directly, confirmed via MirrorAudit). If ConsensusThermometer also needs
cross-contract WRITES (.emit()), that half is still completely unverified --
build it defensively per the MirrorAudit instructions below regardless, and
treat the first live deploy as the actual test, not a formality.

Use the spec for each in CONTRACTS.md as the contract; do not redesign the
purpose or the consensus move. Honor the repository rules in README.md and
the implementation decisions in DECISIONS.md, in particular:
- Target the `py-genlayer` runner pinned to a runner hash (never a floating tag
  like py-genlayer:test, which is rejected at deploy) with `from genlayer import *`
  and `class X(gl.Contract)`. Do NOT use the v0.3 `import genlayer as gl` layout.
- Non-deterministic work goes in an argument-free inner function that never
  touches self/storage; read values into locals first.
- Canonicalize anything compared by strict_eq; store scores as integer
  milli-units, never floats.
- Pick the consensus move the spec names and write a comment explaining WHY
  that move (not just what the code does).
- Header must be the pinned pragma line followed immediately by a real module
  docstring (triple-quoted), never a run of '#' comment lines. GenVM's parser
  concatenates every consecutive '#' line after the pragma before JSON-parsing
  it for Depends -- a second '#' line corrupts that parse and fails deploy with
  invalid_contract/absent_runner_comment. This is the single most likely
  mistake to reproduce from copying the old flagship style out of git history.
- Never build TreeMap[str, typing.Any] as an ad-hoc "return a dict" builder for
  a view method. Its storage descriptor expects .as_bytes-bearing values and
  crashes on a plain str. Any read method that returns multiple fields (status,
  get, assess, audit, etc.) must return str via canonical(...)/json.dumps(...).
- Never pass response_format="json" to gl.nondet.exec_prompt inside a
  prompt_comparative-wrapped inner function -- confirmed to crash GenVM with a
  raw INTERNAL_ERROR VM fault, reproduced independent of prompt size. Ask the
  model for JSON as plain text instead and parse it yourself (tolerate
  markdown code fences); copy the parse_json_response pattern from
  dissensus_oracle.py or jailbreak_bounty.py.
- Payouts use the pull-payment ledger pattern with the marked native-transfer hook.
- Write contracts/<snake>.py in PURE ASCII -- no em dashes, middle dots, box-
  drawing dividers, curly quotes, or ellipses anywhere in the file, including
  the docstring. Confirmed live: gltest's schema-fetch client crashes with
  UnicodeEncodeError on any non-ASCII byte in a contract's source, and its own
  logger that would show this is disabled by default, so the failure looks
  like a generic, unexplained "Failed to get schema from all clients" instead.
  Every existing contract in this repo was fixed for exactly this (see
  DECISIONS.md's 2026-07-01 entry). Use --, -,
  ., and ... instead. This restriction is ONLY for files under contracts/ --
README.md/CONTRACTS.md/DECISIONS.md/docs/*.md are unaffected and keep normal
  typography.
- Do NOT read gl.message.datetime, or assume any clock/timestamp/block-number
  accessor exists. Confirmed live: this pinned runner's gl.message exposes
  ONLY chain_id, contract_address, origin_address, sender_address, value --
  accessing .datetime raises AttributeError, despite being documented in the
  SDK's own API text. If a contract needs a notion of elapsed time or "has
  this changed since last observed," use content-diffing (store what was last
  observed, ask the model whether the fresh fetch has advanced beyond it) --
  see contracts/semantic_deadman.py for the reference pattern.
- Any call to gl.nondet.web.render/.get MUST be wrapped in try/except inside
  its nondet closure. Confirmed live: a fetch failure (dead domain, disallowed
  TLD, DNS failure) raises an uncaught NondetException rather than returning
  an error value, which aborts the whole transaction if uncaught. Catch it and
  decide deliberately what "fetch failed" should mean for the judgment (see
  semantic_deadman.py's judge_liveness() for the reference pattern -- a fetch
  failure there is treated as decisive evidence of "not alive").
- Cross-contract reads (`gl.get_contract_at(addr).view().method(args)`) are now
  confirmed live: the untyped proxy returns the value DIRECTLY (a plain
  `str`/`int`, no wrapper) -- see MirrorAudit and its isolation test. Still
  build any cross-contract call defensively:
  * Use the UNTYPED proxy form. Do NOT use the @gl.contract_interface decorator
    -- per the SDK it is pure type-sugar with no runtime effect.
  * Isolate EVERY cross-contract call in a single private helper, e.g.
    `_read_target(self, addr) -> dict`, so any syntax fix is one line. No other
    method may call the proxy directly.
  * The read is deterministic -- do it in the method body, pull the result into a
    local, THEN run the LLM conformance judgment in the nondet block. Never call
    another contract from inside a nondet block.
  * Wrap the proxy call in try/except -- but do NOT assume this produces a clean
    message for every failure. CONFIRMED LIVE: calling a method the target
    doesn't implement at all raises an UNCATCHABLE runner-level dispatch fault
    (`ValueError: call to private method <function
    Contract.__handle_undefined_method__...>`), not a Python exception your
    try/except can intercept. The transaction still reverts safely (no
    corrupted state), just with a raw traceback instead of your message -- say
    so honestly in the docstring rather than claiming the try/except handles it
    (MirrorAudit's docstring was corrected on exactly this point after live
    testing disproved the original claim).
  * Calling `gl.get_contract_at` against an address with no deployed contract
    at all was observed, informally and not yet confirmed as a general rule,
    to hang rather than revert (a write transaction that never reached a
    terminal status). Do not write an automated test around this -- a hang
    would stall the test run -- but do not claim an unverified address is safe
    to audit either.
  * Add a `## Runner verification` section to the docstring listing exactly what
    to confirm in Studio: that `.view().<method>()` returns the value directly
    (not a wrapper), that positional args work, and the symptom if not.
  * Write an EXTRA isolation test `tests/test_<snake>_read.py` that deploys a
    tiny stub target contract exposing one view (put it under
    contracts/fixtures/, not alongside the 20 catalog primitives -- see
    contracts/fixtures/audit_stub_target.py), deploys your contract, and
    asserts only that it can read the stub's state. This makes a cross-contract
    failure pinpoint instantly on studionet instead of hiding inside a
    conformance-judgment test.

For each contract you must produce:
  - contracts/<snake_name>.py with the header line, a module docstring covering
    purpose / why-this-consensus-move / state design / reuse, inlined helpers,
    one gl.Contract subclass named to match the catalog (PascalCase).
  - tests/test_<snake_name>.py -- gltest tests that assert INVARIANTS and SHAPES
    only (preconditions revert, dedupe, ledger math, score ranges, clear-cut
    inputs land on the expected side of a threshold). Never assert exact LLM text.
  - flip the entry in CONTRACTS.md and README.md from o to [x] and link the source.

After writing each contract:
1. Run `python3 -m py_compile contracts/<file>.py` and fix any syntax error.
   This is a necessary gate, not a sufficient one -- py_compile passed cleanly
   on every one of the ten bugs found in the existing built contracts.
2. Live-smoke-test it yourself via the genlayer CLI before moving to the next
   contract: `genlayer deploy --contract contracts/<file>.py --args ...`, then
   `genlayer call`/`genlayer write` its public methods. An account must already
   be unlocked (check `genlayer account show` first) -- do not attempt to
   recover or guess a keystore password; if none is unlocked, ask rather than
   creating a new one silently. Confirm `execution_result` is `SUCCESS`, not
   just that the transaction was `ACCEPTED` -- a transaction can reach `ACCEPTED`
   via validator consensus even when every validator independently errored
   (this happened during Penumbra's own smoke testing: all validators agreed
   the contract was invalid, and consensus still "succeeded").
3. gltest now works end-to-end in this repo (see DECISIONS.md --
   it took finding a real UnicodeEncodeError bug to get there, fixed by
   keeping contracts/*.py pure ASCII per the rule above). Run
   `gltest --network studionet tests/test_<snake>.py` (conda env `genlayer`,
   Python 3.12+, `.env` copied from `.env.example`) and confirm it actually
   passes -- don't just write the test file and assume it would pass. A stray
   non-ASCII character is now the single most likely reason it wouldn't.

Work in small commits, one contract per commit, message:
"Penumbra: add <Name> (<family>)". Show me each file when it's done and pause
for a quick review before the next one. If any spec detail is ambiguous, state
your assumption inline in the docstring rather than asking -- keep momentum.
```

---

## Reusable single-contract template

Use this to build any one primitive from the queue later:

```
Read README.md, CONTRACTS.md, and DECISIONS.md and the
six built contracts first. Build <NAME> exactly as specified in
CONTRACTS.md (family <N>). Consensus move: <strict_eq | prompt_comparative |
prompt_non_comparative | run_nondet> -- use it and comment why. If it uses
prompt_comparative with exec_prompt, do NOT pass response_format="json" -- plain
text plus manual parsing only (see parse_json_response in dissensus_oracle.py).
Any read method returning multiple fields must return str via canonical(...),
never TreeMap[str, typing.Any]. Do not read gl.message.datetime (does not
exist on this runner -- see semantic_deadman.py for the content-diffing
alternative). Wrap any gl.nondet.web.* call in try/except inside its nondet
closure (fetch failure raises an uncaught NondetException otherwise). Deliver
contracts/<snake>.py + tests/test_<snake>.py (invariant-based) and flip its [x]
in CONTRACTS.md and README.md. py_compile the file, then live-smoke-test it
via `genlayer deploy` / `call` / `write` before considering it done --
py_compile alone did not catch any of the seven bugs found in the existing
built contracts. Commit as "Penumbra: add <NAME> (<family>)".
```

---

## Notes on what NOT to let Claude Code do
- Don't let it "modernize" imports to the v0.3 `gl.contract.Contract` API -- Studio's deployable runner uses the star-import convention. This is the most likely silent break.
- Don't let it mock the Anthropic/LLM calls in tests -- these are live by design.
- Don't let it weaken a precondition or invariant to make a flaky non-deterministic assertion pass. Re-run instead.
- Don't let it collapse multiple contracts into one file -- one `gl.Contract` per module.
- Don't let it treat a clean `py_compile` as proof the contract works. Ten real bugs in the existing built contracts passed `py_compile` and only surfaced on a live deploy or a real gltest run -- require an actual `genlayer deploy` plus a method call per contract.
- Don't let it copy the box-drawn `#`-comment header style from git history or old drafts of the flagships -- only the current docstring-based header is deploy-safe.
- Don't let it assume `gl.message` has a `.datetime`, block number, or any clock -- confirmed absent on this runner despite being in the SDK docs.
- Don't let it leave a `gl.nondet.web.render`/`.get` call unwrapped in try/except -- a fetch failure raises an uncaught exception, not a returned error value.
- Don't let it write an em dash, middle dot, box-drawing divider, or any other non-ASCII character anywhere inside `contracts/*.py` -- confirmed to silently break `gltest` with an unhelpful generic error.

## Mark the unverified surfaces (applies to every contract)
Two API surfaces are not yet confirmed on the runner: cross-contract `.emit()`
(write) calls and native value transfer-out. (Cross-contract `.view()`
[reads] and `gl.nondet.web.*`'s return shape on `mode="text"` are now
confirmed live via MirrorAudit and SemanticDeadman respectively -- both plain
values, no wrapper -- but JS-rendered pages / `mode="html"` remain untested;
treat that as still open too.) Whenever a contract touches one of the
fully-open surfaces, require Claude Code to:
1. isolate it in a single private helper,
2. tag the exact line with `# VERIFY:`,
3. add a short `## Runner verification` note to the docstring (what to confirm in
   Studio + the symptom if it's wrong),
so that when Judith runs studionet, any runner-level surprise is one grep away
and one-line to fix -- never buried inside business logic.
