# PENUMBRA

**A grimoire of GenLayer Intelligent Contract primitives that live in the half-light between determinism and judgment.**

A penumbra is the region of partial shadow at the edge of an eclipse — neither fully lit nor fully dark. It is also where these contracts operate. Ordinary smart contracts demand certainty: every node must compute the same bytes, so the only questions they can answer are questions with one mechanical answer. GenLayer dissolves that constraint. Validators running *different* language models reach agreement through an Equivalence Principle, which means a contract can finally reason about things that were always off-limits to code: ambiguity, meaning, disagreement, contested truth, broken rules, the soundness of an argument.

Penumbra treats the consensus layer itself as a programmable material. Most of these contracts are not "an AI that decides X." They are primitives that use a *specific property of consensus* — agreement, disagreement, the leader/validator asymmetry, semantic equivalence, cross-source corroboration — as a load-bearing building block. Each one is meant to be lifted out and reused.

---

## The one idea worth stealing

> Disagreement is not a bug in AI consensus. It is a measurement instrument.

Every contract here is built from one of four consensus moves. Learn these four and the whole catalog reads like a sentence:

1. **Exact agreement** (`strict_eq`) — validators must produce byte-identical output. Cheap, brutal, certain. Use after you canonicalize.
2. **Equivalent meaning** (`prompt_comparative`) — validators each redo the work; an LLM judges whether their answers *mean* the same thing under a stated principle. This is the move that secretly *measures* agreement.
3. **Verified integrity** (`prompt_non_comparative`) — the leader does the work; validators only check it holds. The asymmetric move: cheap to verify, expensive to produce.
4. **Custom adjudication** (`gl.vm.run_nondet`) — you define, in code, what "the validators agree" even means.

Penumbra's thesis is that moves 2 and 3 are wildly under-used, and that *deliberately engineering for disagreement* unlocks a class of contracts nobody has shipped.

---

## What makes these primitives, not demos

The mission bar is explicit: no hello-worlds, no thin LLM wrappers, no "AI decides X." Every contract here clears it on purpose:

- **Real consensus logic.** Each contract names *which* equivalence principle it uses and *why that one*. The choice is the design.
- **Deliberate state design.** Append-only archives, pull-payment ledgers, content-addressed books, dedupe guards. The non-determinism is quarantined; the state is exact.
- **A reusable shape.** Each is a primitive other builders wrap: an uncertainty gate, an escrow, a verifier, a monitor. Not a finished app.
- **The hard boundary is respected.** Non-deterministic blocks never touch `self` or storage; money and control flow stay deterministic; outputs are canonicalized before exact comparison.

---

## The catalog — 20 primitives in 8 families

Status legend: ✅ built and live-smoke-tested on studionet (deploy + method calls, not just syntax) · ◻️ specified, scheduled in the build queue.

### I · Oracles of Doubt — *disagreement as signal*
1. ✅ **DissensusOracle** — answers a contested question *and* publishes a `dissensus` score by self-ensembling K expert opinions; the comparative principle forces validators to agree on both the verdict and how hard the question was. Downstream contracts gate on it. → `contracts/dissensus_oracle.py`
2. ✅ **AmbiguityGuard** — a wrapper that performs any judgment but writes `ABSTAIN` instead of a verdict when the question is too ambiguous for validators to reliably converge. Consensus-aware refusal. → `contracts/ambiguity_guard.py`

### II · Asymmetric Rites — *generate hard, verify cheap*
3. ✅ **ProofCarryingAnswer** — submit a claim plus the reasoning that backs it; the network attests it only if the proof holds, using the non-comparative principle so validators audit rather than re-derive. → `contracts/proof_carrying_answer.py`
4. ✅ **PolyglotConsensus** — accepts a claim in any language; the principle is translation-invariant, so heterogeneous-language validators must agree on *meaning*. Turns the diverse validator set into a feature. → `contracts/polyglot_consensus.py`

### III · Semantic Machines — *state transitions gated by meaning*
5. ✅ **SemanticCommitReveal** — commit-reveal where a reveal counts if it *means* the commitment, not if it hashes to it. Fuzzy-intent anti-front-running. → `contracts/semantic_commit_reveal.py`
6. ✅ **IntentLock** — access control by plain-language policy: an action unlocks iff consensus judges it satisfies the policy. A semantic ACL. → `contracts/intent_lock.py`
7. ✅ **SemanticDiffLedger** — versioned document where consensus decides which edits are *material* vs cosmetic; only material edits bump the version. Meaning-gated version control. → `contracts/semantic_diff_ledger.py`
8. ✅ **ConstitutionalContract** — holds a prose constitution with immutable core principles; amendments pass only if consensus judges them consistent with the core. Governance as machine-adjudicated consistency. → `contracts/constitutional_contract.py`

### IV · Adversaria — *consensus as referee in a game*
9. ✅ **JailbreakBounty** — escrow that pays a challenger iff independent validators agree their prompt broke a stated rule. The inverse of Wizard-of-Coin: breaking the guard is the win, and the network is the impartial judge. → `contracts/jailbreak_bounty.py`
10. ✅ **SchellingResolver** — players answer a subjective question; consensus clusters the answers and rewards those who matched the focal meaning. Keynesian beauty contest via semantic clustering. → `contracts/schelling_resolver.py`
11. ◻️ **AdversarialReview** — stages two opposing LLM advocates inside the leader block; validators judge which case is stronger. Debate-as-consensus.

### V · Corroboration — *trustless web, verified across sources*
12. ✅ **CorroborationOracle** — fetches N independent sources and accepts a fact only if cross-source agreement clears a threshold; exposes the corroboration ratio. → `contracts/corroboration_oracle.py`
13. ✅ **ProvenanceAttestor** — given a claim + source, emits an attestation with the extracted supporting span; validators independently re-confirm the span backs the claim. Citation-chain provenance. → `contracts/provenance_attestor.py`
14. ◻️ **CanaryTripwire** — monitors a web source for a plain-language tripwire and flips state (and can call back another contract) when consensus judges the condition met. An on-chain monitor.

### VI · Reflexion — *contracts that reason about consensus*
15. ✅ **ConsensusThermometer** — runs a cheap "would the validators even agree?" pre-check before committing an expensive decision, and routes to a fallback when predicted agreement is low. Self-aware meta-consensus. → `contracts/consensus_thermometer.py`
16. ✅ **MirrorAudit** — given another contract's address and a behavioral spec, reads its public state via contract-to-contract calls and judges via consensus whether it conforms. Contracts auditing contracts. → `contracts/mirror_audit.py`
17. ◻️ **EquivalenceRegistry** — named, reusable equivalence principles as first-class on-chain objects other contracts fetch and apply. Composable consensus policy as infrastructure.

### VII · Chronomancy — *time and liveness, judged*
18. ✅ **SemanticDeadman** — a dead-man's switch that releases on *semantic* inactivity (no genuine public activity at a source), not just a missed timestamp ping. → `contracts/semantic_deadman.py`
19. ◻️ **EscalatingVerdict** — a dispute primitive whose consensus rigor scales with stakes: `strict_eq` for pennies, multi-source non-comparative review for serious money. Tiered, economical consensus.

### VIII · Markets of Meaning — *economic primitives with judgment baked in*
20. ◻️ **RealitySettledMarket** — a binary market that self-settles from primary sources with an ambiguity guard: when sources conflict, it refuses to settle and refunds rather than guess. Prediction-market settlement done safely.

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
│   └── fixtures/              ← test-only stand-ins, not catalog primitives
│       └── audit_stub_target.py
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
    └── test_provenance_attestor.py
```

GenLayer contracts run as a single Python file inside the GenVM — there is no `pip install` and no cross-file import at deploy time. `lib/penumbra_consensus.py` is therefore not an imported module but a curated block: each contract inlines the few helpers it needs.

## Build & deploy

Every contract targets the `py-genlayer` runner — **pinned to a runner hash**, since floating tags like `py-genlayer:test` are rejected at deploy — and the live SDK surface (`gl.eq_principle.*`, `gl.nondet.*`, `TreeMap`/`DynArray`, `@gl.public.write.payable`, `gl.message`).

- **Studio:** open [studio.genlayer.com](https://studio.genlayer.com), paste a contract, deploy, and exercise the read/write methods. Recommended first run.
- **CLI:** `genlayer deploy --contract contracts/dissensus_oracle.py --args 7 250`
- **Tests:** `pip install -r requirements-dev.txt` then `gltest --network studionet`. Tests pin contract guarantees (preconditions, dedupe, ledger math, score invariants), not non-deterministic model text.

## License

MIT. Take the patterns. Build in the penumbra.
