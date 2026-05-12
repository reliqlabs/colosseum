#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "mcp>=1.2.0",
#     "httpx>=0.27.0",
# ]
# ///
"""
goedel-mcp: Expose a locally-running Goedel Prover (via LM Studio) as an MCP tool.

Provides Lean 4 tactic proposals to Claude Code (or any MCP-compatible client)
by routing prompts to a local Goedel-Prover-V2 instance served by LM Studio's
OpenAI-compatible chat completions endpoint.

Run standalone:
    ./goedel_mcp.py

Or register with Claude Code via .mcp.json (see README.md).
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

LMSTUDIO_BASE_URL = os.environ.get("GOEDEL_LMSTUDIO_URL", "http://localhost:1234/v1")
GOEDEL_MODEL_ID = os.environ.get("GOEDEL_MODEL_ID", "goedel-prover-v2-32b")
REQUEST_TIMEOUT_S = float(os.environ.get("GOEDEL_TIMEOUT_S", "180"))

mcp = FastMCP("goedel-mcp")


def _format_prompt(goal_state: str, hypotheses: str | None = None) -> str:
    """Format proof state into a Goedel-Prover-V2 tactic-generation prompt.

    The exact format Goedel was trained on is not publicly specified; this
    template treats the model as a Lean 4 expert and asks for a tactic only.
    Tune via the GOEDEL_PROMPT_TEMPLATE env var if needed (future work).
    """
    sections = ["You are an expert Lean 4 theorem prover."]
    if hypotheses:
        sections.append(f"Hypotheses in scope:\n{hypotheses}")
    sections.append(f"Current goal:\n{goal_state}")
    sections.append(
        "Propose a single Lean 4 tactic that makes progress on this goal. "
        "Respond with only the tactic text — no explanation, no markdown, no code fences."
    )
    return "\n\n".join(sections)


async def _call_goedel(
    client: httpx.AsyncClient,
    prompt: str,
    temperature: float,
    max_tokens: int,
) -> str:
    response = await client.post(
        f"{LMSTUDIO_BASE_URL}/chat/completions",
        json={
            "model": GOEDEL_MODEL_ID,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        },
        timeout=REQUEST_TIMEOUT_S,
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"].strip()


@mcp.tool()
async def propose_lean_tactic(
    goal_state: str,
    n: int = 5,
    temperature: float = 0.7,
    max_tokens: int = 256,
    hypotheses: str | None = None,
) -> dict[str, Any]:
    """Propose Lean 4 tactics that advance the given proof goal.

    Routes the goal state to a locally-running Goedel-Prover-V2 instance.
    Generates `n` independent candidates by repeated sampling.

    Args:
        goal_state: The current Lean 4 proof goal (e.g. output of #check or LSP goal query).
        n: Number of independent tactic candidates to generate.
        temperature: Sampling temperature (0.0 = deterministic, higher = more diverse).
        max_tokens: Maximum tokens per candidate response.
        hypotheses: Optional hypotheses-in-scope to include in the prompt.

    Returns:
        dict with `candidates` (list of tactic strings, possibly with duplicates)
        and `metadata` (model + sampling params used).
    """
    if n < 1:
        return {"candidates": [], "metadata": {"error": "n must be >= 1"}}

    prompt = _format_prompt(goal_state, hypotheses)

    async with httpx.AsyncClient() as client:
        tasks = [
            _call_goedel(client, prompt, temperature, max_tokens) for _ in range(n)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    candidates: list[str] = []
    errors: list[str] = []
    for r in results:
        if isinstance(r, Exception):
            errors.append(f"{type(r).__name__}: {r}")
        else:
            candidates.append(r)

    return {
        "candidates": candidates,
        "metadata": {
            "model": GOEDEL_MODEL_ID,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "n_requested": n,
            "n_returned": len(candidates),
            "errors": errors,
            "endpoint": LMSTUDIO_BASE_URL,
        },
    }


@mcp.tool()
async def check_goedel_health() -> dict[str, Any]:
    """Verify the Goedel model is loaded and reachable at the configured endpoint.

    Returns endpoint, configured model id, and whether a minimal completion
    request succeeds. Useful as a precondition check before a proof session.
    """
    async with httpx.AsyncClient() as client:
        try:
            models_resp = await client.get(
                f"{LMSTUDIO_BASE_URL}/models", timeout=10.0
            )
            models_resp.raise_for_status()
            models_data = models_resp.json()
            loaded_ids = [m.get("id") for m in models_data.get("data", [])]
        except Exception as e:
            return {
                "ok": False,
                "endpoint": LMSTUDIO_BASE_URL,
                "configured_model": GOEDEL_MODEL_ID,
                "error": f"could not list models: {type(e).__name__}: {e}",
            }

        model_loaded = GOEDEL_MODEL_ID in loaded_ids

        completion_ok: bool
        completion_error: str | None = None
        if model_loaded:
            try:
                await _call_goedel(client, "ping", temperature=0.0, max_tokens=4)
                completion_ok = True
            except Exception as e:
                completion_ok = False
                completion_error = f"{type(e).__name__}: {e}"
        else:
            completion_ok = False
            completion_error = f"model '{GOEDEL_MODEL_ID}' not in loaded list"

        return {
            "ok": model_loaded and completion_ok,
            "endpoint": LMSTUDIO_BASE_URL,
            "configured_model": GOEDEL_MODEL_ID,
            "model_loaded": model_loaded,
            "loaded_models": loaded_ids,
            "completion_ok": completion_ok,
            "completion_error": completion_error,
        }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
