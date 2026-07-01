# Setup & running

You do **not** need a local network to validate these contracts. Pick the lightest path that does what you need.

## The three environments

| | What it is | Needs | Use it for |
|---|---|---|---|
| **Browser Studio** | studio.genlayer.com | nothing | Interactive smoke-testing. Start here. |
| **studionet** | hosted shared network | Python 3.12 + `genlayer-test` | Running the automated gltest suite. |
| **localnet** | full local network in Docker | Docker 26+, Node 18+, working `genlayer init` | Offline / local-LLM testing. Optional — skip unless you need it. |

## Runner pinning (read this first)

Each contract's first line pins the GenVM runner **by hash**, not by a floating tag:

```
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
```

Studionet, Asimov, and Bradbury all **reject floating tags** (`py-genlayer:test`, `py-genlayer:latest`) at deploy — every validator must resolve to the same runner binary or consensus breaks. If a deploy fails with `invalid_contract`, the pinned hash has advanced: get the current one from the [Available Runners](https://sdk.genlayer.com/main/impl-spec/appendix/available-runners.html) appendix and update the header. Multi-file contracts use `py-genlayer-multi:...`.

## Fastest validation (zero install)

1. Open https://studio.genlayer.com
2. Contracts → paste a file from `contracts/` → Deploy (constructor params are auto-detected).
3. Call the read/write methods and watch the consensus logs.

Smoke-test the five built contracts first: `dissensus_oracle.py` (deploy `7, 250`; `resolve("Is water wet?")`), `jailbreak_bounty.py` (deploy with a rule; `fund()` with value; `attempt("hello")`), `proof_carrying_answer.py` (`attest` a sound proof, then a bogus one), `schelling_resolver.py` (deploy `2`; `submit("blue")` with value from two different accounts, then `resolve()`), `semantic_deadman.py` (deploy `beneficiary, liveness_url, liveness_policy`; `poke()` — unlike the other payable-gated contracts, this one's full LLM path needs no value and works from the CLI too).

## CLI smoke-testing

`genlayer deploy --contract contracts/<file>.py --args ...` / `genlayer call <address> <method> --args ...` (read) / `genlayer write <address> <method> --args ...` (write) work directly against studionet once `genlayer init` has been run once and an account is unlocked (`genlayer account unlock`). This is how every bug listed under "Known blockers & open verification gaps" in `CLAUDE.md` was actually found — by deploying and calling, not by reading the docs.

**Known CLI gap:** `genlayer write` (v0.39.2) hardcodes `value: 0n` on every call — there is no way to send payable value through it. `--fee-value` is gas/fee deposit, not `gl.message.value`. To smoke-test a `.payable` method (`JailbreakBounty.fund()`), use the browser Studio instead — it has a dedicated value field on write calls.

**Account note:** a fresh account (not the CLI's default `default`/`funded` keystores) may be needed — those can end up locked with a lost password and 0 GEN, in which case `genlayer account create --name <name>` and `genlayer account use <name>` is faster than trying to recover them.

## Running the test suite (gltest)

`genlayer-test` requires **Python 3.12+**. On an older Python, pip ignores every modern version and fails — that is the cause of `Could not find a version that satisfies the requirement genlayer-test`.

```bash
conda create -n genlayer python=3.12 -y
conda activate genlayer            # re-run this in every new terminal
pip install -r requirements-dev.txt
gltest --network studionet         # studionet needs no Docker
# single file while iterating:
gltest --network studionet tests/test_dissensus_oracle.py
```

These tests call live LLMs, so a borderline non-deterministic assertion can occasionally flake — re-run before treating it as a real failure. The structural assertions (preconditions, dedupe, ledger math) are deterministic and should always pass.

**gltest has not been run end-to-end in this repo yet — confirmed live 2026-07-01 while building MirrorAudit.** Two real gaps found:
- `gltest.config.yaml` had `studionet:` with no value, which YAML parses as `null` — gltest requires every network entry to be a dictionary. **Fixed**: changed to `studionet: {}`.
- `gltest` also eagerly validates every network block in the config, including unused ones — it errored on a missing `ACCOUNT_PRIVATE_KEY_1` (needed only by `testnet_asimov`) even when running `--network studionet`. Set a placeholder in the environment (or a `.env` file) to get past config validation.
- **Still unresolved**: `gltest`'s own `accounts`/`default_account` fixtures (`gltest/glchain/account.py`) generate a fresh, unfunded keypair every run via `genlayer_py.create_account()` — with 0 GEN, contract deploys to studionet fail with `ValueError: Failed to get schema from all clients`. There is currently no funded account wired into gltest for this repo. Fixing this needs either a funded private key supplied via `.env`/the config's `accounts:` list, or confirming studionet auto-funds fresh gltest accounts (unconfirmed). Until resolved, this repo's actual verification path remains the live `genlayer` CLI (deploy/call/write), not `gltest` — the test files exist and are believed correct by inspection, but have not themselves been executed successfully against studionet.

## Optional: local network

Only if you want fully offline / local-LLM testing. Requires Docker Desktop (26+) installed and running, plus the GenLayer CLI.

```bash
npm install -g genlayer
genlayer init        # downloads + configures Docker containers; prompts for an LLM provider
genlayer up          # launches localnet + Studio at http://localhost:8080/
gltest --network localnet
```

If `genlayer init` crashes in `checkCliVersion` / `update-check` (`Cannot read properties of undefined (reading 'code')`), that is the CLI failing to reach the npm registry during its version check — not a problem with this repo. Try `npm config set registry https://registry.npmjs.org/` and retry, confirm Docker is running, and ensure Node 18+. If it keeps failing, just use the browser Studio + studionet above; localnet is not required to build or submit.
