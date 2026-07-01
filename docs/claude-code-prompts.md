# Claude Code prompts for Penumbra

Paste the batch prompt below into Claude Code from the repo root (after `claude` picks up `CLAUDE.md`). A reusable single-contract template follows it.

---

## Batch 2 kickoff (paste this)

```
Read CLAUDE.md, README.md, and CONTRACTS.md in full before writing anything —
CLAUDE.md's "Known blockers & open verification gaps" section is not optional
reading: it documents four bugs that passed py_compile cleanly and only broke
on a live deploy. Do not reproduce them.
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
- Header must be the pinned pragma line followed immediately by a real module
  docstring (triple-quoted), never a run of '#' comment lines. GenVM's parser
  concatenates every consecutive '#' line after the pragma before JSON-parsing
  it for Depends — a second '#' line corrupts that parse and fails deploy with
  invalid_contract/absent_runner_comment. This is the single most likely
  mistake to reproduce from copying the old flagship style out of git history.
- Never build TreeMap[str, typing.Any] as an ad-hoc "return a dict" builder for
  a view method. Its storage descriptor expects .as_bytes-bearing values and
  crashes on a plain str. Any read method that returns multiple fields (status,
  get, assess, audit, etc.) must return str via canonical(...)/json.dumps(...).
- Never pass response_format="json" to gl.nondet.exec_prompt inside a
  prompt_comparative-wrapped inner function — confirmed to crash GenVM with a
  raw INTERNAL_ERROR VM fault, reproduced independent of prompt size. Ask the
  model for JSON as plain text instead and parse it yourself (tolerate
  markdown code fences); copy the parse_json_response pattern from
  dissensus_oracle.py or jailbreak_bounty.py.
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

After writing each contract:
1. Run `python3 -m py_compile contracts/<file>.py` and fix any syntax error.
   This is a necessary gate, not a sufficient one — py_compile passed cleanly
   on every one of the four bugs found in the first three flagships.
2. Live-smoke-test it yourself via the genlayer CLI before moving to the next
   contract: `genlayer deploy --contract contracts/<file>.py --args ...`, then
   `genlayer call`/`genlayer write` its public methods. An account must already
   be unlocked (check `genlayer account show` first) — do not attempt to
   recover or guess a keystore password; if none is unlocked, ask rather than
   creating a new one silently. Confirm `execution_result` is `SUCCESS`, not
   just that the transaction was `ACCEPTED` — a transaction can reach `ACCEPTED`
   via validator consensus even when every validator independently errored
   (this happened during Penumbra's own smoke testing: all validators agreed
   the contract was invalid, and consensus still "succeeded"). Do not run the
   full gltest suite yourself; the CLI smoke test is enough to catch a broken
   deploy before it compounds across 4 contracts.

Work in small commits, one contract per commit, message:
"Penumbra: add <Name> (<family>)". Show me each file when it's done and pause
for a quick review before the next one. If any spec detail is ambiguous, state
your assumption inline in the docstring rather than asking — keep momentum.
```

---

## Reusable single-contract template

Use this to build any one primitive from the queue later:

```
Read CLAUDE.md (including "Known blockers & open verification gaps") and the
three flagship contracts first. Build <NAME> exactly as specified in
CONTRACTS.md (family <N>). Consensus move: <strict_eq | prompt_comparative |
prompt_non_comparative | run_nondet> — use it and comment why. If it uses
prompt_comparative with exec_prompt, do NOT pass response_format="json" — plain
text plus manual parsing only (see parse_json_response in dissensus_oracle.py).
Any read method returning multiple fields must return str via canonical(...),
never TreeMap[str, typing.Any]. Deliver contracts/<snake>.py +
tests/test_<snake>.py (invariant-based) and flip its ✅ in CONTRACTS.md and
README.md. py_compile the file, then live-smoke-test it via `genlayer deploy` /
`call` / `write` before considering it done — py_compile alone did not catch
any of the four bugs found in the existing flagships. Commit as
"Penumbra: add <NAME> (<family>)".
```

---

## Notes on what NOT to let Claude Code do
- Don't let it "modernize" imports to the v0.3 `gl.contract.Contract` API — Studio's deployable runner uses the star-import convention. This is the most likely silent break.
- Don't let it mock the Anthropic/LLM calls in tests — these are live by design.
- Don't let it weaken a precondition or invariant to make a flaky non-deterministic assertion pass. Re-run instead.
- Don't let it collapse multiple contracts into one file — one `gl.Contract` per module.
- Don't let it treat a clean `py_compile` as proof the contract works. Four real bugs in the first three flagships passed `py_compile` and only surfaced on a live deploy — require an actual `genlayer deploy` plus a method call per contract.
- Don't let it copy the box-drawn `#`-comment header style from git history or old drafts of the flagships — only the current docstring-based header is deploy-safe.

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
