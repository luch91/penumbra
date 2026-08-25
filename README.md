# PENUMBRA

**A grimoire of GenLayer Intelligent Contract primitives that live in the half-light between determinism and judgment.**

A penumbra is the region of partial shadow at the edge of an eclipse -- neither fully lit nor fully dark. It is also where these contracts operate. Ordinary smart contracts demand certainty: every node must compute the same bytes, so the only questions they can answer are questions with one mechanical answer. GenLayer dissolves that constraint. Validators running *different* language models reach agreement through an Equivalence Principle, which means a contract can finally reason about things that were always off-limits to code: ambiguity, meaning, disagreement, contested truth, broken rules, the soundness of an argument.

Penumbra treats the consensus layer itself as a programmable material. Most of these contracts are not "an AI that decides X." They are primitives that use a *specific property of consensus* -- agreement, disagreement, the leader/validator asymmetry, semantic equivalence, cross-source corroboration -- as a load-bearing building block. Each one is meant to be lifted out and reused.

---

## The one idea worth stealing

> Disagreement is not a bug in AI consensus. It is a measurement instrument.

Every contract here is built from one of four consensus moves. Learn these four and the whole catalog reads like a sentence:

1. **Exact agreement** (`strict_eq`) -- validators must produce byte-identical output. Cheap, brutal, certain. Use after you canonicalize.
2. **Equivalent meaning** (`prompt_comparative`) -- validators each redo the work; an LLM judges whether their answers *mean* the same thing under a stated principle. This is the move that secretly *measures* agreement.
3. **Verified integrity** (`prompt_non_comparative`) -- the leader does the work; validators only check it holds. The asymmetric move: cheap to verify, expensive to produce.
4. **Custom adjudication** (`gl.vm.run_nondet`) -- you define, in code, what "the validators agree" even means.

Penumbra's thesis is that moves 2 and 3 are wildly under-used, and that *deliberately engineering for disagreement* unlocks a class of contracts nobody has shipped.

---

## What makes these primitives, not demos

The mission bar is explicit: no hello-worlds, no thin LLM wrappers, no "AI decides X." Every contract here clears it on purpose:

- **Real consensus logic.** Each contract names *which* equivalence principle it uses and *why that one*. The choice is the design.
- **Deliberate state design.** Append-only archives, pull-payment ledgers, content-addressed books, dedupe guards. The non-determinism is quarantined; the state is exact.
- **A reusable shape.** Each is a primitive other builders wrap: an uncertainty gate, an escrow, a verifier, a monitor. Not a finished app.
- **The hard boundary is respected.** Non-deterministic blocks never touch `self` or storage; money and control flow stay deterministic; outputs are canonicalized before exact comparison.

---

## Submission guide: the full project

Penumbra is a complete catalog of 20 standalone GenLayer Intelligent Contract primitives in eight families. The project explores how agreement, disagreement, semantic equivalence, web evidence, and validator roles can become reusable contract logic. The two examples below are entry points into the full project. They show two different patterns, but they do not represent the complete scope of Penumbra.

### Flagship 1: [DissensusOracle](https://github.com/luch91/penumbra/blob/main/contracts/dissensus_oracle.py)

`DissensusOracle.resolve(question)` asks for a self-ensemble of independent expert opinions, records the majority verdict, and stores disagreement as an integer `dissensus_milli` score. The score is persisted in an append-only record and exposed through `is_contested()`, so another contract or application can refuse to act when a question is too contested.

Each validator independently runs the ensemble, and `prompt_comparative` requires agreement on both the verdict's meaning and the agreement level within a configured tolerance. A question therefore fails safely when validators cannot agree even on how difficult or contested it is. This is a reusable uncertainty gate for fraud review, delivery disputes, moderation, and other high-stakes judgments.

- [Contract source](https://github.com/luch91/penumbra/blob/main/contracts/dissensus_oracle.py)
- [Integration tests](https://github.com/luch91/penumbra/blob/main/tests/test_dissensus_oracle.py)
- [Full specification](https://github.com/luch91/penumbra/blob/main/CONTRACTS.md)

### Flagship 2: [RealitySettledMarket](https://github.com/luch91/penumbra/blob/main/contracts/reality_settled_market.py)

`RealitySettledMarket` is a binary market whose settlement decision comes from multiple web sources. Bettors deposit YES or NO stakes into deterministic pools. On `settle()`, validators independently fetch and assess the configured sources; the market settles only when the evidence is sufficiently corroborated and unambiguous. Otherwise it records `REFUND` and credits every bettor their original stake. A later `redeem()` call emits the native GEN transfer.

The non-deterministic judgment is isolated from exact accounting, settlement is one-way, bets close after settlement, and the tests assert that refunds and payouts never over-credit the pool. It is a reusable pattern for evidence-backed markets, oracle-gated escrows, and contracts where refusing to guess is safer than producing a weak verdict.

- [Contract source](https://github.com/luch91/penumbra/blob/main/contracts/reality_settled_market.py)
- [Integration tests](https://github.com/luch91/penumbra/blob/main/tests/test_reality_settled_market.py)
- [Full specification](https://github.com/luch91/penumbra/blob/main/CONTRACTS.md)

### Full project coverage

The catalog below covers all 20 contracts. Each contract has its own source file, public API, state model, and integration test. The project includes uncertainty oracles, proof verification, semantic state machines, adversarial mechanisms, web corroboration, meta-consensus, liveness primitives, and markets with ambiguity-safe settlement.

### Reviewer links

- [Repository](https://github.com/luch91/penumbra)
- [All contract specifications](https://github.com/luch91/penumbra/blob/main/CONTRACTS.md)
- [Engineering decisions and live-run findings](https://github.com/luch91/penumbra/blob/main/DECISIONS.md)
- [All integration tests](https://github.com/luch91/penumbra/tree/main/tests)
- [All standalone contract source files](https://github.com/luch91/penumbra/tree/main/contracts)
- [Consensus helper reference](https://github.com/luch91/penumbra/blob/main/lib/penumbra_consensus.py)
- [Finalized SemanticDeadman deployment](https://explorer-studio.genlayer.com/tx/0x8669e0db1a0295e216733027446ec949082636553ba958ee68a8f09a8cf4f1a2)

### PenumbraGate deployment

PenumbraGate is the catalog contribution review primitive. Its finalized
Studionet deployment uses the pinned runner, the full NN-1 through NN-8 rubric,
comparative consensus for both rubric parts, one free submission per address,
mandatory stake thereafter, and pull-payment refunds.

- [PenumbraGate source](https://github.com/luch91/penumbra/blob/main/contracts/penumbra_gate.py)
- [PenumbraGate contract](https://explorer-studio.genlayer.com/address/0xF45009635A785fE8469935A07F653AF6E9c26c2A)
- [PenumbraGate deployment transaction](https://explorer-studio.genlayer.com/tx/0x50bcc7d3f121005bdf5c6098727cd1fe2f2e33753474d98ab1fc4eb286d5659e)
- Deployment wallet: `0x7048781a2Fc941617995f8c4542A1908500C0703`
- [Free submission smoke test](https://explorer-studio.genlayer.com/tx/0x90225875942d4794aaf50cd6574b7e6f60bb863166797a315e9d8aa3bff9c9cd)
- [Staked submission smoke test](https://explorer-studio.genlayer.com/tx/0xca15a0d9932b053d6508bbee77cb62907ada8d0fbd0d0f739d714ca684b8ed74)
- [Full refund withdrawal](https://explorer-studio.genlayer.com/tx/0x3fe4b876e205c5e90382fd0bd9f30e6c907a66d65c5846779dba5c0d596ae005)
- [PenumbraGate tests](https://github.com/luch91/penumbra/blob/main/tests/test_penumbra_gate.py)
- [PenumbraGate agent](https://github.com/luch91/penumbra/blob/main/agent/review_agent.py)
## The catalog -- 20 primitives in 8 families

Status legend: ✅ source and integration tests present; all 20 catalogue contracts have deployment records and focused live SDK evidence in `CONTRACTS.md`. The full 143-test Studionet suite is not claimed as passed because hosted RPC runs timed out.

### I · Oracles of Doubt -- *disagreement as signal*
1. ✅ **DissensusOracle** -- answers a contested question *and* publishes a `dissensus` score by self-ensembling K expert opinions; the comparative principle forces validators to agree on both the verdict and how hard the question was. Downstream contracts gate on it. → `contracts/dissensus_oracle.py`
2. ✅ **AmbiguityGuard** -- a wrapper that performs any judgment but writes `ABSTAIN` instead of a verdict when the question is too ambiguous for validators to reliably converge. Consensus-aware refusal. → `contracts/ambiguity_guard.py`

### II · Asymmetric Rites -- *generate hard, verify cheap*
3. ✅ **ProofCarryingAnswer** -- submit a claim plus the reasoning that backs it; the network attests it only if the proof holds, using the non-comparative principle so validators audit rather than re-derive. → `contracts/proof_carrying_answer.py`
4. ✅ **PolyglotConsensus** -- accepts a claim in any language; the principle is translation-invariant, so heterogeneous-language validators must agree on *meaning*. Turns the diverse validator set into a feature. → `contracts/polyglot_consensus.py`

### III · Semantic Machines -- *state transitions gated by meaning*
5. ✅ **SemanticCommitReveal** -- commit-reveal where a reveal counts if it *means* the commitment, not if it hashes to it. Fuzzy-intent anti-front-running. → `contracts/semantic_commit_reveal.py`
6. ✅ **IntentLock** -- access control by plain-language policy: an action unlocks iff consensus judges it satisfies the policy. A semantic ACL. → `contracts/intent_lock.py`
7. ✅ **SemanticDiffLedger** -- versioned document where consensus decides which edits are *material* vs cosmetic; only material edits bump the version. Meaning-gated version control. → `contracts/semantic_diff_ledger.py`
8. ✅ **ConstitutionalContract** -- holds a prose constitution with immutable core principles; amendments pass only if consensus judges them consistent with the core. Governance as machine-adjudicated consistency. → `contracts/constitutional_contract.py`

### IV · Adversaria -- *consensus as referee in a game*
9. ✅ **JailbreakBounty** -- escrow that pays a challenger iff independent validators agree their prompt broke a stated rule. The inverse of Wizard-of-Coin: breaking the guard is the win, and the network is the impartial judge. → `contracts/jailbreak_bounty.py`
10. ✅ **SchellingResolver** -- players answer a subjective question; consensus clusters the answers and rewards those who matched the focal meaning. Keynesian beauty contest via semantic clustering. → `contracts/schelling_resolver.py`
11. ✅ **AdversarialReview** -- stages two opposing LLM advocates inside the leader block; validators judge which case is stronger. Debate-as-consensus. → `contracts/adversarial_review.py`

### V · Corroboration -- *trustless web, verified across sources*
12. ✅ **CorroborationOracle** -- fetches N independent sources and accepts a fact only if cross-source agreement clears a threshold; exposes the corroboration ratio. → `contracts/corroboration_oracle.py`
13. ✅ **ProvenanceAttestor** -- given a claim + source, emits an attestation with the extracted supporting span; validators independently re-confirm the span backs the claim. Citation-chain provenance. → `contracts/provenance_attestor.py`
14. ✅ **CanaryTripwire** -- monitors a web source for a plain-language tripwire and flips state (and can call back another contract) when consensus judges the condition met. An on-chain monitor; the first primitive here to confirm a live cross-contract WRITE callback. → `contracts/canary_tripwire.py`

### VI · Reflexion -- *contracts that reason about consensus*
15. ✅ **ConsensusThermometer** -- runs a cheap "would the validators even agree?" pre-check before committing an expensive decision, and routes to a fallback when predicted agreement is low. Self-aware meta-consensus. → `contracts/consensus_thermometer.py`
16. ✅ **MirrorAudit** -- given another contract's address and a behavioral spec, reads its public state via contract-to-contract calls and judges via consensus whether it conforms. Contracts auditing contracts. → `contracts/mirror_audit.py`
17. ✅ **EquivalenceRegistry** -- named, reusable equivalence principles as first-class on-chain objects other contracts fetch and apply. The one primitive here that runs *no* consensus block of its own -- it exists to be read. Composable consensus policy as infrastructure. → `contracts/equivalence_registry.py`

### VII · Chronomancy -- *time and liveness, judged*
18. ✅ **SemanticDeadman** -- a dead-man's switch that releases on *semantic* inactivity (no genuine public activity at a source), not just a missed timestamp ping. → `contracts/semantic_deadman.py`
19. ✅ **EscalatingVerdict** -- a dispute primitive whose consensus rigor scales with stakes: `strict_eq` for pennies, `comparative` mid, multi-lens `non_comparative` review for serious money. Tiered, economical consensus. → `contracts/escalating_verdict.py`

### VIII · Markets of Meaning -- *economic primitives with judgment baked in*
20. ✅ **RealitySettledMarket** -- a binary market that self-settles from primary sources with an ambiguity guard: when sources conflict or are too weak, it refuses to settle and refunds every stake rather than guess. The final primitive, composing the ambiguity gate and the guarded web fetch. → `contracts/reality_settled_market.py`

---

## Repository layout

```
penumbra/
├── README.md                  ← you are here (thesis + catalog)
├── CONTRACTS.md               ← one-pager spec per primitive (purpose · consensus · state · API · reuse)
├── gltest.config.yaml
├── requirements-dev.txt
├── lib/
│   └── penumbra_consensus.py  ← the four consensus moves as documented copy-paste helpers
├── contracts/                 ← one standalone GenVM file per primitive
│   ├── dissensus_oracle.py
│   ├── jailbreak_bounty.py
│   ├── proof_carrying_answer.py
│   ├── schelling_resolver.py
│   ├── semantic_deadman.py
│   ├── mirror_audit.py
│   ├── consensus_thermometer.py
│   ├── ambiguity_guard.py
│   ├── polyglot_consensus.py
│   ├── semantic_commit_reveal.py
│   ├── intent_lock.py
│   ├── semantic_diff_ledger.py
│   ├── constitutional_contract.py
│   ├── corroboration_oracle.py
│   ├── provenance_attestor.py
│   ├── canary_tripwire.py
│   ├── escalating_verdict.py
│   ├── adversarial_review.py
│   ├── equivalence_registry.py
│   ├── reality_settled_market.py
│   └── fixtures/              ← test-only stand-ins, not catalog primitives
│       ├── audit_stub_target.py
│       └── tripwire_callback_stub.py
└── tests/                     ← gltest integration tests; assert invariants, never LLM strings
    ├── test_dissensus_oracle.py
    ├── test_jailbreak_bounty.py
    ├── test_proof_carrying_answer.py
    ├── test_schelling_resolver.py
    ├── test_semantic_deadman.py
    ├── test_mirror_audit.py
    ├── test_mirror_audit_read.py
    ├── test_consensus_thermometer.py
    ├── test_ambiguity_guard.py
    ├── test_polyglot_consensus.py
    ├── test_semantic_commit_reveal.py
    ├── test_intent_lock.py
    ├── test_semantic_diff_ledger.py
    ├── test_constitutional_contract.py
    ├── test_corroboration_oracle.py
    ├── test_provenance_attestor.py
    ├── test_canary_tripwire.py
    ├── test_escalating_verdict.py
    ├── test_adversarial_review.py
    ├── test_equivalence_registry.py
    └── test_reality_settled_market.py
```

GenLayer contracts run as a single Python file inside the GenVM -- there is no `pip install` and no cross-file import at deploy time. `lib/penumbra_consensus.py` is therefore not an imported module but a curated block: each contract inlines the few helpers it needs.

## Build & deploy

Every contract targets the `py-genlayer` runner -- **pinned to a runner hash**, since floating tags like `py-genlayer:test` are rejected at deploy -- and the live SDK surface (`gl.eq_principle.*`, `gl.nondet.*`, `TreeMap`/`DynArray`, `@gl.public.write.payable`, `gl.message`).

- **Studio:** open [studio.genlayer.com](https://studio.genlayer.com), paste a contract, deploy, and exercise the read/write methods. Recommended first run.
- **CLI:** `genlayer deploy --contract contracts/dissensus_oracle.py --args 7 250`
- **Tests:** `pip install -r requirements-dev.txt` then `gltest --network studionet`. Tests pin contract guarantees (preconditions, dedupe, ledger math, score invariants), not non-deterministic model text.

## License

MIT. Take the patterns. Build in the penumbra.
