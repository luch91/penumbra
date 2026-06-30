# Setup & running

You do **not** need a local network to validate these contracts. Pick the lightest path that does what you need.

## The three environments

| | What it is | Needs | Use it for |
|---|---|---|---|
| **Browser Studio** | studio.genlayer.com | nothing | Interactive smoke-testing. Start here. |
| **studionet** | hosted shared network | Python 3.12 + `genlayer-test` | Running the automated gltest suite. |
| **localnet** | full local network in Docker | Docker 26+, Node 18+, working `genlayer init` | Offline / local-LLM testing. Optional — skip unless you need it. |

## Fastest validation (zero install)

1. Open https://studio.genlayer.com
2. Contracts → paste a file from `contracts/` → Deploy (constructor params are auto-detected).
3. Call the read/write methods and watch the consensus logs.

Smoke-test the three flagships first: `dissensus_oracle.py` (deploy `7, 250`; `resolve("Is water wet?")`), `jailbreak_bounty.py` (deploy with a rule; `fund()` with value; `attempt("hello")`), `proof_carrying_answer.py` (`attest` a sound proof, then a bogus one). This confirms the surfaces tagged `# VERIFY:` in the source.

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

## Optional: local network

Only if you want fully offline / local-LLM testing. Requires Docker Desktop (26+) installed and running, plus the GenLayer CLI.

```bash
npm install -g genlayer
genlayer init        # downloads + configures Docker containers; prompts for an LLM provider
genlayer up          # launches localnet + Studio at http://localhost:8080/
gltest --network localnet
```

If `genlayer init` crashes in `checkCliVersion` / `update-check` (`Cannot read properties of undefined (reading 'code')`), that is the CLI failing to reach the npm registry during its version check — not a problem with this repo. Try `npm config set registry https://registry.npmjs.org/` and retry, confirm Docker is running, and ensure Node 18+. If it keeps failing, just use the browser Studio + studionet above; localnet is not required to build or submit.
