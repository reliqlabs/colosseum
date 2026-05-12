#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "mcp>=1.2.0",
#     "httpx>=0.27.0",
# ]
# ///
"""
lm-studio-mcp: General-purpose wrapper for local models served via LM Studio's
OpenAI-compatible endpoint.

Separate from `goedel-mcp` (which is specialized for Lean tactic proposal).
This MCP is the **adversarial floor** of Colosseum's multi-model story: local
models on the user's hardware give genuine architectural diversity (different
training data, different RLHF lineage) at zero marginal cost. Useful as the
always-on cheap voice in adversarial spec review.

Exposes:
  - list_loaded_models — what's available in the LM Studio session
  - query_local         — single-shot completion against a chosen model
  - fan_out_local       — same prompt against multiple loaded models in parallel
  - check_lmstudio_health — endpoint reachable + at least one model loaded

Run standalone:
    ./lm_studio_mcp.py

Or register with Claude Code via .mcp.json (see README.md).
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

LMSTUDIO_BASE_URL = os.environ.get("LMSTUDIO_BASE_URL", "http://localhost:1234/v1")
DEFAULT_TIMEOUT_S = float(os.environ.get("LMSTUDIO_TIMEOUT_S", "300"))
DEFAULT_MODEL = os.environ.get("LMSTUDIO_DEFAULT_MODEL")

mcp = FastMCP("lm-studio-mcp")


async def _list_models(client: httpx.AsyncClient) -> list[str]:
    resp = await client.get(f"{LMSTUDIO_BASE_URL}/models", timeout=10.0)
    resp.raise_for_status()
    data = resp.json()
    return [m.get("id") for m in data.get("data", []) if m.get("id")]


async def _call_lmstudio(
    client: httpx.AsyncClient,
    prompt: str,
    model: str,
    temperature: float,
    max_tokens: int,
    system_prompt: str | None,
) -> dict[str, Any]:
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    response = await client.post(
        f"{LMSTUDIO_BASE_URL}/chat/completions",
        json={
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        },
        timeout=DEFAULT_TIMEOUT_S,
    )
    response.raise_for_status()
    data = response.json()
    return {
        "text": data["choices"][0]["message"]["content"],
        "finish_reason": data["choices"][0].get("finish_reason"),
        "usage": data.get("usage", {}),
        "model_returned": data.get("model"),
    }


@mcp.tool()
async def check_lmstudio_health() -> dict[str, Any]:
    """Verify LM Studio's OpenAI-compatible endpoint is reachable and a model is loaded.

    Returns endpoint, list of loaded model ids, and a minimal completion probe
    against the first available model.
    """
    async with httpx.AsyncClient() as client:
        try:
            loaded = await _list_models(client)
        except Exception as e:
            return {
                "ok": False,
                "endpoint": LMSTUDIO_BASE_URL,
                "error": f"could not list models: {type(e).__name__}: {e}",
                "hint": (
                    "Start LM Studio, load at least one model, and enable the "
                    "developer / OpenAI-compatible server."
                ),
            }

        if not loaded:
            return {
                "ok": False,
                "endpoint": LMSTUDIO_BASE_URL,
                "loaded_models": [],
                "error": "no models loaded in LM Studio",
            }

        probe_model = DEFAULT_MODEL if DEFAULT_MODEL in loaded else loaded[0]
        completion_ok = True
        completion_error: str | None = None
        try:
            await _call_lmstudio(client, "ping", probe_model, 0.0, 4, None)
        except Exception as e:
            completion_ok = False
            completion_error = f"{type(e).__name__}: {e}"

        return {
            "ok": completion_ok,
            "endpoint": LMSTUDIO_BASE_URL,
            "loaded_models": loaded,
            "probed_model": probe_model,
            "completion_ok": completion_ok,
            "completion_error": completion_error,
        }


@mcp.tool()
async def list_loaded_models() -> dict[str, Any]:
    """Return the list of model ids currently loaded in LM Studio.

    Useful before `query_local` or `fan_out_local` to pick which models to
    target.
    """
    async with httpx.AsyncClient() as client:
        try:
            loaded = await _list_models(client)
            return {"endpoint": LMSTUDIO_BASE_URL, "loaded_models": loaded, "count": len(loaded)}
        except Exception as e:
            return {
                "endpoint": LMSTUDIO_BASE_URL,
                "error": f"{type(e).__name__}: {e}",
            }


@mcp.tool()
async def query_local(
    prompt: str,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    system_prompt: str | None = None,
) -> dict[str, Any]:
    """Send a single-shot prompt to a local model via LM Studio.

    Args:
        prompt: User message text.
        model: Model id (must be loaded). Defaults to LMSTUDIO_DEFAULT_MODEL
               or the first loaded model.
        temperature: Sampling temperature.
        max_tokens: Max completion tokens.
        system_prompt: Optional system message.
    """
    async with httpx.AsyncClient() as client:
        try:
            loaded = await _list_models(client)
        except Exception as e:
            return {"error": f"could not list models: {type(e).__name__}: {e}"}
        if not loaded:
            return {"error": "no models loaded in LM Studio"}

        chosen_model = model or DEFAULT_MODEL or loaded[0]
        if chosen_model not in loaded:
            return {
                "error": f"model '{chosen_model}' not loaded",
                "loaded_models": loaded,
            }
        try:
            result = await _call_lmstudio(
                client, prompt, chosen_model, temperature, max_tokens, system_prompt
            )
            return {"provider": "lm-studio", "model": chosen_model, **result}
        except Exception as e:
            return {
                "provider": "lm-studio",
                "model": chosen_model,
                "error": f"{type(e).__name__}: {e}",
            }


@mcp.tool()
async def fan_out_local(
    prompt: str,
    models: list[str] | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    system_prompt: str | None = None,
) -> dict[str, Any]:
    """Send the same prompt to multiple loaded local models in parallel.

    The local equivalent of `external-model-mcp`'s fan_out_query — produces
    architecturally-diverse responses from local-only inference. Useful as
    the cheap always-on layer of adversarial review.

    Note: parallel local inference contends for the same GPU/CPU resources.
    On consumer hardware, two parallel calls to two large models will
    serialize at the LM Studio layer. Use small / fast models here, or
    accept the sequential effective execution.

    Args:
        prompt: User message text.
        models: Subset of loaded models to target. Default: all loaded.
        temperature: Sampling temperature (uniform).
        max_tokens: Max completion tokens (uniform).
        system_prompt: Optional system message (uniform).
    """
    async with httpx.AsyncClient() as client:
        try:
            loaded = await _list_models(client)
        except Exception as e:
            return {"error": f"could not list models: {type(e).__name__}: {e}"}
        if not loaded:
            return {"error": "no models loaded in LM Studio"}

        targets = models or loaded
        targets = [m for m in targets if m in loaded]
        if not targets:
            return {
                "error": "none of the requested models are loaded",
                "loaded_models": loaded,
                "requested": models,
            }

        tasks = [
            _call_lmstudio(client, prompt, m, temperature, max_tokens, system_prompt)
            for m in targets
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    out: dict[str, Any] = {"endpoint": LMSTUDIO_BASE_URL, "models_queried": targets, "responses": {}}
    for model, result in zip(targets, results):
        if isinstance(result, Exception):
            out["responses"][model] = {"error": f"{type(result).__name__}: {result}"}
        else:
            out["responses"][model] = result
    return out


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
