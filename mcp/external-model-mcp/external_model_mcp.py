#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "mcp>=1.2.0",
#     "httpx>=0.27.0",
# ]
# ///
"""
external-model-mcp: Route prompts to non-Anthropic frontier providers for
multi-model adversarial work.

Colosseum's "adversarial beats consensus" claim depends on genuine family
diversity — different training data, different RLHF lineage, different
architectural blind spots. This MCP exposes OpenAI and Google APIs as
Claude-callable tools so the `colosseum-adversarial` skill can dispatch
attacks across providers in parallel.

The wrapped APIs are intentionally simple: single-shot completions, no
tool-use loops, no agentic behavior. Adversarial spec review is a
long-form structured task with all artifacts inlined in one prompt —
that's the v1 contract here.

Run standalone:
    ./external_model_mcp.py

Or register with Claude Code via .mcp.json (see README.md).
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_DEFAULT_MODEL = os.environ.get("OPENAI_DEFAULT_MODEL", "gpt-4o")

GOOGLE_API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
GOOGLE_BASE_URL = os.environ.get(
    "GOOGLE_BASE_URL", "https://generativelanguage.googleapis.com/v1beta"
)
GOOGLE_DEFAULT_MODEL = os.environ.get("GOOGLE_DEFAULT_MODEL", "gemini-2.0-flash-exp")

REQUEST_TIMEOUT_S = float(os.environ.get("EXTERNAL_MODEL_TIMEOUT_S", "300"))

mcp = FastMCP("external-model-mcp")


@mcp.tool()
async def check_external_health() -> dict[str, Any]:
    """Report which external providers are configured (key present) and reachable.

    Performs a minimal probe per configured provider. Does not consume
    significant token budget — uses each provider's model-list endpoint.
    """
    out: dict[str, Any] = {"openai": {"configured": False}, "google": {"configured": False}, "ok": False}

    async with httpx.AsyncClient(timeout=15.0) as client:
        if OPENAI_API_KEY:
            out["openai"]["configured"] = True
            try:
                r = await client.get(
                    f"{OPENAI_BASE_URL}/models",
                    headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                )
                r.raise_for_status()
                data = r.json()
                ids = [m.get("id") for m in data.get("data", [])][:10]
                out["openai"]["reachable"] = True
                out["openai"]["sample_models"] = ids
                out["openai"]["default_model"] = OPENAI_DEFAULT_MODEL
            except Exception as e:
                out["openai"]["reachable"] = False
                out["openai"]["error"] = f"{type(e).__name__}: {e}"

        if GOOGLE_API_KEY:
            out["google"]["configured"] = True
            try:
                r = await client.get(
                    f"{GOOGLE_BASE_URL}/models",
                    params={"key": GOOGLE_API_KEY},
                )
                r.raise_for_status()
                data = r.json()
                ids = [m.get("name") for m in data.get("models", [])][:10]
                out["google"]["reachable"] = True
                out["google"]["sample_models"] = ids
                out["google"]["default_model"] = GOOGLE_DEFAULT_MODEL
            except Exception as e:
                out["google"]["reachable"] = False
                out["google"]["error"] = f"{type(e).__name__}: {e}"

    out["ok"] = (
        out["openai"].get("reachable", False) or out["google"].get("reachable", False)
    )
    if not OPENAI_API_KEY and not GOOGLE_API_KEY:
        out["hint"] = (
            "Set OPENAI_API_KEY and/or GEMINI_API_KEY (or GOOGLE_API_KEY) "
            "in the MCP env block."
        )
    return out


async def _call_openai(
    client: httpx.AsyncClient,
    prompt: str,
    model: str,
    temperature: float,
    max_tokens: int,
    system_prompt: str | None,
) -> dict[str, Any]:
    if not OPENAI_API_KEY:
        return {"error": "OPENAI_API_KEY not set"}
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    response = await client.post(
        f"{OPENAI_BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
        json={
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        timeout=REQUEST_TIMEOUT_S,
    )
    response.raise_for_status()
    data = response.json()
    return {
        "text": data["choices"][0]["message"]["content"],
        "finish_reason": data["choices"][0].get("finish_reason"),
        "usage": data.get("usage", {}),
        "model_returned": data.get("model"),
    }


async def _call_google(
    client: httpx.AsyncClient,
    prompt: str,
    model: str,
    temperature: float,
    max_tokens: int,
    system_prompt: str | None,
) -> dict[str, Any]:
    if not GOOGLE_API_KEY:
        return {"error": "GEMINI_API_KEY / GOOGLE_API_KEY not set"}
    model_name = model if model.startswith("models/") else f"models/{model}"
    payload: dict[str, Any] = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        },
    }
    if system_prompt:
        payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}
    response = await client.post(
        f"{GOOGLE_BASE_URL}/{model_name}:generateContent",
        params={"key": GOOGLE_API_KEY},
        json=payload,
        timeout=REQUEST_TIMEOUT_S,
    )
    response.raise_for_status()
    data = response.json()
    candidates = data.get("candidates", [])
    if not candidates:
        return {"error": "no candidates returned", "raw": data}
    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts)
    return {
        "text": text,
        "finish_reason": candidates[0].get("finishReason"),
        "usage": data.get("usageMetadata", {}),
        "model_returned": model_name,
    }


@mcp.tool()
async def query_openai(
    prompt: str,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    system_prompt: str | None = None,
) -> dict[str, Any]:
    """Send a single-shot prompt to OpenAI's chat completions endpoint.

    Args:
        prompt: User message text.
        model: Model id (default: gpt-4o or OPENAI_DEFAULT_MODEL).
        temperature: Sampling temperature.
        max_tokens: Max completion tokens.
        system_prompt: Optional system message.
    """
    chosen_model = model or OPENAI_DEFAULT_MODEL
    async with httpx.AsyncClient() as client:
        try:
            result = await _call_openai(
                client, prompt, chosen_model, temperature, max_tokens, system_prompt
            )
            return {"provider": "openai", "model": chosen_model, **result}
        except Exception as e:
            return {
                "provider": "openai",
                "model": chosen_model,
                "error": f"{type(e).__name__}: {e}",
            }


@mcp.tool()
async def query_google(
    prompt: str,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    system_prompt: str | None = None,
) -> dict[str, Any]:
    """Send a single-shot prompt to Google's Gemini API.

    Args:
        prompt: User message text.
        model: Model id (default: gemini-2.0-flash-exp or GOOGLE_DEFAULT_MODEL).
        temperature: Sampling temperature.
        max_tokens: Max output tokens.
        system_prompt: Optional system instruction.
    """
    chosen_model = model or GOOGLE_DEFAULT_MODEL
    async with httpx.AsyncClient() as client:
        try:
            result = await _call_google(
                client, prompt, chosen_model, temperature, max_tokens, system_prompt
            )
            return {"provider": "google", "model": chosen_model, **result}
        except Exception as e:
            return {
                "provider": "google",
                "model": chosen_model,
                "error": f"{type(e).__name__}: {e}",
            }


@mcp.tool()
async def fan_out_query(
    prompt: str,
    providers: list[str] | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    system_prompt: str | None = None,
) -> dict[str, Any]:
    """Send the same prompt to multiple providers in parallel.

    Returns a dict keyed by provider with each model's response (or error).
    Use this when you want family-diverse responses to the same question —
    e.g., multi-model adversarial review.

    Args:
        prompt: User message text.
        providers: List of providers to query. Subset of ["openai", "google"].
                   Default: all providers with credentials configured.
        temperature: Sampling temperature applied uniformly.
        max_tokens: Max output tokens applied uniformly.
        system_prompt: Optional system message / instruction.
    """
    available: list[str] = []
    if OPENAI_API_KEY:
        available.append("openai")
    if GOOGLE_API_KEY:
        available.append("google")

    targets = providers or available
    targets = [p for p in targets if p in available]
    if not targets:
        return {
            "error": "no providers available",
            "configured": available,
            "requested": providers,
        }

    async with httpx.AsyncClient() as client:
        tasks = []
        for p in targets:
            if p == "openai":
                tasks.append(
                    _call_openai(
                        client, prompt, OPENAI_DEFAULT_MODEL, temperature, max_tokens, system_prompt
                    )
                )
            elif p == "google":
                tasks.append(
                    _call_google(
                        client, prompt, GOOGLE_DEFAULT_MODEL, temperature, max_tokens, system_prompt
                    )
                )
        results = await asyncio.gather(*tasks, return_exceptions=True)

    out: dict[str, Any] = {"providers_queried": targets, "responses": {}}
    for provider, result in zip(targets, results):
        if isinstance(result, Exception):
            out["responses"][provider] = {
                "error": f"{type(result).__name__}: {result}",
            }
        else:
            out["responses"][provider] = result
    return out


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
