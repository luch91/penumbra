"""Deterministic intake checks and GenLayer transaction orchestration.

The agent recommends. It never merges a contribution and never holds stake.
The rubric is read from a caller-supplied file because the handoff documents
are source material, not repository files.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


RUNNER_RE = re.compile(
    r'^# \{ "Depends": "py-genlayer:([a-z0-9]{20,})" \}$', re.MULTILINE
)
REQUIRED_DOC_SECTIONS = ("PURPOSE", "CONSENSUS", "STATE DESIGN", "REUSE")
FORBIDDEN_PUBLIC_TYPES = ("typing.Any", "Any")
FORBIDDEN_STORAGE_TYPES = {"int", "float", "dict", "list", "typing.Any", "Any"}


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str


def _ascii_check(path: Path) -> CheckResult:
    try:
        path.read_bytes().decode("ascii")
    except UnicodeDecodeError as exc:
        return CheckResult("ascii", False, str(exc))
    return CheckResult("ascii", True, "pure ASCII")


def _compile_check(path: Path) -> CheckResult:
    result = subprocess.run(
        ["python3", "-m", "py_compile", str(path)],
        capture_output=True,
        text=True,
    )
    if result.returncode:
        return CheckResult("py_compile", False, result.stderr.strip())
    return CheckResult("py_compile", True, "compiled")


def _runner_check(text: str) -> CheckResult:
    first_line = text.splitlines()[0] if text.splitlines() else ""
    match = RUNNER_RE.fullmatch(first_line)
    if match and match.group(1) not in {"test", "latest"}:
        return CheckResult("runner_hash", True, "pinned runner hash")
    return CheckResult("runner_hash", False, "missing pinned py-genlayer content hash")


def _doc_check(tree: ast.AST) -> CheckResult:
    module_doc = ast.get_docstring(tree) or ""
    missing = [section for section in REQUIRED_DOC_SECTIONS if section not in module_doc]
    if missing:
        return CheckResult("documentation", False, "missing: " + ", ".join(missing))
    return CheckResult("documentation", True, "purpose, consensus, state, and reuse documented")


def _public_type_check(tree: ast.AST) -> CheckResult:
    failures: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.name or node.name.startswith("_"):
            continue
        rendered = ast.unparse(node.returns) if node.returns else ""
        if any(token in rendered for token in FORBIDDEN_PUBLIC_TYPES):
            failures.append(node.name)
    if failures:
        return CheckResult("public_types", False, "unsupported return type in " + ", ".join(failures))
    return CheckResult("public_types", True, "no forbidden public return types")


def _storage_type_check(tree: ast.AST) -> CheckResult:
    failures: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for child in node.body:
            if not isinstance(child, ast.AnnAssign) or child.annotation is None:
                continue
            rendered = ast.unparse(child.annotation)
            if rendered in FORBIDDEN_STORAGE_TYPES:
                target = ast.unparse(child.target)
                failures.append(f"{node.name}.{target}: {rendered}")
    if failures:
        return CheckResult("storage_types", False, "unsupported storage type: " + ", ".join(failures))
    return CheckResult("storage_types", True, "class storage uses supported typed fields")


def _appeal_method_check(tree: ast.AST) -> CheckResult:
    forbidden = {"appeal", "reroll", "resubmit_for_review"}
    found = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in forbidden
    ]
    if found:
        return CheckResult("appeal_methods", False, "custom appeal method: " + ", ".join(found))
    return CheckResult("appeal_methods", True, "no custom appeal or reroll method")


def _balance_transfer_check(tree: ast.AST) -> CheckResult:
    failures: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body_text = ast.unparse(node)
        touches_balance = "claimable" in body_text or "balance" in body_text
        emits_transfer = "emit_transfer" in body_text
        if touches_balance and ("withdraw" in node.name or "settle" in node.name or "payout" in node.name):
            if not emits_transfer:
                failures.append(node.name)
    if failures:
        return CheckResult("real_custody", False, "no transfer in " + ", ".join(failures))
    return CheckResult("real_custody", True, "balance-affecting payout paths include emit_transfer")


def _web_scope_check(tree: ast.AST) -> CheckResult:
    failures: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        callee = ast.unparse(node.func)
        if "gl.nondet.web" not in callee:
            continue
        if not node.args:
            continue
        url_text = ast.unparse(node.args[0])
        if any(name in url_text.lower() for name in ("source", "url", "uri", "input")):
            parent_hint = ast.unparse(node)
            if "allowlist" not in parent_hint.lower() and "allowed_domains" not in parent_hint.lower():
                failures.append(parent_hint)
    if failures:
        return CheckResult("web_scope", False, "possible unscoped URL: " + failures[0])
    return CheckResult("web_scope", True, "no attacker-controlled web target detected")


def scan_contract(path: str | Path) -> list[CheckResult]:
    contract_path = Path(path)
    raw = contract_path.read_bytes()
    text = raw.decode("ascii")
    tree = ast.parse(text, filename=str(contract_path))
    return [
        _ascii_check(contract_path),
        _compile_check(contract_path),
        _runner_check(text),
        _doc_check(tree),
        _public_type_check(tree),
        _storage_type_check(tree),
        _appeal_method_check(tree),
        _balance_transfer_check(tree),
        _web_scope_check(tree),
    ]


def load_rubric(path: str | Path) -> tuple[str, str]:
    """Load the exact external rubric and split it without rewriting text."""
    rubric = Path(path).read_text(encoding="utf-8")
    headings = [f"NN-{index}" for index in range(1, 9)]
    missing = [heading for heading in headings if heading not in rubric]
    if missing:
        raise ValueError("rubric is missing: " + ", ".join(missing))
    marker = "## Tier B"
    split_at = rubric.find(marker)
    if split_at < 0:
        raise ValueError("rubric must contain the Tier B marker")
    return rubric[:split_at], rubric[split_at:]


def build_submit_arguments(source: str, summary: str) -> list[str]:
    """Return calldata values. Source remains data and is never prompt text."""
    if not source.strip() or not summary.strip():
        raise ValueError("source and summary are required")
    return [source, summary]


def wait_for_finalized(client: Any, transaction_hash: str) -> Any:
    """Wait for FINALIZED, never merely ACCEPTED.

    The call signature is documented by GenLayerPY. Importing the enum lazily
    keeps deterministic pre-filter use independent of an installed SDK.
    """
    from genlayer_py.types import TransactionStatus

    # The public SDK does not expose a developer-side minimum-gas setter.
    # Finality polling remains mandatory because the contract has no action
    # that depends on an appeal being available.
    return client.wait_for_transaction_receipt(
        transaction_hash=transaction_hash,
        status=TransactionStatus.FINALIZED,
        full_transaction=True,
    )


def _round_number(receipt: Any) -> int:
    if not isinstance(receipt, dict):
        return 0
    last_round = receipt.get("last_round") or receipt.get("lastRound") or {}
    value = last_round.get("round", 0) if isinstance(last_round, dict) else 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def receipt_used_appeal(receipt: Any, default_validator_count: int = 0) -> bool:
    if _round_number(receipt) > 0:
        return True
    if not isinstance(receipt, dict):
        return False
    last_round = receipt.get("last_round") or receipt.get("lastRound") or {}
    validators = last_round.get("round_validators", []) if isinstance(last_round, dict) else []
    return bool(default_validator_count and len(validators) > default_validator_count)


def mark_appealed_if_needed(
    client: Any,
    contract_address: str,
    submission_id: int,
    receipt: Any,
    default_validator_count: int = 0,
) -> Any | None:
    """Record an observed appeal only after the original tx is finalized."""
    # Appeal-round metadata is not exposed in contract context. This external
    # receipt observation only records an audit flag after finality.
    if not receipt_used_appeal(receipt, default_validator_count):
        return None
    tx_hash = client.write_contract(
        address=contract_address,
        function_name="mark_appealed",
        args=[submission_id],
        value=0,
    )
    return wait_for_finalized(client, tx_hash)


def submit_and_wait(
    client: Any,
    account: Any,
    contract_address: str,
    source: str,
    summary: str,
    value: int,
) -> tuple[str, Any]:
    tx_hash = client.write_contract(
        account=account,
        address=contract_address,
        function_name="submit",
        args=build_submit_arguments(source, summary),
        value=value,
    )
    return tx_hash, wait_for_finalized(client, tx_hash)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run PenumbraGate mechanical intake checks")
    parser.add_argument("contract", type=Path)
    parser.add_argument("--rubric", type=Path, required=True)
    args = parser.parse_args()
    results = scan_contract(args.contract)
    load_rubric(args.rubric)
    print(json.dumps([result.__dict__ for result in results], indent=2, sort_keys=True))
    return 0 if all(result.passed for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
