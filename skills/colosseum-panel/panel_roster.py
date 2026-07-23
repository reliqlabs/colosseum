"""Stdlib roster loader for the colosseum-panel skill: DIAGNOSTICS / TESTS ONLY.

Reads ``.colosseum/panel-profiles.json`` and freezes a roster for a named
profile. It takes the first candidate for each seat and checks only
``declared_family`` labels; it does NOT verify model availability and cannot see
OMP's opaque ``ctx.models.family`` lineage. It therefore MUST NOT resolve a
roster for real panel execution: a profile whose declared-distinct seats resolve
to the same underlying model family, or name an unavailable model, would pass
here and silently run a degenerate panel.

The authoritative path is the ``colosseum-panel-resolver`` OMP extension: it
picks the first AVAILABLE candidate and enforces distinct model families via
``ctx.models.family`` (opaque, never persisted). Panel execution requires it and
fails closed when it is absent. Both produce the same roster shape consumed by
``omp_panel.run_panel``; this loader exists for offline diagnostics and the test
suite (``normalize_roster`` decodes the extension's ToolResult).
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def _provider_of(selector: str) -> str:
    if not selector or selector.startswith("@"):
        return ""
    return selector.split("/", 1)[0] if "/" in selector else ""


def _seat_from(entry: dict[str, Any], *, where: str) -> dict[str, Any]:
    candidates = entry.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError(f"{where}: seat {entry.get('seat_id')!r} has no candidates")
    selector = candidates[0]
    if not isinstance(selector, str) or not selector:
        raise ValueError(f"{where}: seat {entry.get('seat_id')!r} has an invalid candidate")
    for key in ("seat_id", "declared_family"):
        if not isinstance(entry.get(key), str) or not entry[key]:
            raise ValueError(f"{where}: seat missing {key}")
    return {
        "seat_id": entry["seat_id"],
        "declared_family": entry["declared_family"],
        "requested_selector": selector,
        "resolved_model": selector,
        "resolved_provider": _provider_of(selector),
        "thinking_level": str(entry.get("thinking_level", "")),
        "calibration": str(entry.get("calibration", "pending")),
    }


def resolve_roster(profile_path: str | Path, profile_name: str) -> dict[str, Any]:
    """Freeze a roster for ``profile_name`` from the profiles JSON file.

    Returns ``{profile, mode, min_families, seats, synthesizer}``. Raises when the
    profile is missing, malformed, or declares fewer than ``min_families`` distinct
    seat families.
    """
    data = json.loads(Path(profile_path).read_text())
    profiles = data.get("profiles")
    if not isinstance(profiles, dict) or profile_name not in profiles:
        raise ValueError(f"profile {profile_name!r} not found in {profile_path}")
    prof = profiles[profile_name]
    mode = prof.get("mode")
    if mode not in ("project-plan", "milestone-review"):
        raise ValueError(f"profile {profile_name!r} has invalid mode {mode!r}")
    seat_entries = prof.get("seats")
    if not isinstance(seat_entries, list) or len(seat_entries) < 2:
        raise ValueError(f"profile {profile_name!r} needs at least two seats")
    seats = [_seat_from(e, where=f"{profile_name}.seats") for e in seat_entries]
    ids = [s["seat_id"] for s in seats]
    if len(set(ids)) != len(ids):
        raise ValueError(f"profile {profile_name!r} has duplicate seat_id")
    min_families = int(prof.get("min_families", 3))
    families = {s["declared_family"] for s in seats}
    if len(families) < min_families:
        raise ValueError(
            f"profile {profile_name!r} declares {len(families)} families "
            f"({sorted(families)}); min_families={min_families}")
    synth_entry = prof.get("synthesizer")
    if not isinstance(synth_entry, dict):
        raise ValueError(f"profile {profile_name!r} has no synthesizer")
    synthesizer = _seat_from(synth_entry, where=f"{profile_name}.synthesizer")
    return {
        "profile": profile_name,
        "mode": mode,
        "min_families": min_families,
        "seats": seats,
        "synthesizer": synthesizer,
    }


def _is_roster(obj: Any) -> bool:
    return (isinstance(obj, Mapping) and isinstance(obj.get("seats"), list)
            and isinstance(obj.get("synthesizer"), Mapping))


def normalize_roster(result: Any) -> dict[str, Any]:
    """Coerce the colosseum_panel_resolve tool result into a roster dict.

    The eval ``tool.<name>`` proxy's return shape for a custom tool is not
    guaranteed, so accept any of: the roster directly; an OMP ToolResult wrapper
    ``{"details": roster}``, ``{"text": "<json>"}`` (observed live, 2026-07-24),
    or ``{"content": [{"text": "<json>"}, ...]}``; or a JSON string. Validates
    the result carries ``seats`` + ``synthesizer`` and
    raises ValueError otherwise; the SKILL propagates that (fail-closed) rather
    than downgrading to this diagnostics-only loader.
    """
    if isinstance(result, str):
        result = json.loads(result)
    if _is_roster(result):
        return dict(result)
    if isinstance(result, Mapping):
        details = result.get("details")
        if _is_roster(details):
            return dict(details)
        text = result.get("text")
        if isinstance(text, str):
            try:
                parsed = json.loads(text)
            except (json.JSONDecodeError, ValueError):
                parsed = None
            if _is_roster(parsed):
                return dict(parsed)
        content = result.get("content")
        if isinstance(content, list):
            for item in content:
                if isinstance(item, Mapping) and isinstance(item.get("text"), str):
                    try:
                        parsed = json.loads(item["text"])
                    except (json.JSONDecodeError, ValueError):
                        continue
                    if _is_roster(parsed):
                        return dict(parsed)
    raise ValueError("resolver result does not contain a roster (seats + synthesizer)")
