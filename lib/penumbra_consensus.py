# -----------------------------------------------------------------------------
# PENUMBRA -- shared consensus helpers
#
# GenLayer Intelligent Contracts run as a SINGLE Python file inside the GenVM.
# There is no `pip install` and no cross-file import at deploy time. So this is
# not an importable module -- it is a CURATED COPY-PASTE BLOCK. Drop the helpers
# you need into the top of a contract, below `from genlayer import *`.
#
# Every helper here exists to make one thing explicit: the boundary between the
# DETERMINISTIC world (storage, money, control flow -- must be identical on every
# validator) and the NON-DETERMINISTIC world (LLM calls, web reads -- allowed to
# differ, reconciled by an Equivalence Principle).
#
# The cardinal rule, encoded in every pattern below:
#   A non-deterministic block is an argument-free inner function. It may NOT
#   touch `self` or storage. Read what you need into locals first, close over
#   them, and return a *canonical* value the validators can compare.
# -----------------------------------------------------------------------------

import json


# --- reverting -----------------------------------------------------------------
# Any uncaught exception fails the transaction and rolls back state. We prefer a
# named error type when the runtime exposes one, and fall back to Exception so
# the same code deploys across SDK versions.
try:
    _PenumbraError = gl.vm.UserError  # type: ignore  # noqa: F821
except Exception:  # pragma: no cover - depends on runtime
    _PenumbraError = Exception


def require(condition: bool, message: str) -> None:
    """Deterministic precondition. Runs identically on every validator."""
    if not condition:
        raise _PenumbraError(message)


# --- canonicalization ----------------------------------------------------------
def canonical(obj) -> str:
    """
    Turn an object into a byte-stable string. This is the single most important
    helper in the whole library: strict_eq compares validator outputs for *exact*
    equality, so two validators that produce semantically identical dicts must
    serialize them identically. Sorted keys + tight separators guarantee that.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


# --- non-deterministic primitives ---------------------------------------------
# These are meant to be CALLED FROM INSIDE an inner nondet function, never from a
# method body directly.

def ask_json(prompt: str) -> dict:
    """One LLM call that must return JSON. Returns a parsed dict."""
    return gl.nondet.exec_prompt(prompt, response_format="json")  # noqa: F821


def ask_text(prompt: str) -> str:
    """One LLM call that returns free text."""
    return gl.nondet.exec_prompt(prompt)  # noqa: F821


def read_web(url: str, mode: str = "text") -> str:
    """Render a web page to text or html. Non-deterministic: validators each fetch."""
    return gl.nondet.web.render(url, mode=mode)  # noqa: F821


# --- equivalence wrappers ------------------------------------------------------
# Thin, documented wrappers over the three built-in equivalence principles so the
# *intent* of each consensus step is legible at the call site.

def agree_exact(inner):
    """
    strict_eq: every validator must produce a byte-identical result. Use only for
    nondet work whose output you have canonicalized (numbers, normalized JSON,
    booleans). The strongest and cheapest principle; the least forgiving.
    """
    return gl.eq_principle.strict_eq(inner)  # noqa: F821


def agree_meaning(inner, principle: str):
    """
    prompt_comparative: each validator re-runs `inner` and an LLM decides whether
    its result is EQUIVALENT to the leader's under `principle`. Use when answers
    can be phrased differently but must mean the same thing. The validator does
    the same work as the leader, then compares.
    """
    return gl.eq_principle.prompt_comparative(inner, principle)  # noqa: F821


def agree_integrity(inner, *, task: str, criteria: str):
    """
    prompt_non_comparative: the leader performs `task` on the input returned by
    `inner`; validators do NOT redo the task -- they only check that the leader's
    output satisfies `criteria`. This is the asymmetric principle: cheap to verify,
    expensive to produce. Use when generation is hard but checking is easy, and
    when the input is the same on every node (so there is nothing to disagree
    about except the judgment itself).
    """
    return gl.eq_principle.prompt_non_comparative(inner, task=task, criteria=criteria)  # noqa: F821
