#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "mcp>=1.2.0",
#     "httpx>=0.27.0",
#     "python-dotenv>=1.0.0",
# ]
# ///
"""
external-model-mcp: Route prompts to non-Anthropic frontier providers for
multi-model adversarial work.

Colosseum's "adversarial beats consensus" claim depends on genuine family
diversity — different training data, different RLHF lineage, different
architectural blind spots. This MCP exposes three callable surfaces:

- OpenAI (direct API)
- Google Gemini (direct API)
- An OpenAI-compatible multi-model gateway (URL + key configured via .env)

Any combination of the three can be configured; each tool reports a clear
error if its credentials are missing. Secrets — including the gateway URL —
are loaded from .env / shell env only and are never written into this file.

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
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# Load secrets from .env files (gitignored). Search order:
#   1. $COLOSSEUM_DOTENV (explicit override path)
#   2. CWD/.env (project-local)
#   3. <colosseum repo root>/.env (alongside this MCP)
#   4. ~/.colosseum.env (user-global)
# Existing OS env vars take precedence; nothing in this file is overridden if
# already set in the parent shell.
_dotenv_candidates = [
    os.environ.get("COLOSSEUM_DOTENV"),
    Path.cwd() / ".env",
    Path(__file__).resolve().parents[2] / ".env",  # colosseum repo root
    Path.home() / ".colosseum.env",
]
for _candidate in _dotenv_candidates:
    if _candidate and Path(_candidate).is_file():
        load_dotenv(_candidate, override=False)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_DEFAULT_MODEL = os.environ.get("OPENAI_DEFAULT_MODEL", "gpt-4o")

GOOGLE_API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
GOOGLE_BASE_URL = os.environ.get(
    "GOOGLE_BASE_URL", "https://generativelanguage.googleapis.com/v1beta"
)
GOOGLE_DEFAULT_MODEL = os.environ.get("GOOGLE_DEFAULT_MODEL", "gemini-2.0-flash-exp")

# Multi-model gateway — OpenAI-compatible endpoint that routes to multiple
# upstream providers (Anthropic, Google, etc.) behind one URL. Both the URL
# and the API key are loaded from .env / shell env only; nothing about the
# gateway's identity, slug, or credentials is hardcoded here. If either
# COLOSSEUM_GATEWAY_API_KEY or COLOSSEUM_GATEWAY_BASE_URL is missing, the
# gateway provider is reported as not configured and all gateway tools
# return a clear error.
GATEWAY_API_KEY = os.environ.get("COLOSSEUM_GATEWAY_API_KEY")
GATEWAY_BASE_URL = os.environ.get("COLOSSEUM_GATEWAY_BASE_URL")
GATEWAY_DEFAULT_MODEL = os.environ.get("COLOSSEUM_GATEWAY_DEFAULT_MODEL")

REQUEST_TIMEOUT_S = float(os.environ.get("EXTERNAL_MODEL_TIMEOUT_S", "300"))

mcp = FastMCP("external-model-mcp")


@mcp.tool()
async def check_external_health() -> dict[str, Any]:
    """Report which external providers are configured (key present) and reachable.

    Performs a minimal probe per configured provider. Does not consume
    significant token budget — uses each provider's model-list endpoint.
    """
    out: dict[str, Any] = {
        "openai": {"configured": False},
        "google": {"configured": False},
        "gateway": {"configured": False},
        "ok": False,
    }

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

        gw_configured, gw_err = _gateway_configured()
        if gw_configured:
            out["gateway"]["configured"] = True
            try:
                r = await client.get(
                    f"{GATEWAY_BASE_URL}/models",
                    headers={"Authorization": f"Bearer {GATEWAY_API_KEY}"},
                )
                r.raise_for_status()
                data = r.json()
                ids = [m.get("id") for m in data.get("data", [])][:20]
                out["gateway"]["reachable"] = True
                out["gateway"]["listed_models"] = ids
                if GATEWAY_DEFAULT_MODEL:
                    out["gateway"]["default_model"] = GATEWAY_DEFAULT_MODEL
            except Exception as e:
                out["gateway"]["reachable"] = False
                out["gateway"]["error"] = f"{type(e).__name__}: {e}"
        elif gw_err and "unset" not in gw_err:
            out["gateway"]["error"] = gw_err

    out["ok"] = (
        out["openai"].get("reachable", False)
        or out["google"].get("reachable", False)
        or out["gateway"].get("reachable", False)
    )
    if not OPENAI_API_KEY and not GOOGLE_API_KEY and not GATEWAY_API_KEY:
        out["hint"] = (
            "Set credentials in a .env file or shell environment. See "
            "external-model-mcp/README.md for the env-var contract."
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


def _gateway_configured() -> tuple[bool, str | None]:
    """Return (configured, error_message_if_not). Both URL and key required."""
    if not GATEWAY_API_KEY and not GATEWAY_BASE_URL:
        return False, "gateway not configured (COLOSSEUM_GATEWAY_API_KEY and COLOSSEUM_GATEWAY_BASE_URL unset)"
    if not GATEWAY_API_KEY:
        return False, "gateway URL set but COLOSSEUM_GATEWAY_API_KEY missing"
    if not GATEWAY_BASE_URL:
        return False, "gateway key set but COLOSSEUM_GATEWAY_BASE_URL missing"
    return True, None


async def _call_gateway(
    client: httpx.AsyncClient,
    prompt: str,
    model: str,
    temperature: float,
    max_tokens: int,
    system_prompt: str | None,
) -> dict[str, Any]:
    configured, err = _gateway_configured()
    if not configured:
        return {"error": err}
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    response = await client.post(
        f"{GATEWAY_BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {GATEWAY_API_KEY}"},
        json={
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        timeout=REQUEST_TIMEOUT_S,
    )
    # The gateway returns OpenAI-compatible errors with HTTP 200 in some
    # misconfiguration cases; treat both HTTP errors and body-level errors
    # uniformly. The "ReadableStream is disturbed" gateway-internal bug
    # surfaces as an `error.message` in the JSON body.
    try:
        data = response.json()
    except Exception:
        response.raise_for_status()
        return {"error": "non-JSON response from gateway"}
    if isinstance(data, dict) and "error" in data:
        return {
            "error": data["error"].get("message", "unknown gateway error"),
            "error_type": data["error"].get("type"),
            "error_code": data["error"].get("code"),
        }
    response.raise_for_status()
    return {
        "text": data["choices"][0]["message"]["content"],
        "finish_reason": data["choices"][0].get("finish_reason"),
        "usage": data.get("usage", {}),
        "model_returned": data.get("model"),
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
async def query_gateway(
    prompt: str,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    system_prompt: str | None = None,
) -> dict[str, Any]:
    """Send a single-shot prompt to the configured multi-model gateway.

    Gateway URL and credentials are loaded from .env / shell env only; if
    either is missing, this returns a configuration error. Use
    `check_external_health` to see which models the configured gateway
    currently lists.

    Args:
        prompt: User message text.
        model: Model id. Defaults to COLOSSEUM_GATEWAY_DEFAULT_MODEL if set;
               otherwise the caller MUST supply a model name explicitly.
        temperature: Sampling temperature.
        max_tokens: Max completion tokens.
        system_prompt: Optional system message.
    """
    chosen_model = model or GATEWAY_DEFAULT_MODEL
    if not chosen_model:
        return {
            "provider": "gateway",
            "error": "no model supplied and COLOSSEUM_GATEWAY_DEFAULT_MODEL unset",
        }
    async with httpx.AsyncClient() as client:
        try:
            result = await _call_gateway(
                client, prompt, chosen_model, temperature, max_tokens, system_prompt
            )
            return {"provider": "gateway", "model": chosen_model, **result}
        except Exception as e:
            return {
                "provider": "gateway",
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
        providers: List of providers to query. Subset of
                   ["openai", "google", "gateway"]. Default: all providers
                   with credentials configured.
        temperature: Sampling temperature applied uniformly.
        max_tokens: Max output tokens applied uniformly.
        system_prompt: Optional system message / instruction.
    """
    available: list[str] = []
    if OPENAI_API_KEY:
        available.append("openai")
    if GOOGLE_API_KEY:
        available.append("google")
    gw_configured, _ = _gateway_configured()
    if gw_configured:
        available.append("gateway")

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
            elif p == "gateway":
                gw_model = GATEWAY_DEFAULT_MODEL
                if not gw_model:
                    tasks.append(asyncio.sleep(0, result={
                        "error": "gateway target requested but COLOSSEUM_GATEWAY_DEFAULT_MODEL unset",
                    }))
                else:
                    tasks.append(
                        _call_gateway(
                            client, prompt, gw_model, temperature, max_tokens, system_prompt
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
