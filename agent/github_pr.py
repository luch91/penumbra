"""Small GitHub PR reporting adapter for the PenumbraGate agent.

This module reports a finalized on-chain recommendation. It never merges a
pull request and never sends source text to GitHub as an instruction.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class PullRequestRef:
    owner: str
    repository: str
    number: int


def parse_pull_request_ref(payload: dict[str, object]) -> PullRequestRef:
    """Extract a PR reference from a GitHub webhook payload."""
    repository = payload.get("repository")
    pull_request = payload.get("pull_request")
    if not isinstance(repository, dict) or not isinstance(pull_request, dict):
        raise ValueError("payload is not a pull request event")
    owner_data = repository.get("owner")
    owner = owner_data.get("login") if isinstance(owner_data, dict) else None
    name = repository.get("name")
    number = pull_request.get("number")
    if not isinstance(owner, str) or not owner:
        raise ValueError("payload has no repository owner")
    if not isinstance(name, str) or not name:
        raise ValueError("payload has no repository name")
    if isinstance(number, bool) or not isinstance(number, int) or number < 1:
        raise ValueError("payload has no valid pull request number")
    return PullRequestRef(owner, name, number)


class GitHubPRReporter:
    """Report recommendations through the GitHub REST API.

    Required environment variable: ``PENUMBRA_GITHUB_TOKEN``. The token is
    read at call time and is never included in logs or return values.
    """

    def __init__(self, token: str | None = None, api_url: str = "https://api.github.com"):
        self._token = token or os.environ.get("PENUMBRA_GITHUB_TOKEN", "")
        self._api_url = api_url.rstrip("/")
        if not self._token:
            raise ValueError("PENUMBRA_GITHUB_TOKEN is required")

    def _request(self, method: str, path: str, body: dict[str, object] | None = None) -> dict[str, object]:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = Request(
            self._api_url + path,
            data=data,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": "Bearer " + self._token,
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
                "User-Agent": "penumbra-gate-agent",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                raw = response.read().decode("utf-8")
        except (HTTPError, URLError) as exc:
            raise RuntimeError("GitHub API request failed") from exc
        value = json.loads(raw) if raw else {}
        if not isinstance(value, dict):
            raise RuntimeError("GitHub API returned an invalid response")
        return value

    def comment(self, ref: PullRequestRef, body: str) -> dict[str, object]:
        if not body.strip():
            raise ValueError("comment body is required")
        return self._request(
            "POST",
            f"/repos/{ref.owner}/{ref.repository}/issues/{ref.number}/comments",
            {"body": body},
        )

    def label(self, ref: PullRequestRef, label: str) -> dict[str, object]:
        if not label.strip():
            raise ValueError("label is required")
        return self._request(
            "POST",
            f"/repos/{ref.owner}/{ref.repository}/issues/{ref.number}/labels",
            {"labels": [label]},
        )

    def close(self, ref: PullRequestRef) -> dict[str, object]:
        return self._request(
            "PATCH",
            f"/repos/{ref.owner}/{ref.repository}/issues/{ref.number}",
            {"state": "closed"},
        )


def recommendation_message(verdict: str, reason: str, transaction_hash: str) -> str:
    """Build a human-facing PR report from finalized contract data."""
    normalized = verdict.strip().upper()
    if normalized not in {"ACCEPT", "REJECT"}:
        raise ValueError("verdict must be ACCEPT or REJECT")
    if not transaction_hash.startswith("0x"):
        raise ValueError("transaction hash must be hexadecimal")
    action = "recommended for human merge" if normalized == "ACCEPT" else "rejected"
    return (
        f"PenumbraGate verdict: {normalized}\n\n"
        f"Recommendation: {action}.\n"
        f"Reason: {reason.strip() or 'No reason was recorded.'}\n\n"
        f"Finalized transaction: {transaction_hash}"
    )
