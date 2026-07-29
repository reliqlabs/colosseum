"""Failure-isolated OMP-native adversarial fan-out.

Load this module inside an OMP Python eval cell and inject OMP's ``agent`` and
``parallel`` helpers. The module performs no model calls when imported.
"""
from __future__ import annotations

import hashlib
import fnmatch
import json
import re
import os
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
_PEM_PRIVATE_KEY_RE = re.compile(
    rb"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY(?: BLOCK)?-----")
_ROUTE_HASH_RE = re.compile(r"^sha256:[0-9a-f]{16}$")
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_RESERVED_SUMMARY = {
    "version", "harness", "started_at", "finished_at", "agent", "verdict",
    "voices_ok", "voices_total", "voices", "metadata", "fallback_suppression",
}


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()

def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _file_has_key_marker(path: Path, *, cap: int = 8 * 1024 * 1024) -> bool:
    """True if the file carries a PEM/PGP private-key opening armor line.

    Anchors on the full ``-----BEGIN ... PRIVATE KEY-----`` header (PGP uses
    ``PRIVATE KEY BLOCK``), not a bare ``PRIVATE KEY`` substring. The armored
    header keeps truncated or END-less keys detectable while not flagging source
    that merely names the marker (scanner constants, docs) — such text lacks the
    ``-----BEGIN`` armor prefix. Reads up to ``cap`` bytes; real key files carry
    the header at the top. OSError propagates so an unreadable file is treated as
    suspect, never silently cleared.
    """
    with path.open("rb") as handle:
        head = handle.read(cap)
    return _PEM_PRIVATE_KEY_RE.search(head) is not None


_DERIVED_DIR_NAMES = frozenset({
    ".git", "__pycache__", "node_modules", ".venv", "venv", ".tox",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", ".gradle", ".next",
})


def _is_derived_dir(path: Path) -> bool:
    """Whether this directory is machine-generated rather than authored.

    Two independent signals, neither keyed on a bare directory name being
    "probably a build dir":

    * A small allowlist of unambiguous tool directories (`.git`,
      `node_modules`, virtualenvs, tool caches).
    * `CACHEDIR.TAG`, the cross-tool cache marker Cargo and others write. This
      is what distinguishes a real Cargo `target/` from a REVIEW target that
      merely shares the name: this repo's own `calibration/<run>/target` holds
      the seeded crate a calibration scored and carries no tag, so it stays in
      scope, while `zkdcap/target` carries one and does not.
    """
    if path.name in _DERIVED_DIR_NAMES:
        return True
    return (path / "CACHEDIR.TAG").is_file()

def preflight_scan(root: str | Path,
                   skipped: list[str] | None = None) -> list[str]:
    """Find secret-bearing files or escaping symlinks in the agent-visible tree.

    Derived trees are OUT OF SCOPE and their paths are reported through
    ``skipped`` so the narrowing is auditable, never silent. Rationale: build
    output is reproducible from source, so a secret there is a copy of one that
    is in scope, while compiled artifacts routinely embed the PEM armor as data
    (ed25519_dalek's PKCS#8 doc comment lands in every .rmeta). Scanning them
    produced dozens of false positives on an ordinary Rust project, and a gate
    that always fires is a gate that gets bypassed.
    """
    project = Path(root).resolve()
    violations: list[str] = []
    secret_names = (
        ".env", ".env.*", "*.secret", "secrets.*", "*.pem", "*.p12", "*.pfx",
        "*.key", "*.p8", "*.jks", "*.keystore", ".git-credentials",
        "id_rsa*", "id_dsa*", "id_ecdsa*", "id_ed25519*",
    )
    for current, dirnames, filenames in os.walk(project, followlinks=False):
        here = Path(current)
        pruned = []
        for name in sorted(dirnames):
            child = here / name
            if child.is_symlink():
                target = Path(os.path.realpath(child))
                if not target.is_relative_to(project):
                    violations.append(
                        f"symlink escapes root: {child.relative_to(project)} -> {target}")
                continue  # never descend a symlinked directory
            if _is_derived_dir(child):
                if skipped is not None:
                    skipped.append(str(child.relative_to(project)))
                continue
            pruned.append(name)
        dirnames[:] = pruned

        for name in sorted(filenames):
            path = here / name
            rel = path.relative_to(project)
            if path.is_symlink():
                target = Path(os.path.realpath(path))
                if not target.is_relative_to(project):
                    violations.append(f"symlink escapes root: {rel} -> {target}")
                continue
            if not path.is_file():
                continue
            if any(fnmatch.fnmatch(name, pattern) for pattern in secret_names):
                violations.append(f"secret-named file: {rel}")
                continue
            try:
                if _file_has_key_marker(path):
                    violations.append(f"private-key material: {rel}")
            except OSError:
                violations.append(f"unreadable file (cannot scan for secrets): {rel}")
    return sorted(violations)


def _route_hash(route: Mapping[str, Any]) -> str:
    normalized = {
        "agent": route["agent"],
        "thinking_policy": route["thinking_policy"],
        "voices": sorted(
            ({"id": voice["id"], "model": voice["model"],
              "thinking_level": voice.get("thinking_level")}
             for voice in route["voices"]),
            key=lambda voice: voice["id"],
        ),
    }
    blob = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def _validate_voice(voice: Mapping[str, Any]) -> dict[str, Any]:
    required = ("id", "model", "family", "calibration")
    missing = [key for key in required if not isinstance(voice.get(key), str)
               or not voice[key]]
    if missing:
        raise ValueError(f"OMP voice has missing/invalid fields {missing}: {voice!r}")
    if not _SLUG_RE.fullmatch(voice["id"]):
        raise ValueError(f"unsafe OMP voice id: {voice['id']!r}")
    if "thinking_level" not in voice:
        raise ValueError(f"OMP voice {voice['id']!r} has no thinking_level")
    level = voice["thinking_level"]
    if level is not None and (not isinstance(level, str) or not level):
        raise ValueError(
            f"OMP voice {voice['id']!r} thinking_level must be a non-empty "
            f"string or null, got {level!r}")
    checked: dict[str, Any] = {key: voice[key] for key in required}
    checked["thinking_level"] = level
    # OMP selector grammar is `provider/model:thinkingLevel`, and an explicit
    # selector level outranks the agent wrapper's frontmatter level, so the
    # per-voice effort is what actually runs. A null level dispatches the bare
    # model (the route exposes no ladder).
    checked["dispatch_selector"] = f"{voice['model']}:{level}" if level else voice["model"]
    return checked


def load_omp_native_config(
    config_path: str | Path,
    selected_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Load and validate the generated ``omp_native`` dispatch block."""
    path = Path(config_path)
    config = json.loads(path.read_text())
    for key in ("project_root", "target_spec"):
        if not isinstance(config.get(key), str) or not config[key]:
            raise ValueError(f"{path}: {key} must be a non-empty string")
    route = config.get("omp_native")
    if not isinstance(route, dict):
        raise ValueError(f"{path}: missing omp_native object")
    for key in ("profile", "agent", "thinking_policy", "calibration", "route_hash"):
        if not isinstance(route.get(key), str) or not route[key]:
            raise ValueError(f"{path}: omp_native.{key} must be a non-empty string")
    if not _ROUTE_HASH_RE.fullmatch(route["route_hash"]):
        raise ValueError(f"{path}: invalid omp_native.route_hash")
    if not isinstance(route.get("voices"), list) or not route["voices"]:
        raise ValueError(f"{path}: omp_native.voices must be a non-empty list")

    voices = [_validate_voice(voice) for voice in route["voices"]]
    by_id: dict[str, dict[str, str]] = {}
    for voice in voices:
        if voice["id"] in by_id:
            raise ValueError(f"{path}: duplicate OMP voice id {voice['id']!r}")
        by_id[voice["id"]] = voice
    canonical_route = {**route, "voices": voices}
    expected_hash = _route_hash(canonical_route)
    if route["route_hash"] != expected_hash:
        raise ValueError(
            f"{path}: OMP route hash drift: stored={route['route_hash']} "
            f"recomputed={expected_hash}")

    if selected_ids is not None:
        if not selected_ids:
            raise ValueError("selected_ids must not be empty")
        if len(set(selected_ids)) != len(selected_ids):
            raise ValueError("selected_ids contains duplicates")
        unknown = [voice_id for voice_id in selected_ids if voice_id not in by_id]
        if unknown:
            raise ValueError(f"OMP-native routes not registered for: {unknown}")
        voices = [by_id[voice_id] for voice_id in selected_ids]

    return {
        "project_root": config["project_root"],
        "target_spec": config["target_spec"],
        "profile": route["profile"],
        "agent": route["agent"],
        "thinking_policy": route["thinking_policy"],
        "calibration": route["calibration"],
        "route_hash": route["route_hash"],
        "voices": voices,
    }


_THINKING_LEVELS = frozenset({
    "off", "minimal", "low", "medium", "high", "xhigh", "max", "auto",
})


def _base_selector(selector: str) -> str:
    """`provider/id` with a trailing `:thinkingLevel` stripped, if present.

    Only a final segment that is a known level is removed: a model id may
    legitimately contain a colon (synthetic's `hf:zai-org/GLM-5.2`), so a naive
    split would mangle the id and make every comparison look like a fallback.
    """
    head, sep, tail = selector.rpartition(":")
    return head if sep and tail in _THINKING_LEVELS else selector


def fallback_suppression_overlay(
    voices: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, dict[str, list[object]]]]:
    """Exact process-local OMP overlay that disables tested routes' fallbacks.

    OMP gives an exact ``provider/model`` fallback-chain key precedence over
    wildcard and role keys, and replaces that key's array in a config overlay.
    An empty array therefore prevents retry fallback for that model without
    changing any other process's settings or any unrelated chain. Two voices
    cannot share a base selector: a certificate could not then distinguish their
    route evidence, so reject rather than silently widening its scope.
    """
    checked = [_validate_voice(voice) for voice in voices]
    if not checked:
        raise ValueError("fallback suppression requires at least one voice")
    selectors = [_base_selector(voice["dispatch_selector"]) for voice in checked]
    if len(set(selectors)) != len(selectors):
        raise ValueError("fallback suppression voices share a base selector")
    return {
        "retry": {
            "fallbackChains": {selector: [] for selector in sorted(selectors)},
        },
    }


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot read {label}: {path}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{label} must contain a JSON object: {path}")
    return data


def load_fallback_suppression(
    voices: Sequence[Mapping[str, Any]],
    overlay_path: str | Path | None = None,
    precheck_path: str | Path | None = None,
) -> dict[str, Any]:
    """Verify the launcher certificate for this process-local fallback overlay.

    The OMP eval sandbox cannot inspect its parent settings. This validates the
    generated overlay and the pre-launch ``omp --config … config get`` artifact,
    then records the resulting precondition honestly as
    ``prechecked-suppression``. It does not claim a runtime settings RPC exists.
    """
    overlay_arg = overlay_path or os.environ.get("COLOSSEUM_OMP_FALLBACK_OVERLAY")
    precheck_arg = precheck_path or os.environ.get("COLOSSEUM_OMP_FALLBACK_PRECHECK")
    if not isinstance(overlay_arg, (str, Path)) or not str(overlay_arg):
        raise ValueError("fallback suppression overlay path is required")
    if not isinstance(precheck_arg, (str, Path)) or not str(precheck_arg):
        raise ValueError("fallback suppression precheck path is required")
    overlay = Path(overlay_arg).resolve()
    precheck = Path(precheck_arg).resolve()
    expected = fallback_suppression_overlay(voices)
    if _load_json_object(overlay, "fallback suppression overlay") != expected:
        raise ValueError("fallback suppression overlay does not exactly match selected voices")
    overlay_hash = _sha256_file(overlay)
    evidence = _load_json_object(precheck, "fallback suppression precheck")
    if evidence.get("overlay_sha256") != overlay_hash:
        raise ValueError("fallback suppression precheck is not bound to the overlay")
    effective = evidence.get("effective_fallback_chains")
    expected_chains = expected["retry"]["fallbackChains"]
    if not isinstance(effective, Mapping) or any(
        effective.get(selector) != [] for selector in expected_chains
    ):
        raise ValueError("fallback suppression precheck leaves a tested route eligible")
    command = evidence.get("command")
    environment = evidence.get("environment")
    if not isinstance(command, list) or not all(isinstance(arg, str) for arg in command):
        raise ValueError("fallback suppression precheck command is malformed")
    if not isinstance(evidence.get("cwd"), str) or not evidence["cwd"]:
        raise ValueError("fallback suppression precheck cwd is malformed")
    overlay_sources = environment.get("PI_CONFIG_FILES") if isinstance(environment, Mapping) else None
    if not isinstance(overlay_sources, str):
        raise ValueError("fallback suppression precheck lacks PI_CONFIG_FILES")
    configured_paths = {
        Path(source).resolve() for source in overlay_sources.split(os.pathsep) if source
    }
    if overlay not in configured_paths or command[-3:] != [
        "config", "get", "retry.fallbackChains",
    ]:
        raise ValueError("fallback suppression precheck did not query the expected overlay")
    return {
        "status": "prechecked-suppression",
        "overlay_file": str(overlay),
        "overlay_sha256": overlay_hash,
        "precheck_file": str(precheck),
        "precheck_sha256": _sha256_file(precheck),
        "suppressed_selectors": sorted(expected_chains),
        "note": (
            "OMP `config get`, run with the same PI_CONFIG_FILES overlay also "
            "passed to the launch, shows zero retry fallback candidates for every "
            "selected route. This is a pre-launch configuration certificate, not "
            "provider-served-route attestation."
        ),
    }


def _validate_fallback_suppression(
    suppression: Mapping[str, Any] | None,
    voices: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    if suppression is None:
        return None
    if not isinstance(suppression, Mapping):
        raise ValueError("fallback_suppression must be a mapping or null")
    if suppression.get("status") != "prechecked-suppression":
        raise ValueError("fallback_suppression must be a prechecked certificate")
    expected = set(fallback_suppression_overlay(voices)["retry"]["fallbackChains"])
    selectors = suppression.get("suppressed_selectors")
    if (not isinstance(selectors, list) or not all(isinstance(value, str) for value in selectors)
            or set(selectors) != expected or len(selectors) != len(expected)):
        raise ValueError("fallback_suppression selectors do not exactly match selected voices")
    for key in ("overlay_file", "precheck_file"):
        if not isinstance(suppression.get(key), str) or not suppression[key]:
            raise ValueError(f"fallback_suppression.{key} must be a non-empty string")
    for key in ("overlay_sha256", "precheck_sha256"):
        if not isinstance(suppression.get(key), str) or not _SHA256_RE.fullmatch(suppression[key]):
            raise ValueError(f"fallback_suppression.{key} must be a sha256 digest")
    if not isinstance(suppression.get("note"), str) or not suppression["note"]:
        raise ValueError("fallback_suppression.note must be a non-empty string")
    return dict(suppression)


def _nested_get(result: Mapping[str, Any], key: str) -> Any:
    """Read `key` from the result, or from its `details` object.

    The eval `agent()` bridge nests dispatch metadata under `details`; some
    runtimes flatten it onto the result. Check both rather than assume one.
    """
    if key in result:
        return result[key]
    details = result.get("details")
    if isinstance(details, Mapping):
        return details.get(key)
    return None


def _served_model(result: Any) -> str | None:
    """The model OMP actually dispatched, as the bridge reports it."""
    if not isinstance(result, Mapping):
        return None
    model = _nested_get(result, "model")
    if isinstance(model, str) and model:
        return model
    if isinstance(model, list) and model and isinstance(model[0], str):
        return model[0]
    return None


def _reported_fallback(result: Any) -> bool | None:
    """OMP's own `resolvedModelIsFallback`, when the bridge forwards it.

    The eval bridge currently drops this field (it forwards only `model`), so
    this is usually None and the caller must fall back to comparing selectors.
    Preferred whenever present because it is authoritative.
    """
    if not isinstance(result, Mapping):
        return None
    flag = _nested_get(result, "resolvedModelIsFallback")
    return flag if isinstance(flag, bool) else None


def classify_served_route(
    requested: str,
    result: Any,
    *,
    suppressed_selectors: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """Decide whether a retry fallback served this dispatch, and on what basis.

    OMP rewrites `resolvedModel` to the fallback when one is applied, so a
    served model differing from the requested one is positive evidence. The
    converse is not clean unless a validated, process-local configuration
    certificate disabled that exact route's fallback chain. The basis is
    recorded so evidence never presents an inference as a fact.
    """
    served = _served_model(result)
    reported = _reported_fallback(result)
    if reported is not None:
        return {"served_model": served, "served_is_fallback": reported,
                "fallback_basis": "omp-reported"}
    if served is None:
        return {"served_model": None, "served_is_fallback": None,
                "fallback_basis": "unavailable: bridge reported no model"}
    requested_base = _base_selector(requested)
    if _base_selector(served) != requested_base:
        return {"served_model": served, "served_is_fallback": True,
                "fallback_basis": "inferred: served model differs from requested"}
    if requested_base in suppressed_selectors:
        return {
            "served_model": served,
            "served_is_fallback": False,
            "fallback_basis": (
                "configured-suppression: prechecked empty retry fallback chain "
                "for this exact route"
            ),
        }
    return {"served_model": served, "served_is_fallback": False,
            "fallback_basis": ("inferred-ambiguous: served == requested, which "
                               "means either no fallback or an absent "
                               "resolvedModel echoing the override")}


def _route_established(record: Mapping[str, Any]) -> bool:
    """Whether the record POSITIVELY establishes which route answered.

    An OMP provenance report is authoritative. Otherwise, a differing served
    model establishes a fallback, and a matching model is established only when
    this run carries a validated configuration certificate that suppressed its
    exact retry chain. Other equal-selector matches remain ambiguous.
    """
    basis = record.get("fallback_basis")
    if not isinstance(basis, str):
        return False
    return (basis == "omp-reported" or basis.startswith("inferred:")
            or basis.startswith("configured-suppression:"))


def _unwrap_lone_string(data: Any) -> str:
    """A structured result's payload, unwrapped when it is one string.

    A subagent that yields structured output arrives here as a Mapping. Naively
    serializing it writes the model's prose to disk as an ESCAPED JSON string
    value, so the raw evidence file is a transport envelope rather than the
    voice's own text -- observed in calibration/2026-07-28-r3, where three of
    four voices' compliant fenced findings blocks were escaped inside
    ``{"findings_json": "..."}`` and the first scoring pass read them as
    unparseable. Only a single-string payload is unwrapped: with two or more
    fields there is no basis for choosing, and guessing would silently drop
    evidence.
    """
    if isinstance(data, str):
        return data
    if isinstance(data, Mapping) and len(data) == 1:
        (only,) = data.values()
        if isinstance(only, str):
            return only
    return json.dumps(data, indent=2, ensure_ascii=False)


def _result_text(result: Any) -> tuple[str, str | None, str | None]:
    if isinstance(result, str):
        return result, None, None
    if result is None:
        raise RuntimeError("agent returned no result")
    if not isinstance(result, Mapping):
        return json.dumps(result, indent=2, ensure_ascii=False), None, None

    text = result.get("text")
    if not isinstance(text, str):
        output = result.get("output")
        if isinstance(output, str):
            text = output
        else:
            data = result.get("data", output)
            if data is not None:
                text = _unwrap_lone_string(data)
            elif result.get("error"):
                raise RuntimeError(str(result["error"]))
            else:
                text = ""
    handle = result.get("handle") if isinstance(result.get("handle"), str) else None
    agent_id = result.get("id") if isinstance(result.get("id"), str) else None
    return text, handle, agent_id


def resolve_omp_session_cwd(session_file: str | Path | None = None) -> str | None:
    """Absolute cwd of the OMP session, from the documented session-header contract.

    Reads ``PI_SESSION_FILE`` (host-injected by the OMP notebook runtime;
    ``omp://notebook-tool-runtime.md``) and returns the ``cwd`` of the first
    ``type: "session"`` header entry (``omp://session.md`` file-format contract:
    a valid header has ``type == "session"`` and a string ``id``). The header is
    not guaranteed to be physically line 1 (a ``title`` pad-record may precede
    it), so the leading entries are scanned. Returns ``None`` when the file is
    absent, unreadable, carries no valid header, or the header lacks an absolute
    ``cwd``. Callers MUST treat ``None`` as refusal, never as "unconstrained is
    acceptable".
    """
    raw = session_file if session_file is not None else os.environ.get("PI_SESSION_FILE")
    if not raw:
        return None
    try:
        with Path(raw).open("r", encoding="utf-8") as handle:
            for _ in range(256):  # header sits near the top; bound the scan
                line = handle.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if isinstance(entry, dict) and entry.get("type") == "session":
                    ident, cwd = entry.get("id"), entry.get("cwd")
                    if (isinstance(ident, str) and ident
                            and isinstance(cwd, str) and os.path.isabs(cwd)):
                        return cwd
                    return None
    except OSError:
        return None
    return None


def run_omp_fanout(
    *,
    agent_fn: Callable[..., Any],
    parallel_fn: Callable[[Sequence[Callable[[], Any]]], Sequence[Any]],
    voices: Sequence[Mapping[str, Any]],
    project_root: str | Path,
    target_spec: str | Path,
    run_dir: str | Path,
    prompt: str | None = None,
    prompt_by_voice: Mapping[str, str] | None = None,
    agent_name: str = "colosseum-spec-adversary",
    schema: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
    fallback_suppression: Mapping[str, Any] | None = None,
    allow_unverified_isolation: bool = False,
) -> dict[str, Any]:
    """Run one OMP subagent per voice and persist each outcome independently.

    Exactly one of ``prompt`` and ``prompt_by_voice`` is required. Exceptions
    from one model call become per-voice error records; they never reject the
    parallel wave or discard reports from other voices. ``fallback_suppression``
    may carry a certificate from ``load_fallback_suppression``. It establishes
    an equal-selector result only by proving a process-local, empty fallback
    chain was prechecked before the parent OMP process launched.
    The project tree is scanned before dispatch. ``target_spec`` and ``run_dir``
    must resolve inside ``project_root``; runs live under
    ``.colosseum/attacks`` and never overwrite an existing directory.
    Native dispatch refuses unless the caller opts in with
    ``allow_unverified_isolation=True`` AND the OMP session (per the
    ``PI_SESSION_FILE`` header cwd) is rooted at ``project_root``. Isolation is
    stamped ``unverified``: a matching root is a precondition, not a mechanical
    guarantee that the subagent filesystem is confined.
    """
    if (prompt is None) == (prompt_by_voice is None):
        raise ValueError("provide exactly one of prompt or prompt_by_voice")
    if not isinstance(agent_name, str) or not agent_name:
        raise ValueError("agent_name must be a non-empty string")
    if metadata is not None and any(key in _RESERVED_SUMMARY for key in metadata):
        raise ValueError("metadata contains a reserved summary key")

    checked_voices = [_validate_voice(voice) for voice in voices]
    if not checked_voices:
        raise ValueError("voices must not be empty")
    suppression = _validate_fallback_suppression(fallback_suppression, checked_voices)
    suppressed_selectors = frozenset(
        suppression["suppressed_selectors"] if suppression is not None else ()
    )
    ids = [voice["id"] for voice in checked_voices]
    if len(set(ids)) != len(ids):
        raise ValueError("voices contains duplicate ids")
    if prompt_by_voice is not None:
        missing_prompts = [voice_id for voice_id in ids
                           if not isinstance(prompt_by_voice.get(voice_id), str)
                           or not prompt_by_voice[voice_id]]
        if missing_prompts:
            raise ValueError(f"missing prompt text for voices: {missing_prompts}")
    elif not isinstance(prompt, str) or not prompt:
        raise ValueError("prompt must be a non-empty string")

    project = Path(project_root).resolve()
    if not project.is_dir():
        raise ValueError(f"project_root is not a directory: {project}")
    if not allow_unverified_isolation:
        raise ValueError(
            "OMP-native filesystem isolation is unverified; pass "
            "allow_unverified_isolation=True to acknowledge (see the SKILL "
            "isolation note). This flag never claims the subagent tree is confined.")
    session_cwd = resolve_omp_session_cwd()
    if session_cwd is None:
        raise RuntimeError(
            "cannot confirm the OMP session root from PI_SESSION_FILE (missing, "
            "unreadable, or no valid session header); refusing native dispatch")
    if Path(session_cwd).resolve() != project:
        raise RuntimeError(
            f"OMP session is rooted at {session_cwd}, not project_root {project}; "
            "start OMP inside project_root before native dispatch")
    isolation = {
        "status": "unverified",
        "session_root": str(Path(session_cwd).resolve()),
        "session_root_source": "PI_SESSION_FILE session-header cwd",
        "note": ("session confirmed rooted at project_root; subagent filesystem "
                 "access is NOT confined and isolation is not mechanically verified"),
    }

    target = Path(target_spec)
    if not target.is_absolute():
        target = project / target
    target = target.resolve()
    if not target.is_relative_to(project) or not target.is_file():
        raise ValueError(f"target_spec must be a file inside project_root: {target}")

    attacks_root = (project / ".colosseum" / "attacks").resolve()
    destination = Path(run_dir)
    if not destination.is_absolute():
        destination = project / destination
    destination = destination.resolve()
    if not destination.is_relative_to(attacks_root):
        raise ValueError(f"run_dir must be inside {attacks_root}")
    destination.mkdir(parents=True, exist_ok=False)

    skipped_dirs: list[str] = []
    violations = preflight_scan(project, skipped_dirs)
    preflight = {
        "status": "blocked" if violations else "ok",
        "project_root": str(project),
        "target_spec": str(target.relative_to(project)),
        "target_spec_sha256": _sha256_file(target),
        "violations": violations,
        # What the scan did NOT read. Recorded so a clean preflight states its
        # scope instead of implying the whole tree was examined.
        "scan_skipped_dirs": sorted(skipped_dirs),
    }
    (destination / "preflight.json").write_text(
        json.dumps(preflight, indent=2, ensure_ascii=False) + "\n")
    if violations:
        raise RuntimeError(
            f"preflight blocked OMP-native dispatch ({len(violations)} violation(s)); "
            f"see {destination / 'preflight.json'}")

    prompt_dir = destination / "prompts"
    raw_dir = destination / "raw"
    prompt_dir.mkdir()
    raw_dir.mkdir()

    started_at = _iso_now()
    run_meta = {
        "version": 1,
        "harness": "omp-native",
        "started_at": started_at,
        "agent": agent_name,
        "preflight": preflight,
        "metadata": dict(metadata or {}),
        "isolation": isolation,
        "fallback_suppression": suppression,
        "voices": checked_voices,
    }
    (destination / "meta.json").write_text(
        json.dumps(run_meta, indent=2, ensure_ascii=False) + "\n")

    def invoke(voice: dict[str, str]) -> dict[str, Any]:
        voice_id = voice["id"]
        voice_prompt = (prompt_by_voice[voice_id]
                        if prompt_by_voice is not None else prompt)
        assert isinstance(voice_prompt, str)
        prompt_rel = Path("prompts") / f"{voice_id}.md"
        raw_rel = Path("raw") / f"omp-{voice_id}.md"
        started = time.monotonic()
        base = {
            **voice,
            "prompt_file": str(prompt_rel),
            "prompt_sha256": _sha256_text(voice_prompt),
            "finish_reason": None,
            "requested_selector": voice["dispatch_selector"],
        }
        options: dict[str, Any] = {
            "agent": agent_name,
            "model": voice["dispatch_selector"],
            "label": f"omp-{voice_id}",
            "handle": True,
        }
        if schema is not None:
            options["schema"] = dict(schema)
        try:
            (destination / prompt_rel).write_text(voice_prompt)
            result = agent_fn(voice_prompt, **options)
            text, handle, agent_id = _result_text(result)
            if not text.strip():
                raise RuntimeError("agent returned empty output")
            (destination / raw_rel).write_text(text)
            elapsed = time.monotonic() - started
            record = {
                **base,
                "status": "ok",
                "elapsed_s": round(elapsed, 6),
                "output_file": str(raw_rel),
                "output_sha256": _sha256_text(text),
                "output_bytes": len(text.encode()),
                "handle": handle,
                "agent_id": agent_id,
                # Which route ANSWERED, not merely which was requested: OMP's
                # retry layer may serve a dispatch from a configured fallback
                # (retry.fallbackChains), and evidence that names only the
                # requested model would misattribute the provider.
                **classify_served_route(
                    voice["dispatch_selector"],
                    result,
                    suppressed_selectors=suppressed_selectors,
                ),
            }
            return record
        except Exception as exc:  # one voice must never sink the fan-out wave
            elapsed = time.monotonic() - started
            error_text = f"{type(exc).__name__}: {exc}"
            error_rel = Path("raw") / f"omp-{voice_id}.error.txt"
            (destination / error_rel).write_text(error_text)
            return {
                **base,
                "status": "error",
                "elapsed_s": round(elapsed, 6),
                "output_file": str(error_rel),
                "output_sha256": _sha256_text(error_text),
                "output_bytes": len(error_text.encode()),
                "handle": None,
                "agent_id": None,
                "error": error_text,
            }

    def _write_summary(records: Sequence[Any],
                       orchestration_error: str | None = None) -> dict[str, Any]:
        voices_ok = sum(1 for record in records
                        if isinstance(record, Mapping) and record.get("status") == "ok")
        try:
            target_hash_after = _sha256_file(target)
        except OSError:
            target_hash_after = None
        target_stable = target_hash_after == preflight["target_spec_sha256"]
        if orchestration_error is not None or not target_stable:
            verdict = "INCOMPLETE"
        elif voices_ok == len(checked_voices):
            verdict = "COMPLETE"
        else:
            verdict = "PARTIAL" if voices_ok else "INCOMPLETE"
        # Route provenance at a glance: an evidence reader must not have to
        # diff per-voice selectors to learn which route answered. The two lists
        # partition the OK voices by whether the served route is POSITIVELY
        # established -- an ambiguous equal-selector match is unverified, not
        # clean, so the summary never reads better than the per-voice basis.
        served_by_fallback = sorted(
            record["id"] for record in records
            if isinstance(record, Mapping) and record.get("served_is_fallback") is True)
        route_unverified = sorted(
            record["id"] for record in records
            if isinstance(record, Mapping) and record.get("status") == "ok"
            and not _route_established(record))
        summary = {
            "version": 1,
            "harness": "omp-native",
            "started_at": started_at,
            "finished_at": _iso_now(),
            "agent": agent_name,
            "verdict": verdict,
            "voices_ok": voices_ok,
            "voices_total": len(checked_voices),
            "metadata": dict(metadata or {}),
            "target_spec_sha256_after": target_hash_after,
            "target_spec_stable": target_stable,
            "preflight": preflight,
            "voices": list(records),
            "isolation": isolation,
            "fallback_suppression": suppression,
            "served_by_fallback": served_by_fallback,
            "route_unverified": route_unverified,
        }
        if orchestration_error is not None:
            summary["orchestration_error"] = orchestration_error
        (destination / "summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
        return summary

    thunks = [(lambda voice=voice: invoke(voice)) for voice in checked_voices]
    try:
        records = list(parallel_fn(thunks))
    except Exception as exc:  # the wave itself failed; keep partial evidence auditable
        _write_summary([], orchestration_error=f"{type(exc).__name__}: {exc}")
        raise
    if len(records) != len(checked_voices):
        message = (f"parallel_fn returned {len(records)} results for "
                   f"{len(checked_voices)} voices")
        _write_summary([r for r in records if isinstance(r, Mapping)],
                       orchestration_error=message)
        raise RuntimeError(message)
    return _write_summary(records)
