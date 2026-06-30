# CLAUDE.md — Penumbra

Operating context for Claude Code in this repository. Read this fully before writing or editing any contract. The single most expensive failure mode here is reaching for **stale GenLayer syntax** from training data. The conventions below are the *current, deployable* ones, verified against the live SDK. Follow them exactly.

---

## What this repo is

Penumbra is a library of **GenLayer Intelligent Contract primitives** — reusable, single-file Python contracts that use the consensus layer as a building block. Not apps, not demos, not thin LLM wrappers. The thesis: *disagreement is a measurement instrument, not a bug.*

Each contract is a standalone `.py` file in `contracts/`, deployable as-is to GenLayer Studio. There is **no package, no shared import at deploy time** — `lib/penumbra_consensus.py` is a copy-paste reference, and each contract inlines the few helpers it needs.

Read `README.md` (thesis + catalog) and `CONTRACTS.md` (full spec of all 20) before building. Study the three built flagships as the canonical style: `contracts/dissensus_oracle.py`, `contracts/jailbreak_bounty.py`, `contracts/proof_carrying_answer.py`.

---

## The GenLayer API — CURRENT, DEPLOYABLE CONVENTION

Target the `py-genlayer:test` runner with star imports. **Do not migrate to the v0.3 `import genlayer as gl` / `gl.contract.Contract` layout** — it is not what Studio's deployable runner uses here and will break deploys. If you think the SDK changed, check `https://sdk.genlayer.com/main/_static/ai/api.txt` before editing; do not guess.

### Skeleton
```python
# { "Depends": "py-genlayer:test" }
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
`Address("0x...")` to construct; `.as_hex`, `.as_bytes`, `.as_int`; `Address.ZERO`. Accept user-supplied addresses as `str` and wrap with `Address(...)`.

---

## NON-DETERMINISM — the rules that break contracts if ignored

LLM calls and web reads are non-deterministic. They MUST be quarantined inside an **argument-free inner function** and reconciled by an Equivalence Principle.

**Hard rules:**
1. A nondet block is `def inner():` with **no arguments**.
2. It may **NOT** access `self` or storage. Read what you need into locals first and close over them.
3. **Canonicalize** any value compared by `strict_eq`: `json.dumps(obj, sort_keys=True, separators=(",",":"))`. Two validators producing the "same" dict must serialize identically.
4. Floats are fine *inside* a nondet block, but store probabilities/scores as **integers** (e.g. milli-units, `value * 1000`). Deterministic float math is software-emulated and slow; integers never drift.
5. `gl.nondet.exec_prompt(prompt, response_format="json")` returns a **parsed dict**, not a string.

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
1. `contracts/<snake_name>.py` — header `# { "Depends": "py-genlayer:test" }`, a module docstring covering **purpose · why-this-consensus-move · state design · reuse**, inlined helpers, one `gl.Contract` subclass (PascalCase, matches the catalog name).
2. `tests/test_<snake_name>.py` — invariant-based gltest tests.
3. `CONTRACTS.md` — flip the entry from ◻️ to ✅ and link the source.
4. `README.md` — flip the catalog status to ✅.
5. `python3 -m py_compile contracts/<file>.py` passes (syntax gate; full execution needs GenVM).

Style: keep the deterministic/non-deterministic boundary visually obvious. Comment *why* a consensus move was chosen, not just what the code does. Match the prose density of the existing flagships.

---

## Build queue (remaining 17, fully specified in CONTRACTS.md)

Next batch (priority — these show contract-to-contract + self-referential consensus):
- **SchellingResolver** (IV) — semantic clustering, focal-point payout
- **MirrorAudit** (VI) — reads another contract's state, judges conformance
- **ConsensusThermometer** (VI) — predicts validator agreement before committing
- **SemanticDeadman** (VII) — liveness judged from a web source

Then: AmbiguityGuard, PolyglotConsensus, SemanticCommitReveal, IntentLock, SemanticDiffLedger, ConstitutionalContract, AdversarialReview, CorroborationOracle, ProvenanceAttestor, CanaryTripwire, EquivalenceRegistry, EscalatingVerdict, RealitySettledMarket.

## References
- API (authoritative, machine-readable): https://sdk.genlayer.com/main/_static/ai/api.txt
- Docs: https://docs.genlayer.com/developers/intelligent-contracts
- Equivalence principle: https://docs.genlayer.com/understand-genlayer-protocol/core-concepts/optimistic-democracy/equivalence-principle
- gltest: https://pypi.org/project/genlayer-test/
