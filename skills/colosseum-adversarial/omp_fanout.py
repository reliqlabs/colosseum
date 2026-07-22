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
_RESERVED_SUMMARY = {
    "version", "harness", "started_at", "finished_at", "agent", "verdict",
    "voices_ok", "voices_total", "voices", "metadata",
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


def preflight_scan(root: str | Path) -> list[str]:
    """Find secret-bearing files or escaping symlinks in the agent-visible tree."""
    project = Path(root).resolve()
    violations: list[str] = []
    secret_names = (
        ".env", ".env.*", "*.secret", "secrets.*", "*.pem", "*.p12", "*.pfx",
        "*.key", "*.p8", "*.jks", "*.keystore", ".git-credentials",
        "id_rsa*", "id_dsa*", "id_ecdsa*", "id_ed25519*",
    )
    for path in sorted(project.rglob("*")):
        rel = path.relative_to(project)
        if rel.parts and rel.parts[0] == ".git":
            continue
        if "__pycache__" in rel.parts:
            continue
        if path.is_symlink():
            target = Path(os.path.realpath(path))
            if not target.is_relative_to(project):
                violations.append(f"symlink escapes root: {rel} -> {target}")
            continue
        if not path.is_file():
            continue
        if any(fnmatch.fnmatch(path.name, pattern) for pattern in secret_names):
            violations.append(f"secret-named file: {rel}")
            continue
        try:
            if _file_has_key_marker(path):
                violations.append(f"private-key material: {rel}")
        except OSError:
            violations.append(f"unreadable file (cannot scan for secrets): {rel}")
    return violations


def _route_hash(route: Mapping[str, Any]) -> str:
    normalized = {
        "agent": route["agent"],
        "thinking_level": route["thinking_level"],
        "voices": sorted(
            ({"id": voice["id"], "model": voice["model"]}
             for voice in route["voices"]),
            key=lambda voice: voice["id"],
        ),
    }
    blob = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def _validate_voice(voice: Mapping[str, Any]) -> dict[str, str]:
    required = ("id", "model", "family", "calibration")
    missing = [key for key in required if not isinstance(voice.get(key), str)
               or not voice[key]]
    if missing:
        raise ValueError(f"OMP voice has missing/invalid fields {missing}: {voice!r}")
    if not _SLUG_RE.fullmatch(voice["id"]):
        raise ValueError(f"unsafe OMP voice id: {voice['id']!r}")
    return {key: voice[key] for key in required}


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
    for key in ("profile", "agent", "thinking_level", "calibration", "route_hash"):
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
        "thinking_level": route["thinking_level"],
        "calibration": route["calibration"],
        "route_hash": route["route_hash"],
        "voices": voices,
    }


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
                text = json.dumps(data, indent=2, ensure_ascii=False)
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
    allow_unverified_isolation: bool = False,
) -> dict[str, Any]:
    """Run one OMP subagent per voice and persist each outcome independently.

    Exactly one of ``prompt`` and ``prompt_by_voice`` is required. Exceptions
    from one model call become per-voice error records; they never reject the
    parallel wave or discard reports from other voices.
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

    violations = preflight_scan(project)
    preflight = {
        "status": "blocked" if violations else "ok",
        "project_root": str(project),
        "target_spec": str(target.relative_to(project)),
        "target_spec_sha256": _sha256_file(target),
        "violations": violations,
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
        }
        options: dict[str, Any] = {
            "agent": agent_name,
            "model": voice["model"],
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
