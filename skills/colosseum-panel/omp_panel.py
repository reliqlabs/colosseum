"""Failure-isolated OMP-native deliberation panel (drafts -> cross-review -> synthesis).

Load this module inside an OMP Python eval cell and inject OMP's ``agent`` and
``parallel`` helpers plus a ``secure`` module that provides the two
security-critical primitives (``preflight_scan`` and ``resolve_omp_session_cwd``).
The canonical provider of ``secure`` is the colosseum-adversarial skill's
``omp_fanout`` module; this engine never reimplements the secret scanner or the
session-root gate, so there is exactly one copy of that logic per install.

The module performs no model calls when imported. It runs three barriered waves:

  Wave 1  drafts     — every seat works the frozen brief independently, blind to
                       peers. One seat's failure never sinks the wave.
  (quorum barrier)   — enough distinct declared families must have drafted, or the
                       run stops INCOMPLETE before any peer sees another's work.
  Wave 2  reviews    — each seat whose own draft succeeded cross-reviews EVERY
                       successful draft, anonymized (no model/provider identity).
  (coverage barrier) — enough reviews must land, or the run stops INCOMPLETE.
  Wave 3  synthesis  — one synthesizer seat produces the canonical output over all
                       drafts and reviews.

``run_status`` reports orchestration completeness (COMPLETE / PARTIAL /
INCOMPLETE). It is deliberately distinct from any milestone verdict
(PASS / FAIL / CONTESTED), which is a *judgment* the synthesizer records inside
its structured output — panel agreement never manufactures verification evidence.
"""
from __future__ import annotations

import hashlib
import json
import random
import secrets
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import re

_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
_RESERVED_SUMMARY = {
    "version", "harness", "mode", "started_at", "finished_at", "run_status",
    "drafts", "reviews", "synthesis", "quorum", "metadata", "route_hash",
}
_VALID_MODES = ("project-plan", "milestone-review")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _sec(secure: Any, name: str) -> Any:
    """Fetch a security primitive whether ``secure`` is an object or a namespace
    dict (the skill loads omp_fanout via ``exec(read('skill://...'), ns)``)."""
    if isinstance(secure, Mapping):
        return secure.get(name)
    return getattr(secure, name, None)


def _require_secure(secure: Any) -> None:
    for name in ("preflight_scan", "resolve_omp_session_cwd"):
        if not callable(_sec(secure, name)):
            raise ValueError(
                f"secure module must expose callable {name!r}; wire the "
                "colosseum-adversarial omp_fanout module (never a stub)")


def _target_snapshot(project: Path, exclude_rel: str | None) -> dict[str, Any]:
    """Content snapshot of the target SOURCE tree for drift detection.

    Hashes ``git diff HEAD`` (all tracked staged+unstaged changes vs HEAD) plus
    every untracked file's content, EXCLUDING generated Colosseum artifacts so the
    token reflects the source under review, not our own outputs. Excludes the
    whole ``.colosseum/`` tree (evidence, panels, attacks, verify, dispatch,
    scripts) — critically, Gate B evidence records live in ``.colosseum/evidence``
    and bind their ``source_snapshot`` to this token, so hashing them would be
    circular (a record could never match a token that includes itself). A plain
    HEAD+dirty flag is insufficient: a tree that starts dirty stays dirty, and
    same-status in-place edits would go unnoticed — the content hash catches
    both. ``available`` is False outside a git work tree (revision unknown, not
    an error); drift is only enforced when a snapshot is actually known.
    """
    def _git(*args: str) -> tuple[int, str]:
        try:
            p = subprocess.run(["git", "-C", str(project), *args],
                               capture_output=True, text=True, timeout=30)
            return p.returncode, (p.stdout or "")
        except (OSError, subprocess.SubprocessError):
            return 1, ""
    code, head = _git("rev-parse", "HEAD")
    if code != 0:
        return {"available": False, "head": None,
                "snapshot_sha256": None, "dirty": None}
    head = head.strip()
    # Exclude generated Colosseum artifacts (self-reference + noise) and the run
    # dir. `.colosseum/` covers evidence/panels/attacks/verify and our machinery.
    exclude_dirs = [".colosseum"]
    if exclude_rel and not exclude_rel.startswith(".colosseum"):
        exclude_dirs.append(exclude_rel)
    excludes: list[str] = []
    for d in exclude_dirs:
        excludes += [f":(exclude,glob){d}/**", f":(exclude){d}"]
    # --binary --full-index so binary content changes register (plain diff would
    # collapse to "Binary files differ" and miss drift).
    dcode, tracked = _git("diff", "--binary", "--full-index", "--no-color", "HEAD", "--", ".", *excludes)
    ocode, others = _git("ls-files", "-o", "--exclude-standard", "--", ".", *excludes)
    if dcode != 0 or ocode != 0:
        # A failed diff/ls-files after a good rev-parse must not yield a partial
        # hash Gate B could trust; report unavailable so a milestone cannot PASS.
        return {"available": False, "head": head, "snapshot_sha256": None,
                "dirty": None, "error": "git diff/ls-files failed"}
    untracked = sorted(ln for ln in others.splitlines() if ln.strip())
    digest = hashlib.sha256()
    digest.update(head.encode()); digest.update(b"\0")
    digest.update(tracked.encode()); digest.update(b"\0")
    for rel in untracked:
        digest.update(rel.encode()); digest.update(b"\0")
        try:
            digest.update((project / rel).read_bytes())
        except OSError:
            digest.update(b"<unreadable>")
        digest.update(b"\0")
    return {
        "available": True,
        "head": head,
        "snapshot_sha256": "sha256:" + digest.hexdigest(),
        "dirty": bool(tracked.strip()) or bool(untracked),
    }


def _validate_seat(seat: Mapping[str, Any], *, where: str) -> dict[str, Any]:
    """A resolved panel seat as produced by the roster resolver.

    Required stable fields only; the opaque OMP family token is never accepted
    or persisted here (see omp-panel-resolver.ts — it is used in-memory for the
    duplicate-family check and discarded). ``declared_family`` is the stable,
    profile-declared label that IS persisted.
    """
    required = ("seat_id", "declared_family", "resolved_model")
    missing = [k for k in required
               if not isinstance(seat.get(k), str) or not seat[k]]
    if missing:
        raise ValueError(f"{where}: seat missing/invalid fields {missing}: {seat!r}")
    if not _SLUG_RE.fullmatch(seat["seat_id"]):
        raise ValueError(f"{where}: unsafe seat_id: {seat['seat_id']!r}")
    model = seat["resolved_model"]
    level = str(seat.get("thinking_level", ""))
    # Compose one canonical dispatch selector and hash/dispatch exactly that, so
    # the requested thinking level is never silently dropped. OMP model selectors
    # accept provider/model:thinkingLevel (omp://models.md). Only append the level
    # when the model segment does not already carry a ':' suffix.
    if level and ":" not in model.rsplit("/", 1)[-1]:
        dispatch_selector = f"{model}:{level}"
    else:
        dispatch_selector = model
    out = {
        "seat_id": seat["seat_id"],
        "declared_family": seat["declared_family"],
        "resolved_model": model,
        "dispatch_selector": dispatch_selector,
        "requested_selector": str(seat.get("requested_selector", "")),
        "resolved_provider": str(seat.get("resolved_provider", "")),
        "thinking_level": level,
        "calibration": str(seat.get("calibration", "pending")),
    }
    return out


def _route_hash(mode: str, seats: Sequence[Mapping[str, Any]],
                synth: Mapping[str, Any]) -> str:
    """Content-address the frozen roster over stable persisted fields only.

    Excludes OMP's opaque family token so a vocabulary change upstream never
    invalidates historical panel evidence.
    """
    def norm(seat: Mapping[str, Any]) -> dict[str, str]:
        return {
            "seat_id": seat["seat_id"],
            "declared_family": seat["declared_family"],
            "resolved_model": seat["resolved_model"],
            "dispatch_selector": seat.get("dispatch_selector", seat["resolved_model"]),
            "thinking_level": seat.get("thinking_level", ""),
            "calibration": seat.get("calibration", ""),
        }
    normalized = {
        "mode": mode,
        "seats": sorted((norm(s) for s in seats), key=lambda s: s["seat_id"]),
        "synthesizer": norm(synth),
    }
    blob = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def _extract(result: Any) -> tuple[str, Any, str | None, str | None]:
    """(text, data, handle, agent_id) from an OMP agent() result.

    ``data`` is the parsed structured object when the call used a schema; else
    None. Mirrors omp_fanout._result_text but also surfaces structured data.
    """
    if isinstance(result, str):
        return result, None, None, None
    if result is None:
        raise RuntimeError("agent returned no result")
    if not isinstance(result, Mapping):
        return json.dumps(result, indent=2, ensure_ascii=False), None, None, None
    data = result.get("data")
    text = result.get("text")
    if not isinstance(text, str):
        output = result.get("output")
        if isinstance(output, str):
            text = output
        elif data is not None:
            text = json.dumps(data, indent=2, ensure_ascii=False)
        elif result.get("error"):
            raise RuntimeError(str(result["error"]))
        else:
            text = ""
    handle = result.get("handle") if isinstance(result.get("handle"), str) else None
    agent_id = result.get("id") if isinstance(result.get("id"), str) else None
    return text, data, handle, agent_id


def run_panel(
    *,
    agent_fn: Callable[..., Any],
    parallel_fn: Callable[[Sequence[Callable[[], Any]]], Sequence[Any]],
    secure: Any,
    mode: str,
    seats: Sequence[Mapping[str, Any]],
    synthesizer_seat: Mapping[str, Any],
    project_root: str | Path,
    brief_path: str | Path,
    run_dir: str | Path,
    draft_prompt_builder: Callable[[Mapping[str, Any]], str],
    review_prompt_builder: Callable[[Mapping[str, Any], str, Sequence[Mapping[str, Any]]], str],
    synthesis_prompt_builder: Callable[[Sequence[Mapping[str, Any]], Sequence[Mapping[str, Any]]], str],
    panelist_agent: str = "colosseum-panelist",
    synthesizer_agent: str = "colosseum-panel-synthesizer",
    draft_schema: Mapping[str, Any] | None = None,
    review_schema: Mapping[str, Any] | None = None,
    synthesis_schema: Mapping[str, Any] | None = None,
    min_families: int = 3,
    metadata: Mapping[str, Any] | None = None,
    required_criteria: Sequence[str] | None = None,
    evidence_gate: Callable[[str, str], Mapping[str, Any]] | None = None,
    verdict_guard_factory: Callable[[Mapping[str, str]], Callable[[Any], Mapping[str, Any]]] | None = None,
    allow_unverified_isolation: bool = False,
) -> dict[str, Any]:
    """Run a three-wave deliberation panel and persist every phase.

    Failure isolation: one seat's raised exception becomes a per-seat error
    record; it never rejects a wave or discards peers. The project tree is
    scanned before any model call; ``brief_path`` and ``run_dir`` must resolve
    inside ``project_root``; runs live under ``.colosseum/panels`` and never
    overwrite an existing directory. Native dispatch refuses unless the caller
    opts in with ``allow_unverified_isolation=True`` AND the OMP session (per the
    ``PI_SESSION_FILE`` header cwd) is rooted at ``project_root``. Isolation is
    stamped ``unverified``: a matching root is a precondition, not a mechanical
    guarantee the subagent filesystem is confined.
    """
    _require_secure(secure)
    if mode not in _VALID_MODES:
        raise ValueError(f"mode must be one of {_VALID_MODES}: {mode!r}")
    if mode == "milestone-review":
        if not (required_criteria and all(isinstance(c, str) and c for c in required_criteria)):
            raise ValueError(
                "milestone-review requires a non-empty required_criteria list "
                "(the acceptance-criterion / Gate B claim ids)")
        if not callable(evidence_gate) or not callable(verdict_guard_factory):
            raise ValueError(
                "milestone-review requires evidence_gate + verdict_guard_factory so the "
                "verdict is bound to Gate B evidence at the engine's frozen snapshot "
                "(never model-reported prose)")
        if draft_schema is None or review_schema is None or synthesis_schema is None:
            raise ValueError(
                "milestone-review requires draft_schema, review_schema and "
                "synthesis_schema (structured evidence is mandatory)")
    if not callable(agent_fn) or not callable(parallel_fn):
        raise ValueError("agent_fn and parallel_fn must be callable")
    if metadata is not None and any(k in _RESERVED_SUMMARY for k in metadata):
        raise ValueError("metadata contains a reserved summary key")
    if not isinstance(min_families, int) or min_families < 1:
        raise ValueError("min_families must be a positive integer")

    checked = [_validate_seat(s, where="seats") for s in seats]
    if len(checked) < 2:
        raise ValueError("a panel needs at least two seats")
    ids = [s["seat_id"] for s in checked]
    if len(set(ids)) != len(ids):
        raise ValueError("seats contains duplicate seat_id")
    families = {s["declared_family"] for s in checked}
    if len(families) < min_families:
        raise ValueError(
            f"panel declares {len(families)} distinct families "
            f"({sorted(families)}); min_families={min_families}")
    synth = _validate_seat(synthesizer_seat, where="synthesizer_seat")

    project = Path(project_root).resolve()
    if not project.is_dir():
        raise ValueError(f"project_root is not a directory: {project}")
    if not allow_unverified_isolation:
        raise ValueError(
            "OMP-native filesystem isolation is unverified; pass "
            "allow_unverified_isolation=True to acknowledge (see the SKILL "
            "isolation note). This flag never claims the subagent tree is confined.")
    session_cwd = _sec(secure, "resolve_omp_session_cwd")()
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

    brief = Path(brief_path)
    if not brief.is_absolute():
        brief = project / brief
    brief = brief.resolve()
    if not brief.is_relative_to(project) or not brief.is_file():
        raise ValueError(f"brief_path must be a file inside project_root: {brief}")

    panels_root = (project / ".colosseum" / "panels").resolve()
    destination = Path(run_dir)
    if not destination.is_absolute():
        destination = project / destination
    destination = destination.resolve()
    if not destination.is_relative_to(panels_root):
        raise ValueError(f"run_dir must be inside {panels_root}")
    destination.mkdir(parents=True, exist_ok=False)

    exclude_rel = destination.relative_to(project).as_posix()
    target_before = _target_snapshot(project, exclude_rel)
    violations = _sec(secure, "preflight_scan")(project)
    brief_hash = _sha256_file(brief)
    preflight = {
        "status": "blocked" if violations else "ok",
        "project_root": str(project),
        "brief_path": str(brief.relative_to(project)),
        "brief_sha256": brief_hash,
        "target_revision": target_before,
        "violations": violations,
    }
    (destination / "preflight.json").write_text(
        json.dumps(preflight, indent=2, ensure_ascii=False) + "\n")
    if violations:
        raise RuntimeError(
            f"preflight blocked OMP-native panel ({len(violations)} violation(s)); "
            f"see {destination / 'preflight.json'}")

    # Bind milestone evidence via Gate B at the canonical source snapshot. The
    # gate receives HEAD (matching itf_replay's source_snapshot convention) and
    # is invoked here inside the frozen window — never "HEAD moments later". The
    # skill passes it to check_evidence_records --expect-snapshot HEAD
    # --snapshot-exact; combined with the engine's clean-tree requirement for a
    # PASS, HEAD then fully determines content. A non-git target yields no token
    # and no evidence, so a milestone cannot PASS on an unversioned tree.
    snapshot_token: str | None = None
    if target_before["available"]:
        snapshot_token = target_before["head"]
    evidence_status: dict[str, str] = {}
    evidence_binding: dict[str, Any] | None = None
    if evidence_gate is not None and snapshot_token is not None:
        # The evidence_gate is caller-supplied trusted code (the canonical
        # gate_b_status helper): it archives the exact Gate B inputs, verifies copy
        # integrity, and returns a structured result. The engine records that
        # binding verbatim and reads the per-claim statuses from it; the archival
        # and integrity trust boundary lives in the helper, not in re-checking an
        # in-process callback (a caller could bypass run_panel entirely).
        raw = dict(evidence_gate(snapshot_token, str(destination / "evidence-inputs")))
        if isinstance(raw.get("status"), Mapping):
            evidence_status = {str(k): v for k, v in raw["status"].items()}
            evidence_binding = raw
        else:  # a bare {claim_id: status} map (e.g. a deterministic test fake)
            evidence_status = {str(k): v for k, v in raw.items()}
            evidence_binding = {"status": evidence_status}
        (destination / "evidence.json").write_text(
            json.dumps(evidence_binding, indent=2, ensure_ascii=False, default=str) + "\n")
    guard = (verdict_guard_factory(evidence_status)
             if verdict_guard_factory is not None else None)

    (destination / "brief.md").write_text(brief.read_text())
    for sub in ("prompts", "prompts/drafts", "prompts/reviews", "drafts", "reviews"):
        (destination / sub).mkdir(parents=True, exist_ok=True)

    # Randomized anon labels so a reviewer cannot infer identity from profile
    # order, and the de-anonymizing map is withheld from the agent-visible tree
    # until _finish (after every review + synthesis). Per-seat files are named by
    # label only. An instruction "do not inspect" is not blinding; keeping the
    # map out of tree is. Filesystem isolation is still unverified (see note), so
    # this is defense against the deterministic in-tree leak, not confinement.
    order = list(range(len(checked)))
    random.Random().shuffle(order)
    labels = {checked[idx]["seat_id"]: chr(ord("A") + pos)
              for pos, idx in enumerate(order)}
    route_hash = _route_hash(mode, checked, synth)
    route = {
        "version": 1,
        "mode": mode,
        "route_hash": route_hash,
        "min_families": min_families,
        "family_distinctness_checked": True,
        "family_distinctness_source": "OMP ctx.models.family runtime comparison (resolver)",
        "seats": checked,
        "synthesizer": synth,
        "anon_labels": labels,
    }
    started_at = _iso_now()
    meta = {
        "version": 1,
        "harness": "omp-native",
        "mode": mode,
        "started_at": started_at,
        "panelist_agent": panelist_agent,
        "synthesizer_agent": synthesizer_agent,
        "route_hash": route_hash,
        "preflight": preflight,
        "isolation": isolation,
        "metadata": dict(metadata or {}),
        "seats": checked,
        "synthesizer": synth,
    }

    def _write_identity_artifacts() -> None:
        # Identity-revealing records land only when no panelist is still running.
        (destination / "route.json").write_text(
            json.dumps(route, indent=2, ensure_ascii=False) + "\n")
        (destination / "meta.json").write_text(
            json.dumps(meta, indent=2, ensure_ascii=False) + "\n")

    def _dispatch(*, seat: Mapping[str, Any], agent_name: str, phase: str,
                  prompt: str, schema: Mapping[str, Any] | None,
                  prompt_rel: Path, out_rel: Path) -> dict[str, Any]:
        # Pure: performs the model call and returns the result in memory. Nothing
        # is written to the agent-visible tree here — persistence happens only
        # after the wave's parallel_fn barrier, so a slow same-wave peer with
        # filesystem tools cannot read a faster peer's output mid-wave.
        seat_id = seat["seat_id"]
        started = time.monotonic()
        selector = seat.get("dispatch_selector", seat["resolved_model"])
        base = {
            "seat_id": seat_id,
            "declared_family": seat["declared_family"],
            "resolved_model": seat["resolved_model"],
            "dispatch_selector": selector,
            "phase": phase,
            "prompt_file": str(prompt_rel),
            "prompt_sha256": _sha256_text(prompt),
            "finish_reason": None,
            "_prompt": prompt,
            "_prompt_rel": str(prompt_rel),
        }
        # Independent per-call random label containing no seat_id: a child that
        # observes its own label cannot enumerate peers' labels. The label->seat
        # map lives only in the record, persisted after the barrier.
        base["dispatch_label"] = f"panel-{phase}-{secrets.token_hex(10)}"
        options: dict[str, Any] = {
            "agent": agent_name,
            "model": selector,
            "label": base["dispatch_label"],
            "handle": True,
        }
        if schema is not None:
            options["schema"] = dict(schema)
        try:
            result = agent_fn(prompt, **options)
            text, data, handle, agent_id = _extract(result)
            if schema is not None and data is None:
                raise RuntimeError(
                    "schema required structured output but the agent returned none")
            if not text.strip() and data is None:
                raise RuntimeError("agent returned empty output")
            elapsed = time.monotonic() - started
            return {
                **base,
                "status": "ok",
                "elapsed_s": round(elapsed, 6),
                "output_file": str(out_rel),
                "output_sha256": _sha256_text(text),
                "output_bytes": len(text.encode()),
                "structured": bool(schema is not None and data is not None),
                "handle": handle,
                "agent_id": agent_id,
                "data": data,
                "_text": text,
                "_out_rel": str(out_rel),
            }
        except Exception as exc:  # one seat must never sink the wave
            elapsed = time.monotonic() - started
            error_text = f"{type(exc).__name__}: {exc}"
            err_rel = out_rel.with_suffix(".error.txt")
            return {
                **base,
                "status": "error",
                "elapsed_s": round(elapsed, 6),
                "output_file": str(err_rel),
                "output_sha256": _sha256_text(error_text),
                "output_bytes": len(error_text.encode()),
                "structured": False,
                "handle": None,
                "agent_id": None,
                "data": None,
                "error": error_text,
                "_text": error_text,
                "_out_rel": str(err_rel),
            }

    def _persist_records(records: Sequence[Any]) -> None:
        """Write prompt + output/error + structured json AFTER a wave barrier."""
        for r in records:
            if not isinstance(r, Mapping):
                continue
            prel = r.get("_prompt_rel")
            if prel is not None:
                (destination / prel).write_text(r.get("_prompt", ""))
            orel = r.get("_out_rel")
            if orel is not None:
                (destination / orel).write_text(r.get("_text", ""))
                if r.get("structured") and r.get("data") is not None:
                    (destination / Path(orel).with_suffix(".json")).write_text(
                        json.dumps(r["data"], indent=2, ensure_ascii=False) + "\n")

    def _finish(run_status: str, drafts: list[Any], reviews: list[Any],
                synthesis: dict[str, Any] | None, quorum: dict[str, Any],
                orchestration_error: str | None = None) -> dict[str, Any]:
        _write_identity_artifacts()
        try:
            brief_after = _sha256_file(brief)
        except OSError:
            brief_after = None
        brief_stable = brief_after == brief_hash
        target_after = _target_snapshot(project, exclude_rel)
        if not target_before["available"]:
            revision_stable = True  # revision unknown -> cannot enforce drift
        else:
            revision_stable = (
                target_after["available"]
                and target_after["head"] == target_before["head"]
                and target_after["snapshot_sha256"] == target_before["snapshot_sha256"])
        # Any instability of the frozen brief OR the target working tree makes the
        # run untrustworthy — a moving target invalidates a milestone verdict.
        if (not brief_stable or not revision_stable) and run_status != "INCOMPLETE":
            run_status = "INCOMPLETE"
        adjudication: dict[str, Any] | None = None
        if guard is not None:
            data = synthesis.get("data") if (synthesis and synthesis.get("status") == "ok") else None
            adjudication = dict(guard(data))
            if run_status == "INCOMPLETE" and adjudication.get("verdict") not in (None, "INCOMPLETE", "FAIL"):
                # An incomplete run cannot yield PASS or a panel-derived CONTESTED,
                # but an authoritative Gate B FAIL is evidence of failure and stands.
                adjudication.setdefault("reasons", []).append(
                    f"run_status={run_status}; non-FAIL verdict forced to INCOMPLETE")
                adjudication["verdict"] = "INCOMPLETE"
            # A milestone PASS asserts success: it requires a fully-complete run
            # AND a known, stable, CLEAN target tree. Gate B binds evidence to HEAD
            # (canonical convention); only a clean tree makes HEAD fully determine
            # content, so a dirty/unavailable/unstable tree or a PARTIAL run can
            # never yield PASS.
            snapshot_ok = (bool(target_before.get("available")) and revision_stable
                           and not target_before.get("dirty"))
            if adjudication.get("verdict") == "PASS" and not (run_status == "COMPLETE" and snapshot_ok):
                adjudication.setdefault("reasons", []).append(
                    f"PASS requires run_status COMPLETE (got {run_status}) and an available, "
                    f"stable, clean target tree (available={bool(target_before.get('available'))}, "
                    f"stable={revision_stable}, dirty={target_before.get('dirty')}); "
                    "downgraded to INCOMPLETE")
                adjudication["verdict"] = "INCOMPLETE"
        summary = {
            "version": 1,
            "harness": "omp-native",
            "mode": mode,
            "started_at": started_at,
            "finished_at": _iso_now(),
            "run_status": run_status,
            "route_hash": route_hash,
            "quorum": quorum,
            "brief_sha256": brief_hash,
            "brief_sha256_after": brief_after,
            "brief_stable": brief_stable,
            "target_revision_before": target_before,
            "target_revision_after": target_after,
            "revision_stable": revision_stable,
            "adjudication": adjudication,
            "evidence": ({k: v for k, v in evidence_binding.items() if k != "report"}
                         if evidence_binding else None),
            "preflight": preflight,
            "isolation": isolation,
            "metadata": dict(metadata or {}),
            "drafts": [_public(r) for r in drafts],
            "reviews": [_public(r) for r in reviews],
            "synthesis": _public(synthesis) if synthesis else None,
        }
        if orchestration_error is not None:
            summary["orchestration_error"] = orchestration_error
        (destination / "summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
        return summary

    def _public(record: Mapping[str, Any] | None) -> dict[str, Any] | None:
        if record is None:
            return None
        # Structured payloads are persisted to their own .json file; the summary
        # keeps only metadata so it stays small and parseable.
        return {k: v for k, v in record.items()
                if k not in ("data", "_prompt", "_prompt_rel", "_text", "_out_rel")}

    # ---- Wave 1: independent drafts (blind to peers) --------------------
    def draft_thunk(seat: Mapping[str, Any]) -> dict[str, Any]:
        slug = labels[seat["seat_id"]]
        return _dispatch(
            seat=seat, agent_name=panelist_agent, phase="draft",
            prompt=draft_prompt_builder(seat), schema=draft_schema,
            prompt_rel=Path("prompts/drafts") / f"{slug}.md",
            out_rel=Path("drafts") / f"{slug}.md")

    draft_thunks = [(lambda s=s: draft_thunk(s)) for s in checked]
    try:
        drafts = list(parallel_fn(draft_thunks))
    except Exception as exc:  # the wave itself failed
        summary = _finish("INCOMPLETE", [], [], None,
                          {"stage": "drafts", "reason": "wave crashed"},
                          orchestration_error=f"{type(exc).__name__}: {exc}")
        raise
    if len(drafts) != len(checked):
        message = f"parallel_fn returned {len(drafts)} draft results for {len(checked)} seats"
        _finish("INCOMPLETE", [d for d in drafts if isinstance(d, Mapping)], [], None,
                {"stage": "drafts", "reason": "result count mismatch"},
                orchestration_error=message)
        raise RuntimeError(message)

    _persist_records(drafts)  # wave-1 barrier passed; safe to write outputs

    ok_drafts = [d for d in drafts if d.get("status") == "ok"]
    ok_families = {d["declared_family"] for d in ok_drafts}
    quorum: dict[str, Any] = {
        "seats": len(checked),
        "drafts_ok": len(ok_drafts),
        "families_ok": sorted(ok_families),
        "min_families": min_families,
        "reviews_ok": 0,
    }
    if len(ok_drafts) < 2 or len(ok_families) < min_families:
        quorum["stage"] = "draft-quorum"
        quorum["reason"] = (
            f"{len(ok_drafts)} draft(s) across {len(ok_families)} families; "
            f"need >=2 drafts and >={min_families} families")
        return _finish("INCOMPLETE", drafts, [], None, quorum)

    # ---- Wave 2: cross-review (each reviewer sees ALL successful drafts) -
    anon_drafts = [
        {"label": labels[d["seat_id"]], "text": d["_text"]}
        for d in ok_drafts
    ]
    reviewer_seats = [next(s for s in checked if s["seat_id"] == d["seat_id"])
                      for d in ok_drafts]

    def review_thunk(seat: Mapping[str, Any]) -> dict[str, Any]:
        own = labels[seat["seat_id"]]
        return _dispatch(
            seat=seat, agent_name=panelist_agent, phase="review",
            prompt=review_prompt_builder(seat, own, anon_drafts),
            schema=review_schema,
            prompt_rel=Path("prompts/reviews") / f"{own}.md",
            out_rel=Path("reviews") / f"{own}.md")

    review_thunks = [(lambda s=s: review_thunk(s)) for s in reviewer_seats]
    try:
        reviews = list(parallel_fn(review_thunks))
    except Exception as exc:
        quorum["stage"] = "reviews"
        quorum["reason"] = "wave crashed"
        _finish("INCOMPLETE", drafts, [], None, quorum,
                orchestration_error=f"{type(exc).__name__}: {exc}")
        raise
    if len(reviews) != len(reviewer_seats):
        message = f"parallel_fn returned {len(reviews)} review results for {len(reviewer_seats)} reviewers"
        quorum["stage"] = "reviews"
        quorum["reason"] = "result count mismatch"
        _finish("INCOMPLETE", drafts, [r for r in reviews if isinstance(r, Mapping)],
                None, quorum, orchestration_error=message)
        raise RuntimeError(message)

    _persist_records(reviews)  # wave-2 barrier passed; safe to write outputs

    ok_reviews = [r for r in reviews if r.get("status") == "ok"]
    # Coverage contract (revised from the loose "every reviewer must succeed"):
    # cross-review coverage means every SUCCESSFUL draft receives an external
    # (non-author) review. Because each reviewer reviews ALL drafts, >=2
    # successful reviews from distinct seats guarantees every draft has an
    # external reviewer -> complete draft coverage -> synthesis may run. This
    # preserves failure isolation: a single transient reviewer error must not
    # discard an otherwise-good N-family panel. Whether EVERY reviewer seat also
    # succeeded is a separate signal (review_coverage_complete) that only gates
    # COMPLETE vs PARTIAL, never whether synthesis runs.
    quorum["reviews_ok"] = len(ok_reviews)
    quorum["reviewers_expected"] = len(reviewer_seats)
    quorum["review_quorum_met"] = len(ok_reviews) >= 2
    quorum["review_coverage_complete"] = len(ok_reviews) == len(reviewer_seats)
    if not quorum["review_quorum_met"]:
        quorum["stage"] = "review-quorum"
        quorum["reason"] = (
            f"{len(ok_reviews)} external review(s); need >=2 so every draft has "
            "a non-author reviewer before synthesis")
        return _finish("INCOMPLETE", drafts, reviews, None, quorum)

    # ---- Wave 3: synthesis --------------------------------------------
    anon_reviews = [
        {"label": labels[r["seat_id"]], "text": r["_text"]}
        for r in ok_reviews
    ]
    synth_prompt = synthesis_prompt_builder(anon_drafts, anon_reviews)
    synthesis = _dispatch(
        seat=synth, agent_name=synthesizer_agent, phase="synthesis",
        prompt=synth_prompt, schema=synthesis_schema,
        prompt_rel=Path("prompts") / "synthesis.md",
        out_rel=Path("final.md"))
    _persist_records([synthesis])
    if synthesis.get("status") != "ok":
        quorum["stage"] = "synthesis"
        quorum["reason"] = "synthesizer failed"
        return _finish("INCOMPLETE", drafts, reviews, synthesis, quorum)

    all_drafted = len(ok_drafts) == len(checked)
    run_status = ("COMPLETE" if (all_drafted and quorum["review_coverage_complete"])
                  else "PARTIAL")
    return _finish(run_status, drafts, reviews, synthesis, quorum)
