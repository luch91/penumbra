# Claude Code prompts for Penumbra

Paste the batch prompt below into Claude Code from the repo root (after `claude` picks up `CLAUDE.md`). A reusable single-contract template follows it.

---

## Batch 2 kickoff (paste this)

```
Read CLAUDE.md, README.md, and CONTRACTS.md in full before writing anything.
Then read all three existing flagships as the style and correctness reference:
contracts/dissensus_oracle.py, contracts/jailbreak_bounty.py,
contracts/proof_carrying_answer.py. Match their structure, comment density, and
the deterministic/non-deterministic discipline exactly.

Build the next batch of 4 primitives, one at a time, fully finishing each
(source + tests + catalog/README status) before starting the next:

  1. SchellingResolver      (family IV)  — semantic clustering + focal-point payout
  2. MirrorAudit            (family VI)  — reads another contract via gl.get_contract_at, judges conformance
  3. ConsensusThermometer   (family VI)  — cheap agreement pre-check, routes to a fallback when low
  4. SemanticDeadman        (family VII) — liveness judged from a web source, not a timestamp ping

Use the spec for each in CONTRACTS.md as the contract; do not redesign the
purpose or the consensus move. Honor every rule in CLAUDE.md, in particular:
- Target the `py-genlayer` runner pinned to a runner hash (never a floating tag
  like py-genlayer:test, which is rejected at deploy) with `from genlayer import *`
  and `class X(gl.Contract)`. Do NOT use the v0.3 `import genlayer as gl` layout.
- Non-deterministic work goes in an argument-free inner function that never
  touches self/storage; read values into locals first.
- Canonicalize anything compared by strict_eq; store scores as integer
  milli-units, never floats.
- Pick the consensus move the spec names and write a comment explaining WHY
  that move (not just what the code does).
- Payouts use the pull-payment ledger pattern with the marked native-transfer hook.
- For MirrorAudit, the cross-contract read is the riskiest, least-verified API
  in this repo. Build it defensively:
  * Use the UNTYPED proxy form: `gl.get_contract_at(addr).view().method(args)`.
    Do NOT use the @gl.contract_interface decorator — per the SDK it is pure
    type-sugar with no runtime effect, so it only adds a way to break.
  * Isolate EVERY cross-contract call in a single private helper, e.g.
    `_read_target(self, addr) -> dict`, so any syntax fix is one line. No other
    method may call the proxy directly.
  * The read is deterministic — do it in the method body, pull the result into a
    local, THEN run the LLM conformance judgment in the nondet block. Never call
    another contract from inside a nondet block.
  * Tag the proxy line with `# VERIFY:` and wrap the read in try/except that
    re-raises a clear message ("cross-contract view() shape differs — see
    Runner verification") so a wrong proxy shape fails loudly, not opaquely.
  * Add a `## Runner verification` section to the docstring listing exactly what
    to confirm in Studio: that `.view().<method>()` returns the value directly
    (not a wrapper), that positional args work, and the symptom if not.
  * Write an EXTRA isolation test `tests/test_mirror_audit_read.py` that deploys
    a 3-line stub target contract exposing one view, deploys MirrorAudit, and
    asserts only that MirrorAudit can read the stub's state. This makes a
    cross-contract failure pinpoint instantly on studionet instead of hiding
    inside a conformance-judgment test.

For each contract you must produce:
  - contracts/<snake_name>.py with the header line, a module docstring covering
    purpose / why-this-consensus-move / state design / reuse, inlined helpers,
    one gl.Contract subclass named to match the catalog (PascalCase).
  - tests/test_<snake_name>.py — gltest tests that assert INVARIANTS and SHAPES
    only (preconditions revert, dedupe, ledger math, score ranges, clear-cut
    inputs land on the expected side of a threshold). Never assert exact LLM text.
  - flip the entry in CONTRACTS.md and README.md from ◻️ to ✅ and link the source.

After writing each contract, run `python3 -m py_compile contracts/<file>.py` and
fix any syntax error before moving on. Do not run gltest yourself (it needs a
live LLM network); I will run it against studionet.

Work in small commits, one contract per commit, message:
"Penumbra: add <Name> (<family>)". Show me each file when it's done and pause
for a quick review before the next one. If any spec detail is ambiguous, state
your assumption inline in the docstring rather than asking — keep momentum.
```

---

## Reusable single-contract template

Use this to build any one primitive from the queue later:

```
Read CLAUDE.md and the three flagship contracts first. Build <NAME> exactly as
specified in CONTRACTS.md (family <N>). Consensus move: <strict_eq |
prompt_comparative | prompt_non_comparative | run_nondet> — use it and comment
why. Deliver contracts/<snake>.py + tests/test_<snake>.py (invariant-based) and
flip its ✅ in CONTRACTS.md and README.md. Honor every non-determinism rule in
CLAUDE.md, py_compile the file, and commit as "Penumbra: add <NAME> (<family>)".
```

---

## Notes on what NOT to let Claude Code do
- Don't let it "modernize" imports to the v0.3 `gl.contract.Contract` API — Studio's deployable runner uses the star-import convention. This is the most likely silent break.
- Don't let it mock the Anthropic/LLM calls in tests — these are live by design.
- Don't let it weaken a precondition or invariant to make a flaky non-deterministic assertion pass. Re-run instead.
- Don't let it collapse multiple contracts into one file — one `gl.Contract` per module.

## Mark the unverified surfaces (applies to every contract)
Three API surfaces are not yet confirmed on the runner: cross-contract
`view()`/`emit()` calls, native value transfer-out, and live `gl.nondet.web.*`
fetch shapes. Whenever a contract touches one, require Claude Code to:
1. isolate it in a single private helper,
2. tag the exact line with `# VERIFY:`,
3. add a short `## Runner verification` note to the docstring (what to confirm in
   Studio + the symptom if it's wrong),
so that when Judith runs studionet, any runner-level surprise is one grep away
and one-line to fix — never buried inside business logic.
```
