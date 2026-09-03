# Setup & running

You do **not** need a local network to validate these contracts. Pick the lightest path that does what you need.

## The three environments

| | What it is | Needs | Use it for |
|---|---|---|---|
| **Browser Studio** | studio.genlayer.com | nothing | Interactive smoke-testing. Start here. |
| **studionet** | hosted shared network | Python 3.12 + `genlayer-test` | Running the automated gltest suite. |
| **localnet** | full local network in Docker | Docker 26+, Node 18+, working `genlayer init` | Offline / local-LLM testing. Optional -- skip unless you need it. |

## Runner pinning (read this first)

Each contract's first line pins the GenVM runner **by hash**, not by a floating tag:

```
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
```

Studionet, Asimov, and Bradbury all **reject floating tags** (`py-genlayer:test`, `py-genlayer:latest`) at deploy -- every validator must resolve to the same runner binary or consensus breaks. If a deploy fails with `invalid_contract`, the pinned hash has advanced: get the current one from the [Available Runners](https://sdk.genlayer.com/main/impl-spec/appendix/available-runners.html) appendix and update the header. Multi-file contracts use `py-genlayer-multi:...`.

## Fastest validation (zero install)

1. Open https://studio.genlayer.com
2. Contracts -> paste a file from `contracts/` -> Deploy (constructor params are auto-detected).
3. Call the read/write methods and watch the consensus logs.

Smoke-test the five built contracts first: `dissensus_oracle.py` (deploy `7, 250`; `resolve("Is water wet?")`), `jailbreak_bounty.py` (deploy with a rule; `fund()` with value; `attempt("hello")`), `proof_carrying_answer.py` (`attest` a sound proof, then a bogus one), `schelling_resolver.py` (deploy `2`; `submit("blue")` with value from two different accounts, then `resolve()`), `semantic_deadman.py` (deploy `beneficiary, liveness_url, liveness_policy`; `poke()` -- unlike the other payable-gated contracts, this one's full LLM path needs no value and works from the CLI too). A failed liveness fetch must now be verified as `FETCH_FAILED`: it must leave the treasury, release flag, claimable balance, and baseline unchanged.

## CLI smoke-testing

`genlayer deploy --contract contracts/<file>.py --args ...` / `genlayer call <address> <method> --args ...` (read) / `genlayer write <address> <method> --args ...` (write) work directly against studionet once `genlayer init` has been run once and an account is unlocked (`genlayer account unlock`). This is how the runner-specific issues documented in `DECISIONS.md` were found -- by deploying and calling, not by reading the docs.

**Known CLI gap:** `genlayer write` hardcodes `value: 0n` on every call -- there is no way to send payable value through it. `--fee-value` is a gas or fee deposit, not `gl.message.value`. To smoke-test a `.payable` method, use the browser Studio or the JavaScript SDK. The SDK path is the current reproducible route for Studionet because it supports an explicit transaction `value` field.

**Account note:** a fresh account (not the CLI's default `default`/`funded` keystores) may be needed -- those can end up locked with a lost password and 0 GEN, in which case `genlayer account create --name <name>` and `genlayer account use <name>` is faster than trying to recover them.

## Running the test suite (gltest)

`genlayer-test` requires **Python 3.12+**. On an older Python, pip ignores every modern version and fails -- that is the cause of `Could not find a version that satisfies the requirement genlayer-test`.

```bash
conda create -n genlayer python=3.12 -y
conda activate genlayer            # re-run this in every new terminal
pip install -r requirements-dev.txt
cp .env.example .env               # gltest needs this env var defined even for studionet -- see below
gltest --network studionet         # studionet needs no Docker
# single file while iterating:
gltest --network studionet tests/test_dissensus_oracle.py
```

The repo root's `conftest.py` un-disables `gltest`'s own internal logger (disabled by default upstream), so a schema-fetch failure shows the real per-client reason instead of a generic `ValueError`. Don't remove it.

These tests call live LLMs, so a borderline non-deterministic assertion can occasionally flake -- re-run before treating it as a real failure. The structural assertions (preconditions, dedupe, ledger math) are deterministic and should always pass.

**gltest now actually works end-to-end in this repo -- confirmed live 2026-07-01.** It took three fixes to get there, and the real blocker was not what it first looked like:
- `gltest.config.yaml` had `studionet:` with no value, which YAML parses as `null` -- gltest requires every network entry to be a dictionary. **Fixed**: changed to `studionet: {}`.
- `gltest` also eagerly validates every network block in the config, including unused ones -- it errored on a missing `ACCOUNT_PRIVATE_KEY_1` (needed only by `testnet_asimov`) even when running `--network studionet`. Set a placeholder in the environment (or a `.env` file) to get past config validation.
- **The real blocker, and the one that actually mattered**: every deploy via `gltest` failed with `ValueError: Failed to get schema from all clients (default, hosted studio, and local)`. This is NOT a funding/gas issue (studionet doesn't need GEN for gas -- this repo's own `genlayer` CLI account sat at `0 GEN` through every successful deploy all session) and NOT a client-connectivity issue either, despite that being the first two guesses. The actual cause, found by reading `gltest`'s source (`gltest/contracts/contract_factory.py::_get_schema_with_fallback`) and reproducing it directly: the schema-fetch call (`client.get_contract_schema_for_code(...)`) raises `UnicodeEncodeError` the instant a contract's source contains ANY non-ASCII character (an em dash, a middle dot, a box-drawing divider, etc.) -- and every contract in this repo used exactly those characters throughout its docstrings. `gltest`'s own internal logger, which would have shown this immediately, is `disabled = True` by default (`gltest/logging.py`), which is why it took this long to find. **Fixed**: stripped every non-ASCII character from every file under `contracts/` (README.md/CONTRACTS.md/DECISIONS.md keep their normal typography -- they're never sent through this call). A root `conftest.py` now un-disables gltest's logger so a future regression is diagnosable immediately instead of hiding behind the generic `ValueError`. **New rule for every future contract: `contracts/*.py` (including test fixtures) must be pure ASCII.** See DECISIONS.md's "Known blockers" and "Definition of done" for the durable version of this rule, and `DECISIONS.md`'s 2026-07-01 entry for the full story.

The last complete catalog suite run was on 2026-08-28: it collected 155 tests and passed all 155, including all 20 catalog contracts, PenumbraGate, and agent tests. The current checkout collects 160 tests, so run the full command again to establish a fresh baseline. Live consensus can experience transient network failures; retry and document those separately from source failures.

## Optional: local network

Only if you want fully offline / local-LLM testing. Requires Docker Desktop (26+) installed and running, plus the GenLayer CLI.

```bash
npm install -g genlayer
genlayer init        # downloads + configures Docker containers; prompts for an LLM provider
genlayer up          # launches localnet + Studio at http://localhost:8080/
gltest --network localnet
```

If `genlayer init` crashes in `checkCliVersion` / `update-check` (`Cannot read properties of undefined (reading 'code')`), that is the CLI failing to reach the npm registry during its version check -- not a problem with this repo. Try `npm config set registry https://registry.npmjs.org/` and retry, confirm Docker is running, and ensure Node 18+. If it keeps failing, just use the browser Studio + studionet above; localnet is not required to build or submit.
