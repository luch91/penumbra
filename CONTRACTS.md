# Penumbra · Contract Catalog

One page per primitive. Each entry states the **purpose**, the **consensus move** it is built on (and why that move), the **state design**, the **key methods**, and the **reuse** shape. Built contracts link to source; specified contracts are fully designed and queued.

Consensus moves referenced below:
`strict_eq` (byte-exact) · `comparative` (equivalent meaning, validators redo + compare) · `non_comparative` (leader does it, validators verify integrity) · `run_nondet` (custom adjudication).

---

## I · Oracles of Doubt

### 1. DissensusOracle ✅ `contracts/dissensus_oracle.py`
- **Purpose.** Answer a contested question and publish how contested it is, as a `dissensus` score in milli-units [0..1000].
- **Consensus.** `comparative`. The leader self-ensembles K independent expert opinions and reports `{verdict, agreement}`. The principle requires validators to agree on the verdict *and* on the agreement ratio within a tolerance — so the network must concur on the difficulty, not just the answer. Unstable difficulty fails consensus and the oracle declines to speak.
- **State.** Append-only `DynArray[Record]` archive (`question, verdict, dissensus_milli, sample_size`) + `latest` index. Integer milli-units keep probabilities exact on-chain.
- **API.** `resolve(question) -> verdict` · `latest_verdict()` · `get(id)` · `is_contested(id, threshold_milli) -> bool`.
- **Reuse.** Gate any high-stakes judgment: only execute when `dissensus < threshold`.

### 2. AmbiguityGuard ◻️
- **Purpose.** A drop-in wrapper that returns a verdict *or* `ABSTAIN`, never a confident answer to an unanswerable question.
- **Consensus.** `comparative` with a principle that treats "leader answered X, validator would answer ABSTAIN" as non-equivalent; persistent non-equivalence collapses to a stored `ABSTAIN`.
- **State.** `last_status` enum-as-string, `abstain_count`, archive of (question, status).
- **API.** `judge(question, options) -> status` · `did_abstain() -> bool`.
- **Reuse.** Compose in front of governance, liquidation, or moderation calls to force fail-safe behavior under ambiguity.

---

## II · Asymmetric Rites

### 3. ProofCarryingAnswer ✅ `contracts/proof_carrying_answer.py`
- **Purpose.** Attest a claim only if the submitted proof actually establishes it. The contract is the cheap verification half of a hard/easy asymmetry.
- **Consensus.** `non_comparative`. Claim + proof arrive as arguments, so every node shares identical input; the `task` verifies and the `criteria` define soundness (every step follows, conclusion matches, no gaps). Validators audit the leader's verdict; they never re-derive.
- **State.** Content-addressed `DynArray[Attestation]` + `seen` dedupe map keyed by SHA-256 of the claim. Rejected claims revert and leave no trace, so the book holds only attested truth.
- **API.** `attest(claim, proof) -> bool` · `is_attested(claim)` · `get(index)` · `count()`.
- **Reuse.** Eligibility/compliance proofs, lemmas, dataset-derived figures; pair with an off-chain solver.

### 4. PolyglotConsensus ◻️
- **Purpose.** Accept a claim in any language and reach agreement on its meaning across translations.
- **Consensus.** `comparative` with a translation-invariant principle ("equivalent if they assert the same proposition regardless of language"). The diverse, multi-model validator set becomes the robustness mechanism rather than a noise source.
- **State.** Canonical English normalization stored alongside the original; `TreeMap[str, str]` of claim-hash → normalized proposition.
- **API.** `submit(text) -> proposition_id` · `same_meaning(id_a, id_b) -> bool`.
- **Reuse.** Language-agnostic input layer for any multilingual dApp; dedupe submissions that differ only in language.

---

## III · Semantic Machines

### 5. SemanticCommitReveal ◻️
- **Purpose.** Commit-reveal where a reveal is valid if it *means* the commitment, defeating front-runners who can copy ciphertext but not intent.
- **Consensus.** `comparative` on (decrypted commit intent) vs (revealed statement) under a "same intent" principle; deterministic hash check still binds the commit phase.
- **State.** `TreeMap[Address, Commit]` (`hash, opened, intent`), reveal window timestamps.
- **API.** `commit(hash)` · `reveal(statement, salt) -> bool`.
- **Reuse.** Sealed-bid auctions and votes where exact wording shouldn't be game-able.

### 6. IntentLock ◻️
- **Purpose.** Access control whose key is a plain-language policy, not an address allow-list.
- **Consensus.** `non_comparative`: policy + requested action are deterministic input; validators verify the leader's grant/deny respects the policy.
- **State.** `policy: str`, `grants: DynArray[record]`, optional one-shot nonce per grant.
- **API.** `set_policy(text)` (owner) · `request(action) -> granted: bool`.
- **Reuse.** Permissioning for treasury actions, content publishing, agent tool-use.

### 7. SemanticDiffLedger ◻️
- **Purpose.** Track an evolving document and only bump the version on *material* change.
- **Consensus.** `comparative` comparing old vs new under a "materially different?" principle; cosmetic edits are judged equivalent and ignored.
- **State.** `current: str`, `DynArray[Snapshot]` of material versions, `version: u256`.
- **API.** `propose(new_text) -> bumped: bool` · `version()` · `snapshot(v)`.
- **Reuse.** On-chain changelogs, license/terms tracking, spec governance.

### 8. ConstitutionalContract ◻️
- **Purpose.** A rulebook in prose whose amendments must stay consistent with immutable core principles.
- **Consensus.** `non_comparative`: core principles + proposed amendment are deterministic input; validators verify the leader's consistency ruling.
- **State.** `core: DynArray[str]` (immutable after init), `body: str`, `amendments: DynArray[record]`.
- **API.** `propose_amendment(text) -> accepted: bool` · `read_constitution()`.
- **Reuse.** DAO charters, protocol policy, agent operating agreements.

---

## IV · Adversaria

### 9. JailbreakBounty ✅ `contracts/jailbreak_bounty.py`
- **Purpose.** Pay a challenger iff the network agrees their prompt broke a sworn rule. Trustless red-team market.
- **Consensus.** `comparative` keyed only on the `violated` boolean. Each validator runs its own guarded model *and* its own judge; payout requires independent agreement that a violation occurred — rewarding robust, transferable breaks, not one-off lucky samples.
- **State & money.** Payable `fund()` accumulates `bounty`; a win closes `open` and credits the challenger's `claimable` (pull-payment). `withdraw()` debits the ledger and marks the native/ERC-20 transfer hook. `reclaim_unclaimed()` lets the owner retire an unbroken pool.
- **API.** `fund()` payable · `attempt(prompt) -> bool` · `withdraw()` · `status()` · `winning_attack()`.
- **Reuse.** Bug-bounty markets for any plain-language guardrail: filters, refusals, compliance rules.

### 10. SchellingResolver ◻️
- **Purpose.** Resolve a subjective question by paying whoever matched the crowd's focal meaning.
- **Consensus.** `comparative` to cluster submissions into semantic groups; the largest cluster is the Schelling point; deterministic payout math follows.
- **State.** `DynArray[Submission]`, cluster assignment, reward pool.
- **API.** `submit(answer)` payable-stake · `resolve()` · `claim()`.
- **Reuse.** Decentralized labeling, subjective dispute resolution, focal-point coordination.

### 11. AdversarialReview ◻️
- **Purpose.** Decide a contested claim by staging a debate rather than a single judgment.
- **Consensus.** `non_comparative`: the leader generates a pro case and a con case and a ruling; validators verify the ruling fairly follows from the stronger case.
- **State.** `DynArray[Case]` (claim, winner, margin).
- **API.** `adjudicate(claim) -> winner` · `get(id)`.
- **Reuse.** Grant review, content appeals, any "steelman both sides" decision.

---

## V · Corroboration

### 12. CorroborationOracle ◻️
- **Purpose.** Accept a fact only when independent sources corroborate it; publish the corroboration ratio.
- **Consensus.** `comparative`: each validator fetches the same N source URLs and extracts the fact; the principle requires agreement on the corroborated value. Sources that disagree drag the ratio below threshold and the write reverts.
- **State.** `DynArray[Fact]` (value, ratio_milli, sources_count).
- **API.** `establish(question, urls[]) -> value` · `get(id)`.
- **Reuse.** Price/score/event oracles that must not trust a single endpoint.

### 13. ProvenanceAttestor ◻️
- **Purpose.** Attest that a specific source supports a specific claim, with the supporting span recorded.
- **Consensus.** `non_comparative`: validators independently re-read the source and verify the extracted span genuinely backs the claim.
- **State.** `DynArray[Attestation]` (claim, url, span_hash, supports: bool).
- **API.** `attest(claim, url) -> supports: bool` · `get(id)`.
- **Reuse.** Citation chains, fact provenance, anti-misinformation rails.

### 14. CanaryTripwire ◻️
- **Purpose.** Watch a web source for a plain-language condition and flip on consensus that it has occurred.
- **Consensus.** `comparative` on the boolean tripwire state across validators that each fetch the source.
- **State.** `armed: bool`, `tripped: bool`, `callback: Address`, `condition: str`.
- **API.** `arm(condition, callback)` · `poll() -> tripped: bool` (fires a contract-to-contract callback on first trip).
- **Reuse.** On-chain alerts: depeg watch, governance-deadline watch, outage detection.

---

## VI · Reflexion

### 15. ConsensusThermometer ◻️
- **Purpose.** Predict whether validators would agree *before* paying for an expensive decision; route to fallback when they wouldn't.
- **Consensus.** A cheap `comparative` probe on a downsampled version of the task; high predicted agreement unlocks the full decision, low agreement stores a `DEFERRED` status for human/appeal handling.
- **State.** `DynArray[Probe]` (task_hash, predicted_agreement_milli, routed_to).
- **API.** `assess(task) -> route` · `last_probe()`.
- **Reuse.** Cost control + graceful degradation for any consensus-heavy pipeline.

### 16. MirrorAudit ◻️
- **Purpose.** One contract audits another against a behavioral description.
- **Consensus.** `non_comparative`: target's public state (read via contract-to-contract calls) + spec are the input; validators verify the leader's conformance ruling.
- **State.** `DynArray[Audit]` (target: Address, conforms: bool, note_hash).
- **API.** `audit(target, spec) -> conforms: bool` · `history(target)`.
- **Reuse.** On-chain conformance checks, registry gating, agent-to-agent trust.

### 17. EquivalenceRegistry ◻️
- **Purpose.** Make equivalence principles reusable, named, on-chain objects.
- **Consensus.** Deterministic registry CRUD (`strict_eq`-trivial); other contracts fetch a principle string via contract-to-contract `view()` and feed it into their own `comparative` calls.
- **State.** `TreeMap[str, Principle]` (name → text, author, version).
- **API.** `register(name, text)` · `get(name) -> text` · `bump(name, text)`.
- **Reuse.** Shared, audited "definitions of agreement" across an ecosystem.

---

## VII · Chronomancy

### 18. SemanticDeadman ◻️
- **Purpose.** A dead-man's switch keyed to *genuine* activity, not a mechanical heartbeat.
- **Consensus.** `comparative`: validators fetch the liveness source (e.g. a public profile/feed) and agree on whether meaningful recent activity exists.
- **State.** `owner`, `beneficiary`, `last_alive_ts`, `liveness_url`, `released: bool`.
- **API.** `check_in()` (owner) · `poke() -> released: bool` · `claim()` (beneficiary).
- **Reuse.** Inheritance, key-rotation fallback, abandoned-treasury recovery.

### 19. EscalatingVerdict ◻️
- **Purpose.** Match consensus rigor to stakes so cheap disputes stay cheap and expensive ones get scrutiny.
- **Consensus.** Tiered: `strict_eq` for small stakes, `comparative` mid, multi-source `non_comparative` for large. Tier selected deterministically from the escrowed amount.
- **State.** `DynArray[Dispute]` (stake, tier, verdict).
- **API.** `open_dispute(question)` payable · `resolve(id) -> verdict`.
- **Reuse.** Marketplaces, insurance, arbitration with proportionate cost.

---

## VIII · Markets of Meaning

### 20. RealitySettledMarket ◻️
- **Purpose.** A binary market that settles itself from primary sources, and refuses to settle when reality is unclear.
- **Consensus.** `comparative` on the YES/NO outcome across validators that each fetch the resolution sources; an ambiguity guard converts source conflict into `REFUND` instead of a coin-flip.
- **State.** `question`, `yes_pool`, `no_pool`, `resolution_urls`, `outcome` enum.
- **API.** `bet(side)` payable · `settle() -> outcome` · `redeem()`.
- **Reuse.** Self-resolving prediction markets, parametric payouts, event escrows.
