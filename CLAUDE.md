# CLAUDE.md — Penumbra

Operating context for Claude Code in this repository. Read this fully before writing or editing any contract. The single most expensive failure mode here is reaching for **stale GenLayer syntax** from training data. The conventions below are the *current, deployable* ones, verified against the live SDK. Follow them exactly.

---

## What this repo is

Penumbra is a library of **GenLayer Intelligent Contract primitives** — reusable, single-file Python contracts that use the consensus layer as a building block. Not apps, not demos, not thin LLM wrappers. The thesis: *disagreement is a measurement instrument, not a bug.*

Each contract is a standalone `.py` file in `contracts/`, deployable as-is to GenLayer Studio. There is **no package, no shared import at deploy time** — `lib/penumbra_consensus.py` is a copy-paste reference, and each contract inlines the few helpers it needs.

Read `README.md` (thesis + catalog) and `CONTRACTS.md` (full spec of all 20) before building. Study the seven built primitives as the canonical style: `contracts/dissensus_oracle.py`, `contracts/jailbreak_bounty.py`, `contracts/proof_carrying_answer.py`, `contracts/schelling_resolver.py`, `contracts/semantic_deadman.py`, `contracts/mirror_audit.py`, `contracts/consensus_thermometer.py`.

---

## The GenLayer API — CURRENT, DEPLOYABLE CONVENTION

Target the `py-genlayer` runner with star imports, **pinned to a runner hash — never a floating tag**. Studionet now matches the Asimov and Bradbury testnets: floating tags (`py-genlayer:test`, `py-genlayer:latest`) are rejected at deploy with `invalid_contract`, because every validator must resolve to the *same* runner binary or consensus breaks. The current single-file pin is `py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6` (multi-file contracts use `py-genlayer-multi:...`). Get the authoritative hash from the [Available Runners](https://sdk.genlayer.com/main/impl-spec/appendix/available-runners.html) appendix, and re-read it if a deploy returns `invalid_contract` — runner hashes advance over time. **Do not migrate to the v0.3 `import genlayer as gl` / `gl.contract.Contract` layout** — it is not what Studio's deployable runner uses here and will break deploys. If you think the SDK changed, check `https://sdk.genlayer.com/main/_static/ai/api.txt` before editing; do not guess.

### Skeleton
```python
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
from genlayer import *
import json
import typing

class MyPrimitive(gl.Contract):
    # state: type-annotated class attributes
    owner: Address
    total: u256
    notes: TreeMap[Address, str]
    log: DynArray[str]

    def __init__(self, seed: str = ""):
        self.owner = gl.message.sender_address

    @gl.public.view
    def read(self) -> str:
        return self.notes.get(self.owner, "")

    @gl.public.write
    def write(self, value: str) -> None:
        self.notes[gl.message.sender_address] = value
```

### Storage types (deterministic state)
- Allowed: `str`, `bool`, `bytes`, `Address`, `u8..u256`, `i8..i256`, `bigint`, `TreeMap[K, V]`, `DynArray[T]`, `Array[T, N]`.
- **Forbidden:** plain `int`, `list`, `dict`, or un-parameterized generics (`TreeMap` alone). Use `u256`/`bigint`, `DynArray[T]`, `TreeMap[K, V]`.
- **`TreeMap[str, typing.Any]` used as an ad-hoc "return a dict-like object" builder is broken** — confirmed by testing: `out["field"] = some_str` raises `AttributeError: 'str' object has no attribute 'as_bytes'`. The storage descriptor backing `TreeMap` expects values with `.as_bytes` (`Address`/`bytes`-like); it does not support heterogeneous `Any`-typed scalars, even as a throwaway local (not just as `self.` state). `TreeMap[K, V]` with a single concrete, homogeneous value type (e.g. `TreeMap[Address, u256]`) is unaffected and works fine. **For any read method that needs to return a heterogeneous structure (`status()`, `get()`, etc.), return `str` via `canonical(...)`/`json.dumps(...)`, not `TreeMap`.**
- Nested records: decorate a dataclass with `@allow_storage`:
  ```python
  from dataclasses import dataclass
  @allow_storage
  @dataclass
  class Record:
      who: Address
      amount: u256
  ```
- Allocate a generic storage object in memory with `gl.storage.inmem_allocate(Item[str], data, label)`.
- `TreeMap`/`DynArray` are auto-initialized; you do **not** need to assign them in `__init__`.

### Methods & money
- `@gl.public.view` — read-only, no gas, returns data.
- `@gl.public.write` — mutates state.
- `@gl.public.write.payable` — can receive value; read it with `gl.message.value`.
- Message context: `gl.message.sender_address`, `gl.message.value`, `gl.message.origin_address`, `gl.message.contract_address`, `gl.message.chain_id`.
- **Payouts:** use the pull-payment pattern (credit a `TreeMap[Address, u256]`, withdraw separately). The exact native-transfer-out call is unverified on this runner — leave the marked integration hook and keep the internal ledger authoritative.
- **`genlayer write` (CLI v0.39.2) cannot send payable value** — its `write.ts` hardcodes `value: 0n` on every call; `--fee-value` only sets the gas/fee deposit, unrelated to `gl.message.value`. Confirmed by testing `JailbreakBounty.fund()`: the call succeeds but `bounty` stays 0. To smoke-test a `.payable` method, use Studio's browser UI (has a dedicated value field) or a raw RPC call — not the CLI.

### Reverting
```python
try:
    _Err = gl.vm.UserError
except Exception:
    _Err = Exception
def require(cond, msg):
    if not cond:
        raise _Err(msg)
```
Any uncaught exception fails the transaction and rolls back.

### Addresses
`Address("0x...")` to construct; `.as_hex`, `.as_bytes`, `.as_int`. **`Address.ZERO` is declared in the SDK source but was `AttributeError` on the pinned runner in testing — do not rely on it.** For a zero/null address, construct explicitly: `Address("0x0000000000000000000000000000000000000000")`.

**Accepting an address parameter: do NOT blindly `str`-then-`Address(...)`.** Confirmed by testing: when a caller (at minimum, `genlayer-cli`'s `--args`) passes a hex-address-shaped argument, GenVM decodes it into a native `Address` object on arrival regardless of the Python parameter's `str` type hint. Calling `Address(who)` on an already-`Address` value then crashes (`TypeError: cannot convert 'Address' object to bytes`) — this runner's bundled `Address.__init__` lacks the `isinstance(val, Address)` early-return that the SDK's GitHub `main` branch has. Type the parameter as `Address` and handle both cases defensively:
```python
@gl.public.view
def claimable_of(self, who: Address) -> int:
    addr = who if isinstance(who, Address) else Address(who)
    return int(self.claimable.get(addr, u256(0)))
```
Found and fixed in both `SchellingResolver.claimable_of` and `JailbreakBounty.claimable_of`. Audit any other method taking an address argument for the same pattern.

---

## NON-DETERMINISM — the rules that break contracts if ignored

LLM calls and web reads are non-deterministic. They MUST be quarantined inside an **argument-free inner function** and reconciled by an Equivalence Principle.

**Hard rules:**
1. A nondet block is `def inner():` with **no arguments**.
2. It may **NOT** access `self` or storage. Read what you need into locals first and close over them.
3. **Canonicalize** any value compared by `strict_eq`: `json.dumps(obj, sort_keys=True, separators=(",",":"))`. Two validators producing the "same" dict must serialize identically.
4. Floats are fine *inside* a nondet block, but store probabilities/scores as **integers** (e.g. milli-units, `value * 1000`). Deterministic float math is software-emulated and slow; integers never drift.
5. `gl.nondet.exec_prompt(prompt, response_format="json")` returns a **parsed dict**, not a string.
6. **`response_format="json"` crashes GenVM when the call sits inside `gl.eq_principle.prompt_comparative`** — confirmed by isolation testing on the pinned runner (raw `INTERNAL_ERROR`/VM fault, not a Python exception, reproducible). Inside a `prompt_comparative`-wrapped inner function, call `gl.nondet.exec_prompt(prompt)` with **plain text** instead, instruct the model to return JSON in the prompt text, and parse the response yourself (tolerate markdown code fences — strip ```` ``` ```` and locate the outermost `{...}` before `json.loads`). This is untested with `strict_eq` / `prompt_non_comparative`; the failure is specific to the `prompt_comparative` combination as verified.

**Correct shape:**
```python
@gl.public.write
def judge(self, question: str) -> str:
    q = question                      # pull into a local
    def inner():
        data = gl.nondet.exec_prompt(
            f"Answer in JSON: {q}", response_format="json"
        )
        return json.dumps(data, sort_keys=True, separators=(",", ":"))
    agreed = gl.eq_principle.strict_eq(inner)
    self.last = json.loads(agreed)["answer"]   # storage write OUTSIDE the block
    return self.last
```

### Non-deterministic primitives
- `gl.nondet.exec_prompt(prompt, *, response_format="text"|"json", images=None)`
- `gl.nondet.web.render(url, *, mode="text"|"html") -> str`
- `gl.nondet.web.get(url, *, headers={})` · `gl.nondet.web.post(url, *, body=None, headers={})`

### The four consensus moves — pick deliberately, document the choice
1. `gl.eq_principle.strict_eq(inner)` — validators must produce byte-identical output. Cheapest, strictest. Use after canonicalizing deterministic-ish output.
2. `gl.eq_principle.prompt_comparative(inner, principle)` — each validator re-runs `inner`; an LLM judges whether its result is equivalent to the leader's under `principle`. Use for "different words, same meaning." This move secretly *measures agreement*.
3. `gl.eq_principle.prompt_non_comparative(inner, task=..., criteria=...)` — leader does the work; validators only verify integrity against `criteria`. The asymmetric move (cheap verify). Best when the **input is identical on every node** (passed as args), so the only thing to disagree about is the judgment.
4. `gl.vm.run_nondet(leader_fn, validator_fn)` — custom adjudication; `validator_fn(result) -> bool`. Use only when the three above genuinely can't express the rule, and add a focused test.

### Contract-to-contract
**Prefer the untyped proxy.** The `@gl.contract_interface` decorator is, per the SDK, purely type-sugar with *no runtime function* — it compiles to the same proxy call. So skip the decorator and call the proxy directly; it's the actual runtime path and one less thing to break.
```python
other = gl.get_contract_at(addr)          # untyped proxy
val = other.view().latest_verdict()       # read (deterministic) — positional args
other.emit(value=u256(0)).resolve(q)      # write — positional args
# deploy a child: gl.deploy_contract(code=..., args=[...], kwargs={}, value=u256(0))
```
Rules:
- A cross-contract **read is deterministic** — do it in the method body, pull the result into a local, then run any LLM judgment in the nondet block. Never call another contract from inside a nondet block.
- **This is the single least-verified surface in the repo.** Whenever you use it: (1) isolate every cross-contract call in one private helper so a fix is one-line, (2) tag each such call with a `# VERIFY:` comment, and (3) add a `## Runner verification` note to the contract docstring stating what to check in Studio and the symptom if the proxy shape differs (e.g. "`.view()` returns a wrapper, not the value"). See the MirrorAudit build instructions.

### DO NOT use (dead/old API — common training-data mistakes)
| Wrong (old) | Right (current) |
|---|---|
| `gl.exec_prompt(...)` | `gl.nondet.exec_prompt(...)` |
| `gl.get_webpage(...)` | `gl.nondet.web.render(...)` |
| `gl.eq_principle_strict_eq(fn)` | `gl.eq_principle.strict_eq(fn)` |
| `gl.eq_principle_prompt_comparative(fn, p)` | `gl.eq_principle.prompt_comparative(fn, p)` |
| `gl.ContractAt(addr)` | `gl.get_contract_at(addr)` |
| `from genlayer import Rollback` | `gl.vm.UserError` |
| `gl.advanced.run_nondet(...)` | `gl.vm.run_nondet(...)` |
| accessing `self` inside a nondet block | read into locals first |
| storing `int`/`list`/`dict` | `u256`/`DynArray[T]`/`TreeMap[K,V]` |

---

## Known blockers & open verification gaps

Everything below was found by live-deploying contracts to studionet via the CLI across four smoke-test sessions — not just `python3 -m py_compile`. Read this before assuming an untested pattern "should" work; the SDK docs and this file's own prior guidance were wrong on eleven separate points below.

**Fixed and reverified end-to-end (safe to build on):**
- GenVM's runner-comment parser concatenates every consecutive `#`-comment line after the `Depends` pragma into one blob before JSON-parsing it — a multi-line `#`-comment header (the box-drawn doc-comment style used in early drafts of these contracts) corrupts that parse and fails deploy with `invalid_contract`/`absent_runner_comment`. Fixed in all three flagships by moving documentation into a real module docstring. **Do this for every new contract** — pragma line, then a docstring, never a second `#` line.
- `Address.ZERO` is absent on the pinned runner (see "Addresses" above).
- `TreeMap[str, typing.Any]` as an ad-hoc dict builder is broken (see "Storage types" above).
- `response_format="json"` inside `gl.eq_principle.prompt_comparative` crashes GenVM with a raw `INTERNAL_ERROR` VM fault — reproduced 3 of 4 attempts, including with the minimum `ensemble_size`, ruling out prompt size as the cause; an isolation test with plain-text `exec_prompt` succeeded cleanly every time. Fixed in `DissensusOracle` and `JailbreakBounty` via `parse_json_response()` (see NON-DETERMINISM rule 6 above). **Untested with `strict_eq` or `prompt_non_comparative`** — the failure is specific to the `prompt_comparative` combination as verified; don't generalize the ban beyond that without testing.
- Accepting an `Address` argument via `str` + `Address(who)` crashes when the caller passes a hex-address-shaped value — GenVM auto-decodes it as a native `Address` regardless of the parameter's type hint, and re-wrapping an already-`Address` value crashes on this runner (see "Addresses" above). Found in and fixed for both `JailbreakBounty.claimable_of` and `SchellingResolver.claimable_of`; audited the other two flagships, no other occurrences exist.
- **`gl.message.datetime` does not exist on this runner** — the SDK's published API text (`sdk.genlayer.com/main/_static/ai/api.txt`) documents `genlayer.message.datetime: str`, but a live isolation probe (a throwaway contract that dumps `dir(gl.message)` and returns it, deployed and read on studionet) confirmed `gl.message` exposes only `chain_id`, `contract_address`, `origin_address`, `sender_address`, `value` — accessing `.datetime` raises `AttributeError: 'MessageType' object has no attribute 'datetime'`. **There is no clock, timestamp, or block-number accessor available at all on this runner.** Any contract needing a notion of elapsed time must find another primitive (e.g. content-diffing — see `SemanticDeadman`, which was redesigned around this exact finding; full reasoning in `DECISIONS.md`).
- **`gl.nondet.web.render()`/`.get()` raise an uncaught `NondetException` on fetch failure** instead of returning an error value — confirmed live via a deliberately dead URL (`{'causes': ['TLD_FORBIDDEN'], ...}` for a reserved `.invalid` TLD, and the same uncaught-exception path for a resolvable-but-nonexistent `.com` domain). If the nondet closure doesn't wrap the call in `try/except`, the whole transaction aborts instead of treating "source unreachable" as a judgeable outcome. Fixed in `SemanticDeadman.poke()` by catching the exception inside the closure and returning a canonical `{"alive": false, ...}` directly, never reaching the LLM. **Any future contract that calls `gl.nondet.web.*` must do the same** — CorroborationOracle, ProvenanceAttestor, CanaryTripwire, and RealitySettledMarket all touch this surface and need this guard.
- **Cross-contract READS via `gl.get_contract_at(addr).view().method()` are now confirmed** — the untyped proxy returns the value directly (plain `str`/`int`, no wrapper), exactly as the "Contract-to-contract" convention above describes. Confirmed twice: a throwaway isolation probe (a stub target with `get_label()`/`get_count()`) and live in `MirrorAudit.audit()` against a real deployed `SemanticDeadman` instance, correctly reading its `status()` JSON and reaching accurate conformance verdicts for both a true and a deliberately false spec. **This is the first confirmation of what was previously the single least-verified surface in the repo.**
- **But calling a method the target doesn't implement is an UNCATCHABLE runner-level fault, not a Python exception** — confirmed live auditing a target lacking `status()`: fails with `ValueError: call to private method <function Contract.__handle_undefined_method__...>`, raised while GenVM resolves the method against the target's own execution context. A `try/except` around the proxy call in the CALLING contract does **not** catch this (unlike the `NondetException` case above, which is catchable). The outcome is still safe — every validator agrees the call errors and the transaction reverts cleanly with no corrupted state, verified via `count()` unchanged after the failed call — but any contract calling a target whose method existence isn't guaranteed should expect a raw traceback, not a custom revert message, in that case. See `MirrorAudit`'s docstring for the fuller writeup.
- **`gltest` now runs successfully end-to-end against studionet — but ONLY if the contract's source is pure ASCII.** Real root cause, found by reading `gltest`'s own source and reproducing directly (2026-07-01): `_get_schema_with_fallback()` (`gltest/contracts/contract_factory.py`) fetches the schema via `client.get_contract_schema_for_code(contract_code=...)`, and that client-side call raises `UnicodeEncodeError: 'ascii' codec can't encode characters ...` the instant the contract's source contains ANY non-ASCII character — confirmed by testing an em-dash-free copy of a fixture (passed) against the original with one em dash (failed identically every time). `gltest`'s own internal logger that would have surfaced this is `disabled = True` by default (`gltest/logging.py`), which is why every prior attempt this session only saw the generic `ValueError: Failed to get schema from all clients` with no clue why. **Every contract in this repo used em dashes, a middle dot, box-drawing dividers, and one ellipsis throughout — meaning gltest had never worked against any real Penumbra contract before this was found.** Fixed (2026-07-01, Judith's explicit choice) by stripping all non-ASCII characters from every file under `contracts/` (·→., —→--, …→..., ─→-) — confirmed via `gltest --network studionet` actually passing on `test_mirror_audit.py` (5/5) and `test_semantic_deadman.py` (6/6, two initial DNS-blip failures cleared on retry). **This is now the primary regression risk for every future contract**: `README.md`/`CONTRACTS.md`/`CLAUDE.md`/`docs/*.md` may keep their typographic style freely (never sent through this schema-fetch call) — but any file under `contracts/` (including test fixtures) must stay pure ASCII. A root repo `conftest.py` now un-disables `gltest`'s logger so a future regression surfaces the real per-client error instead of the opaque `ValueError`.
- **`JailbreakBounty`'s payable `fund()` path is now confirmed end-to-end via `gltest`** (2026-07-02, closing half of what was previously listed under "Still open" below) — `gltest`'s `.transact(value=N)` can send real payable value where the `genlayer` CLI cannot (see the CLI limitation still listed below). `test_funding_accumulates` confirms `fund()` accepts and accumulates real value (1000 then 500 -> bounty 1500); `test_owner_can_reclaim_unbroken_pool` confirms the owner-reclaim-then-withdraw pull-payment flow works end-to-end with real funds (2000 funded -> reclaimed -> withdrawn successfully). All 5 tests in `test_jailbreak_bounty.py` passed live. **Still unconfirmed:** the full break-to-challenger-payout path — no test forces the LLM to judge a jailbreak attempt as successful (per the "never bet on exact LLM output" testing philosophy), so a challenger actually collecting a bounty via `claim()`/`withdraw()` after a genuine break has never been exercised.

**Still open — do not claim these are verified:**
- **`SchellingResolver`'s real payable/resolve path has never executed end-to-end.** Every non-payable guard is confirmed live (`resolve()`, `submit()`, `claim()`, `get()`, `winning_indices()` all revert correctly on empty/invalid state — `test_deploys_empty` and `test_submit_requires_stake` both passed cleanly via `gltest` on 2026-07-02), but `submit()` requires a real stake, so the `resolve()` LLM-clustering path has never run. Attempted via `gltest --network studionet tests/test_schelling_resolver.py` twice on 2026-07-02; both attempts hit session-level network flakiness (see below) on the payable-path tests specifically (`test_focal_cluster_wins_and_pool_splits`, `test_double_resolve_reverts`, `test_claim_without_balance_reverts`, `test_resolve_requires_minimum_submissions`) before completing. Needs re-running in a future session — no code changes indicated.
- **`ProofCarryingAnswer` could not be re-verified via `gltest` on 2026-07-02** due to the same network flakiness (see below) — 4 attempts, 0 clean passes (1 test passed on one attempt, isolated). Its ASCII-fix status from the original two-contract verification pass (`MirrorAudit`, `SemanticDeadman`) is not itself in doubt, but this specific suite needs re-running in a future session once network conditions are stable.
- **Session-level network/TLS flakiness observed 2026-07-02, distinct from the DNS-resolution blips noted elsewhere**: `gltest` runs against `ProofCarryingAnswer` and `SchellingResolver` intermittently failed with a family of TLS errors (`SSLV3_ALERT_ILLEGAL_PARAMETER`, `SSLV3_ALERT_BAD_RECORD_MAC`, `[SSL] record layer failure`, `RemoteDisconnected`) against `studio.genlayer.com`, evidently connection-reuse/keep-alive related under `gltest`'s rapid polling loop. Confirmed NOT a hard outage or code issue: a single raw `requests.post()` to the same endpoint succeeded cleanly mid-episode, `DissensusOracle` and `JailbreakBounty` both ran fully clean immediately before the flaky window started, and a subset of tests within the affected suites (2/7 `SchellingResolver`, 1/4 `ProofCarryingAnswer` on one attempt) also passed cleanly during it. If a future `gltest` run hits this pattern, retry once or twice — don't treat it as a contract regression, but also don't retry indefinitely; if it persists across a whole session, note it and move on rather than burning cycles.
- **`genlayer write` (CLI v0.39.2) cannot send payable value at all** — `write.ts` hardcodes `value: 0n`; `--fee-value` is an unrelated gas/fee-deposit concept. There is currently no CLI-only way to smoke-test any `.payable` method via the raw CLI (use `gltest`'s `.transact(value=N)` instead, or Studio's browser UI which has a dedicated value field). (`SemanticDeadman` sidesteps this entirely — its `poke()`/`check_in()` core paths are non-payable and have been fully verified live, including the actual release path against both a live and a deliberately dead source; only its optional `fund()` needs Studio or `gltest`.)
- **Cross-contract WRITE calls (`gl.get_contract_at(addr).emit()...`) remain completely unexercised.** Only the read half (`.view()`) is confirmed (see above). `ConsensusThermometer` turned out to be self-contained (per its CONTRACTS.md spec, no cross-contract calls at all -- the FULL/DEFERRED routing decision is a plain deterministic threshold compare against the already-agreed `predicted_agreement_milli`), so it did not end up exercising this surface. A future contract that genuinely needs `.emit()` must confirm its shape separately before it's treated as safe.
- **Calling `gl.get_contract_at` on an address with no deployed contract code at all appears to hang rather than revert.** Observed once, informally, while probing an isolation contract with a synthetic invalid address (not a real deployed contract): the write transaction never reached a terminal status and the CLI timed out waiting for `ACCEPTED`. This is distinct from — and possibly worse than — the clean "target lacks this method" revert above. Not reproduced deliberately or confirmed as a general rule; treat "audit an arbitrary, unverified address" as a real risk (possible hang, not just a revert) until this is tested properly, and do not write an automated test around it (a hang would stall the test run).

---

## Toolchain

- **Studio** (`studio.genlayer.com`) — paste a contract, deploy, exercise methods. Fastest feedback; use it to smoke-test before tests.
- **CLI** — `genlayer init` (choose an LLM provider when prompted), `genlayer up` to run localnet, `genlayer deploy --contract contracts/<file>.py --args ...`.
- **Tests** — `genlayer-test` (the `gltest` runner). `pip install -r requirements-dev.txt`.

---

## Testing (gltest)

```python
from gltest import get_contract_factory, create_account
from gltest.assertions import tx_execution_succeeded

def test_x():
    factory = get_contract_factory("DissensusOracle")   # CLASS name
    c = factory.deploy(args=[7, 250])                    # constructor args
    receipt = c.resolve(args=["..."]).transact()         # write -> receipt
    assert tx_execution_succeeded(receipt)
    data = c.latest_verdict().call()                     # view -> value
    assert data["dissensus_milli"] < 400
```
- Read: `contract.method(args=[...]).call()`. Write: `contract.method(args=[...]).transact()`.
- Payable: `.transact(value=N)`.
- Fixtures available: `gl_client`, `default_account`, `accounts`.
- Run: `gltest --network studionet` (LLM-backed) or `--network localnet` only if providers/`--ollama` were configured.

**Testing philosophy — non-negotiable:** intelligent-contract tests assert **invariants and shapes**, never exact LLM strings. Pin the contract's guarantees: preconditions revert, dedupe works, ledger math balances, scores fall in valid ranges, a clear-cut input lands on the low/high side of a threshold. A borderline case may occasionally flake because the model is non-deterministic — re-run before treating it as a real failure. Never weaken a guard just to make a flaky assertion pass.

---

## Definition of done for a new primitive

A contract is complete only when all of these exist:
1. `contracts/<snake_name>.py` — header `# { "Depends": "py-genlayer:<pinned-runner-hash>" }` (pin the hash, never a floating tag — see the deployable-convention section), a module docstring covering **purpose · why-this-consensus-move · state design · reuse**, inlined helpers, one `gl.Contract` subclass (PascalCase, matches the catalog name).
2. `tests/test_<snake_name>.py` — invariant-based gltest tests.
3. `CONTRACTS.md` — flip the entry from ◻️ to ✅ and link the source.
4. `README.md` — flip the catalog status to ✅.
5. `python3 -m py_compile contracts/<file>.py` passes (syntax gate; full execution needs GenVM).
6. **`contracts/<file>.py` (and any file under `contracts/`, including test fixtures) is pure ASCII — no em dashes, middle dots, box-drawing dividers, curly quotes, or ellipses.** Confirmed live (2026-07-01): `gltest`'s schema-fetch client crashes with `UnicodeEncodeError` on any non-ASCII byte in a contract's source, silently (its own logger is disabled by default) breaking every test in this repo until found. Use `--`, `-`, `.`, and `...` instead. This restriction applies ONLY inside `contracts/` — `README.md`/`CONTRACTS.md`/`CLAUDE.md`/`docs/*.md` are never sent through this call and may keep their normal typography.

Style: keep the deterministic/non-deterministic boundary visually obvious. Comment *why* a consensus move was chosen, not just what the code does. Match the prose density of the existing flagships.

---

## Build queue (remaining 13, fully specified in CONTRACTS.md)

Next up:
- **AmbiguityGuard** (II) — a drop-in wrapper that returns a verdict or `ABSTAIN`, never a confident answer to an unanswerable question. `comparative` with a principle that treats "leader answered X, validator would answer ABSTAIN" as non-equivalent. Self-contained, no cross-contract surface.

Then: PolyglotConsensus, SemanticCommitReveal, IntentLock, SemanticDiffLedger, ConstitutionalContract, AdversarialReview, CorroborationOracle, ProvenanceAttestor, CanaryTripwire, EquivalenceRegistry, EscalatingVerdict, RealitySettledMarket.

Note: CorroborationOracle, ProvenanceAttestor, CanaryTripwire, and RealitySettledMarket all call `gl.nondet.web.*` — wrap every such call in `try/except` inside its nondet closure (see "Known blockers" above, the `NondetException`-on-fetch-failure finding from `SemanticDeadman`).

## References
- API (authoritative, machine-readable): https://sdk.genlayer.com/main/_static/ai/api.txt
- Docs: https://docs.genlayer.com/developers/intelligent-contracts
- Equivalence principle: https://docs.genlayer.com/understand-genlayer-protocol/core-concepts/optimistic-democracy/equivalence-principle
- gltest: https://pypi.org/project/genlayer-test/
