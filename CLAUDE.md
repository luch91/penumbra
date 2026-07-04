# CLAUDE.md — Penumbra

Operating context for Claude Code in this repository. Read this fully before writing or editing any contract. The single most expensive failure mode here is reaching for **stale GenLayer syntax** from training data. The conventions below are the *current, deployable* ones, verified against the live SDK. Follow them exactly.

---

## What this repo is

Penumbra is a library of **GenLayer Intelligent Contract primitives** — reusable, single-file Python contracts that use the consensus layer as a building block. Not apps, not demos, not thin LLM wrappers. The thesis: *disagreement is a measurement instrument, not a bug.*

Each contract is a standalone `.py` file in `contracts/`, deployable as-is to GenLayer Studio. There is **no package, no shared import at deploy time** — `lib/penumbra_consensus.py` is a copy-paste reference, and each contract inlines the few helpers it needs.

Read `README.md` (thesis + catalog) and `CONTRACTS.md` (full spec of all 20) before building. Study the seventeen built primitives as the canonical style: `contracts/dissensus_oracle.py`, `contracts/jailbreak_bounty.py`, `contracts/proof_carrying_answer.py`, `contracts/schelling_resolver.py`, `contracts/semantic_deadman.py`, `contracts/mirror_audit.py`, `contracts/consensus_thermometer.py`, `contracts/ambiguity_guard.py`, `contracts/polyglot_consensus.py`, `contracts/semantic_commit_reveal.py`, `contracts/intent_lock.py`, `contracts/semantic_diff_ledger.py`, `contracts/constitutional_contract.py`, `contracts/corroboration_oracle.py`, `contracts/provenance_attestor.py`, `contracts/canary_tripwire.py`, `contracts/escalating_verdict.py`.

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

**An empty-string `str` calldata argument passed via `genlayer write ... --args`can decode as a non-`str` type (observed: `int`), not `""`.** Confirmed live (2026-07-03): `IntentLock.request(action: str, nonce: str)`, called via `genlayer write <addr> request --args "some action" ""`, crashed on every validator with `AttributeError: 'int' object has no attribute 'strip'` at `n = nonce.strip()` -- the CLI's calldata encoder appears to special-case an empty-string argument the same way GenVM special-cases a hex-address-shaped one (see "Addresses" above), silently ignoring the declared `str` type hint. Confirmed as specific to the empty case, not a general problem with the parameter, by re-sending the identical call with a non-empty nonce (`"abc123"`), which hit `nonce.strip()` with no error (4/6 validators `SUCCESS`, MAJORITY_AGREE; the other 2 were benign `VALIDATOR_QUORUM_REACHED` idles, not related). **Any `str` parameter that a legitimate caller might pass as `""` (an optional field, an "empty means unset" convention, or a deliberate empty-input test case) needs the same defensive coercion as the `Address` pattern above:**
```python
act = (action if isinstance(action, str) else "").strip()
```
Fixed in `IntentLock.request` for both `action` and `nonce` (the latter is optional-by-design: an empty nonce means "no one-shot binding requested"). **Also note for CLI smoke-testing generally**: `genlayer write`'s `status_name: 'ACCEPTED'` / `"✔ Write operation successfully executed"` only means consensus was REACHED -- it does NOT mean the call succeeded. Validators can unanimously `AGREE` on a deterministic revert or uncaught exception and still show `ACCEPTED`/`MAJORITY_AGREE`. Always check the `execution_result` field inside `consensus_data.leader_receipt` (`'SUCCESS'` vs `'ERROR'`) or read back state afterward before trusting a CLI write actually did what the contract intended -- this was how this bug was caught (a subsequent `get(0)` read reverted with "no such grant" despite the write showing ACCEPTED).

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
- **`gl.nondet.web.render()`/`.get()` raise an uncaught `NondetException` on fetch failure** instead of returning an error value — confirmed live via a deliberately dead URL (`{'causes': ['TLD_FORBIDDEN'], ...}` for a reserved `.invalid` TLD, and the same uncaught-exception path for a resolvable-but-nonexistent `.com` domain). If the nondet closure doesn't wrap the call in `try/except`, the whole transaction aborts instead of treating "source unreachable" as a judgeable outcome. Fixed in `SemanticDeadman.poke()` by catching the exception inside the closure and returning a canonical `{"alive": false, ...}` directly, never reaching the LLM. **Any future contract that calls `gl.nondet.web.*` must do the same** — RealitySettledMarket still needs this guard (CorroborationOracle, ProvenanceAttestor, and CanaryTripwire now confirm it works at three more call sites, see below).
- **Cross-contract READS via `gl.get_contract_at(addr).view().method()` are now confirmed** — the untyped proxy returns the value directly (plain `str`/`int`, no wrapper), exactly as the "Contract-to-contract" convention above describes. Confirmed twice: a throwaway isolation probe (a stub target with `get_label()`/`get_count()`) and live in `MirrorAudit.audit()` against a real deployed `SemanticDeadman` instance, correctly reading its `status()` JSON and reaching accurate conformance verdicts for both a true and a deliberately false spec. **This is the first confirmation of what was previously the single least-verified surface in the repo.**
- **But calling a method the target doesn't implement is an UNCATCHABLE runner-level fault, not a Python exception** — confirmed live auditing a target lacking `status()`: fails with `ValueError: call to private method <function Contract.__handle_undefined_method__...>`, raised while GenVM resolves the method against the target's own execution context. A `try/except` around the proxy call in the CALLING contract does **not** catch this (unlike the `NondetException` case above, which is catchable). The outcome is still safe — every validator agrees the call errors and the transaction reverts cleanly with no corrupted state, verified via `count()` unchanged after the failed call — but any contract calling a target whose method existence isn't guaranteed should expect a raw traceback, not a custom revert message, in that case. See `MirrorAudit`'s docstring for the fuller writeup.
- **`gltest` now runs successfully end-to-end against studionet — but ONLY if the contract's source is pure ASCII.** Real root cause, found by reading `gltest`'s own source and reproducing directly (2026-07-01): `_get_schema_with_fallback()` (`gltest/contracts/contract_factory.py`) fetches the schema via `client.get_contract_schema_for_code(contract_code=...)`, and that client-side call raises `UnicodeEncodeError: 'ascii' codec can't encode characters ...` the instant the contract's source contains ANY non-ASCII character — confirmed by testing an em-dash-free copy of a fixture (passed) against the original with one em dash (failed identically every time). `gltest`'s own internal logger that would have surfaced this is `disabled = True` by default (`gltest/logging.py`), which is why every prior attempt this session only saw the generic `ValueError: Failed to get schema from all clients` with no clue why. **Every contract in this repo used em dashes, a middle dot, box-drawing dividers, and one ellipsis throughout — meaning gltest had never worked against any real Penumbra contract before this was found.** Fixed (2026-07-01, Judith's explicit choice) by stripping all non-ASCII characters from every file under `contracts/` (·→., —→--, …→..., ─→-) — confirmed via `gltest --network studionet` actually passing on `test_mirror_audit.py` (5/5) and `test_semantic_deadman.py` (6/6, two initial DNS-blip failures cleared on retry). **This is now the primary regression risk for every future contract**: `README.md`/`CONTRACTS.md`/`CLAUDE.md`/`docs/*.md` may keep their typographic style freely (never sent through this schema-fetch call) — but any file under `contracts/` (including test fixtures) must stay pure ASCII. A root repo `conftest.py` now un-disables `gltest`'s logger so a future regression surfaces the real per-client error instead of the opaque `ValueError`.
- **`JailbreakBounty`'s payable `fund()` path is now confirmed end-to-end via `gltest`** (2026-07-02, closing half of what was previously listed under "Still open" below) — `gltest`'s `.transact(value=N)` can send real payable value where the `genlayer` CLI cannot (see the CLI limitation still listed below). `test_funding_accumulates` confirms `fund()` accepts and accumulates real value (1000 then 500 -> bounty 1500); `test_owner_can_reclaim_unbroken_pool` confirms the owner-reclaim-then-withdraw pull-payment flow works end-to-end with real funds (2000 funded -> reclaimed -> withdrawn successfully). All 5 tests in `test_jailbreak_bounty.py` passed live. **Still unconfirmed:** the full break-to-challenger-payout path — no test forces the LLM to judge a jailbreak attempt as successful (per the "never bet on exact LLM output" testing philosophy), so a challenger actually collecting a bounty via `claim()`/`withdraw()` after a genuine break has never been exercised.
- **`gl.eq_principle.prompt_non_comparative` used purely as a judgment call over two already-agreed chain-state strings (no new state written) is now confirmed live** — `PolyglotConsensus.same_meaning(id_a, id_b)` reads two stored `normalized` propositions and passes them into a `non_comparative` verification-input closure exactly like `ProofCarryingAnswer.attest()` does, except the inputs come from storage rather than fresh calldata. Confirmed via CLI (`same_meaning(0, 1)` on an English/French pair, ACCEPTED, MAJORITY_AGREE) and 9/9 `gltest` on `test_polyglot_consensus.py` (2026-07-02). This is the first confirmation that `non_comparative` composes cleanly as a second consensus move inside a contract whose other write method already uses `comparative` — a spec is not limited to one move per contract.
- **`SchellingResolver`'s real payable/resolve path is now confirmed end-to-end via `gltest`** (2026-07-03, re-run after 2026-07-02's TLS flakiness cleared) — all 7/7 tests in `test_schelling_resolver.py` passed cleanly in one run (265.06s), including the previously-unexercised LLM-clustering path: `test_focal_cluster_wins_and_pool_splits`, `test_double_resolve_reverts`, `test_claim_without_balance_reverts`, and `test_resolve_requires_minimum_submissions` all passed. No code changes were needed — the prior blocker was purely the session-level network flakiness noted below, not a contract defect.
- **`ProofCarryingAnswer` is now confirmed end-to-end via `gltest`** (2026-07-03, same re-run) — all 4/4 tests in `test_proof_carrying_answer.py` passed cleanly in one run (137.28s). No code changes were needed.
- **`SemanticCommitReveal` confirms two new patterns live** (2026-07-03): (1) a deterministic `sha256(...)` equality check run BEFORE a `prompt_comparative` nondet block, as the unforgeable bind half of a two-stage write — confirmed via CLI (`commit()` then `reveal()` with matching intent/salt, both ACCEPTED) and 10/10 `gltest`, including the wrong-salt-reverts case never reaching the LLM; (2) splitting what the CONTRACTS.md spec describes as one mutable `TreeMap[Address, Commit]` into two independent APPEND-ONLY `DynArray` archives (`commits`, `reveals`) each with their own `TreeMap[Address, u256]` index map, specifically to avoid ever writing `self.some_dyn_array[i] = x` — no contract in this repo has verified in-place `DynArray` element mutation, only append (`.append(...)`) and read-by-index. This dual-archive shape is now the reference pattern for any future primitive whose literal catalog spec implies "one record that gets updated in place."
- **`CorroborationOracle` confirms a new `gl.nondet.web.render` call site live** (2026-07-04) — SemanticDeadman's `try/except`-around-fetch guard was reused unchanged, and per this file's own rule that each new call site still needs separate confirmation, two fresh studionet deploys (`threshold_milli=700` and `threshold_milli=300`, same fixed two-URL Wikipedia pair) both reproduced `ratio_milli=500` identically -- live-verifying the revert path (`require(ratio_milli >= threshold_milli)` firing correctly, majority-agreed deterministic rollback, 3 agree/1 disagree/1 idle) and the success/archive path (`count()`==1, `get(0)` matching) from the same underlying fetch+judge block. 7/7 `gltest --network studionet` passed cleanly (317.98s) on a clean re-run (see the SynSent-hang entry below for why a re-run was needed; the re-run's clean pass through the test that had shown a bare "F" in the killed first run confirms that failure was a network artifact, not a contract defect).
- **New environment-flakiness class: a genuine TCP-level connection hang, distinct from the RemoteDisconnected/ConnectionAbortedError/timeout exceptions already known.** Observed during `CorroborationOracle`'s first `gltest` run (2026-07-04): after progressing partway through the suite, the `gltest` process's CPU time flatlined across two consecutive ~5-minute polls (no growth at all), unlike every previously-seen "slow but alive" wait in this repo's history, which always showed continuous slow CPU growth. Diagnosed via PowerShell `Get-NetTCPConnection -OwningProcess <pid>`, which showed a connection stuck in `SynSent` state to a remote IP on port 443 -- the TCP handshake itself never completed. Unlike the exception-based flakiness (which surfaces as a Python error and can just be retried), a `SynSent` hang leaves the process alive but stuck, so retrying the command alone does nothing -- the stalled process must be killed first (`Stop-Process -Force` on the PIDs holding the stuck connection) before re-running. **Diagnostic rule: if CPU time shows zero growth across two consecutive multi-minute polls, treat it as a hung TCP connection, not a slow LLM/network call -- check `Get-NetTCPConnection` and kill-and-retry rather than continuing to wait.**
- **`ProvenanceAttestor` confirms `gl.nondet.web.render` at a third guarded call site, and deliberately deviates from CONTRACTS.md's stated `non_comparative` to `comparative`** (2026-07-04) -- see DECISIONS.md for the full reasoning (family V needs independent cross-fetch verification; a single leader-controlled fetch defeats the trustless-web point). Live-verified: a real claim ("water boils at 100 C at sea level") against a real Wikipedia page returned `supports:true` with a genuine extracted quoting span, MAJORITY_AGREE; a deliberately unreachable `.invalid` URL resolved cleanly to `supports:false, span:""` (the guard working, not the transaction reverting), 4/5 agree. `gltest --network studionet` passed 6/6 (265.79s).
- **A `gltest` run launched from a plain Bash shell with no conda env active resolves the WRONG Python and fails immediately with a real (non-flaky) `ImportError`, easily mistaken for the SynSent-hang/timeout flakiness classes above.** Found live (2026-07-04) building `ProvenanceAttestor`: `which python`/`gltest` in a bare Bash shell resolve to the miniconda3 **base** env (Python 3.11.4), not the dedicated `genlayer` conda env (Python 3.12.13) that every prior successful `gltest` run in this repo actually used. The base env crashes instantly with `ImportError: cannot import name 'Buffer' from 'collections.abc'` inside `genlayer_py/types/calldata.py`, because `collections.abc.Buffer` is a Python 3.12+ stdlib addition `genlayer_py` depends on. **Always run `source /c/Users/user/miniconda3/etc/profile.d/conda.sh && conda activate genlayer` (confirm with `python --version` -> 3.12.13) before any `gltest` invocation** -- otherwise the failure looks environmental/flaky but is actually a wrong-interpreter error that will recur identically on every retry until the correct env is activated.
- **Cross-contract WRITE calls (`gl.get_contract_at(addr).emit()...`) are now confirmed live, closing what was previously the single most unexercised surface in the repo** (2026-07-04, `CanaryTripwire.poll()` firing a callback to a deployed `TripwireCallbackStub` fixture via `gl.get_contract_at(callback).emit().on_trip(condition)`). Confirmed via CLI: the initiating `poll()` transaction's receipt included a top-level `messages` array queuing a message to the target address with method `on_trip` and the condition payload; a follow-up read of the target's `status()` confirmed `trip_count:1` and `last_condition` matching exactly. **But delivery is ASYNCHRONOUS relative to the initiating transaction** -- the first `gltest` run against this exact path failed 2/7 with `trip_count == 0` immediately after `tx_execution_succeeded` was true on the `poll()` call, because gltest's rapid-succession read raced ahead of message delivery (the live CLI test happened to have several minutes of natural gap between calling `poll()` and reading the target's state in separate commands, which is why it looked synchronous there). Fixed by adding a retry-poll helper (`_wait_for_trip_count`, up to 60s) before asserting on the callback target's state; the fix made both previously-failing tests pass, and a clean full run then passed 7/7 (458.72s). **Any contract or test relying on a cross-contract WRITE callback must poll/retry the target's state, never assume it is already visible the instant the initiating write's receipt shows SUCCESS/ACCEPTED.**

**Still open — do not claim these are verified:**
- **`genlayer write` (CLI v0.39.2) cannot send payable value at all** — `write.ts` hardcodes `value: 0n`; `--fee-value` is an unrelated gas/fee-deposit concept. There is currently no CLI-only way to smoke-test any `.payable` method via the raw CLI (use `gltest`'s `.transact(value=N)` instead, or Studio's browser UI which has a dedicated value field). (`SemanticDeadman` sidesteps this entirely — its `poke()`/`check_in()` core paths are non-payable and have been fully verified live, including the actual release path against both a live and a deliberately dead source; only its optional `fund()` needs Studio or `gltest`.)
- **Calling `gl.get_contract_at` on an address with no deployed contract code at all appears to hang rather than revert.** Observed once, informally, while probing an isolation contract with a synthetic invalid address (not a real deployed contract): the write transaction never reached a terminal status and the CLI timed out waiting for `ACCEPTED`. This is distinct from — and possibly worse than — the clean "target lacks this method" revert above. Not reproduced deliberately or confirmed as a general rule; treat "audit an arbitrary, unverified address" as a real risk (possible hang, not just a revert) until this is tested properly, and do not write an automated test around it (a hang would stall the test run). `CanaryTripwire.arm()` documents this same risk in its own docstring since it cannot safely validate the callback address at arm-time without triggering it.

---

## Toolchain

- **Studio** (`studio.genlayer.com`) — paste a contract, deploy, exercise methods. Fastest feedback; use it to smoke-test before tests.
- **CLI** — `genlayer init` (choose an LLM provider when prompted), `genlayer up` to run localnet, `genlayer deploy --contract contracts/<file>.py --args ...`.
- **Tests** — `genlayer-test` (the `gltest` runner). `pip install -r requirements-dev.txt`.
- **`gltest` requires the `genlayer` conda env, not a bare shell.** `source /c/Users/user/miniconda3/etc/profile.d/conda.sh && conda activate genlayer` before running `gltest` — a bare Bash shell resolves the miniconda3 base env's Python 3.11.4, which crashes instantly with `ImportError: cannot import name 'Buffer' from 'collections.abc'` (a Python 3.12+ stdlib symbol `genlayer_py` depends on). Confirm with `python --version` -> `3.12.13` before trusting a `gltest` result. See "Known blockers" for how this was found and can be mistaken for network flakiness.

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

## Build queue (remaining 3, fully specified in CONTRACTS.md)

The shared-guard web-fetch trio (V) is complete: `CorroborationOracle`, `ProvenanceAttestor`, and `CanaryTripwire` are all built and confirm the `try/except`-around-`gl.nondet.web.render` guard works live across four call sites total. `CanaryTripwire` additionally delivered the first confirmed cross-contract WRITE in the repo (see "Known blockers" above) -- any future contract needing `.emit()` can now build on that pattern (best-effort try/except, callback delivery is asynchronous, target address must be a real deployed contract). `EscalatingVerdict` (VII) is also done -- a tiered consensus dispatcher (`strict_eq`/`comparative`/`non_comparative` selected deterministically by escrowed stake), deviating from CONTRACTS.md's literal "multi-source" wording for the large-stake tier into a multi-lens deterministic input instead (see DECISIONS.md).

Next up:
- **AdversarialReview** (IV) and **EquivalenceRegistry** (VI) — the two genuinely novel mechanisms: AdversarialReview's dual-advocate staging, EquivalenceRegistry's likely cross-contract WRITE need (now de-risked by CanaryTripwire's confirmation above).

Then: **RealitySettledMarket** (VIII), saved for last since it composes both AmbiguityGuard's ambiguity-guard pattern and the web-fetch trio's fetch-guard pattern (see DECISIONS.md's ordering rationale).

Note: RealitySettledMarket calls `gl.nondet.web.*` — wrap every such call in `try/except` inside its nondet closure (see "Known blockers" above, the `NondetException`-on-fetch-failure finding from `SemanticDeadman`, now reconfirmed by `CorroborationOracle`, `ProvenanceAttestor`, and `CanaryTripwire`).

## References
- API (authoritative, machine-readable): https://sdk.genlayer.com/main/_static/ai/api.txt
- Docs: https://docs.genlayer.com/developers/intelligent-contracts
- Equivalence principle: https://docs.genlayer.com/understand-genlayer-protocol/core-concepts/optimistic-democracy/equivalence-principle
- gltest: https://pypi.org/project/genlayer-test/
