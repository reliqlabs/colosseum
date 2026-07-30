#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Launch one OMP calibration session with tested routes' fallbacks disabled.

The OMP eval bridge may echo a requested selector even when its retry layer
served another provider. Calibration therefore needs a process-local overlay
that sets ``retry.fallbackChains[provider/model] = []`` for exactly the voices
being measured. This launcher generates and prechecks that overlay, archives
both artifacts, then starts OMP with the same file through ``--config`` and
``PI_CONFIG_FILES``. The precheck must use ``PI_CONFIG_FILES`` because OMP's
``config`` subcommand accepts no launch flags. An inherited ``PI_CONFIG_FILES``
is preserved and the generated overlay is appended last, so it outranks caller
overlays on the suppressed selectors. It never edits user or project OMP
configuration.

USAGE
    omp_calibration_session.py --project <project> --evidence-dir <dir>
        [--voice <id> ...] [--omp <binary>] -- <OMP launch arguments>

The evidence directory must exist and none of the three generated files may
already exist. Pass the selected route IDs to ``load_omp_native_config`` and
``load_fallback_suppression`` inside the launched OMP eval cell.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
FANOUT = REPO / "skills" / "colosseum-adversarial" / "omp_fanout.py"


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)


def load_fanout():
    spec = importlib.util.spec_from_file_location("colosseum_omp_fanout", FANOUT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {FANOUT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--project", required=True, type=Path,
                        help="initialized project containing .colosseum/dispatch.json")
    result.add_argument("--evidence-dir", required=True, type=Path,
                        help="existing calibration evidence directory")
    result.add_argument("--voice", dest="voices", action="append", default=[],
                        help="OMP voice ID to calibrate; repeatable, defaults to all")
    result.add_argument("--omp", default="omp", help="OMP executable (default: omp)")
    result.add_argument("omp_args", nargs=argparse.REMAINDER,
                        help="arguments passed to OMP after --")
    return result


def is_config_flag(argument: str) -> bool:
    return argument == "--config" or argument.startswith("--config=")


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    project = args.project.resolve()
    evidence_dir = args.evidence_dir.resolve()
    if not project.is_dir():
        parser().error(f"project is not a directory: {project}")
    if not evidence_dir.is_dir():
        parser().error(f"evidence directory does not exist: {evidence_dir}")
    dispatch = project / ".colosseum" / "dispatch.json"
    if not dispatch.is_file():
        parser().error(f"project lacks generated OMP dispatch config: {dispatch}")
    omp_args = list(args.omp_args)
    if omp_args[:1] == ["--"]:
        omp_args = omp_args[1:]
    if not omp_args:
        parser().error("pass OMP launch arguments after --")
    if any(is_config_flag(argument) for argument in omp_args):
        parser().error("do not pass --config; this launcher owns the calibration overlay")
    if not Path(args.omp).is_file() and shutil.which(args.omp) is None:
        parser().error(f"OMP executable is not on PATH: {args.omp}")

    fanout = load_fanout()
    route = fanout.load_omp_native_config(dispatch, selected_ids=args.voices or None)
    overlay = fanout.fallback_suppression_overlay(route["voices"])
    suppressed = sorted(overlay["retry"]["fallbackChains"])
    overlay_path = evidence_dir / "omp-fallback-suppression.json"
    precheck_path = evidence_dir / "omp-fallback-precheck.json"
    launch_path = evidence_dir / "omp-fallback-launch.json"
    existing = [path for path in (overlay_path, precheck_path, launch_path) if path.exists()]
    if existing:
        parser().error("refusing to overwrite calibration evidence: "
                       + ", ".join(str(path) for path in existing))

    atomic_json(overlay_path, overlay)
    overlay_hash = sha256_file(overlay_path)
    precheck_command = [args.omp, "config", "get", "retry.fallbackChains"]
    precheck_environment = os.environ.copy()
    existing_sources = precheck_environment.get("PI_CONFIG_FILES")
    config_sources = os.pathsep.join(
        source for source in (existing_sources, str(overlay_path)) if source)
    # OMP's `config` subcommand intentionally has no launch flags. Its Settings
    # loader does honour PI_CONFIG_FILES. Append rather than replace any caller
    # overlays, so the generated overlay wins without dropping user settings.
    precheck_environment["PI_CONFIG_FILES"] = config_sources
    try:
        precheck_run = subprocess.run(
            precheck_command, capture_output=True, text=True, timeout=60,
            check=False, cwd=project, env=precheck_environment)
    except OSError as exc:
        atomic_json(precheck_path, {
            "version": 1,
            "command": precheck_command,
            "cwd": str(project),
            "environment": {"PI_CONFIG_FILES": config_sources},
            "overlay_sha256": overlay_hash,
            "error": f"{type(exc).__name__}: {exc}",
        })
        print(f"FATAL: could not run OMP precheck: {exc}", file=sys.stderr)
        return 2

    try:
        effective = json.loads(precheck_run.stdout)
    except json.JSONDecodeError:
        effective = None
    precheck = {
        "version": 1,
        "command": precheck_command,
        "cwd": str(project),
        "environment": {"PI_CONFIG_FILES": config_sources},
        "overlay_sha256": overlay_hash,
        "returncode": precheck_run.returncode,
        "stdout_sha256": "sha256:" + hashlib.sha256(precheck_run.stdout.encode()).hexdigest(),
        "stderr_sha256": "sha256:" + hashlib.sha256(precheck_run.stderr.encode()).hexdigest(),
        "effective_fallback_chains": effective,
    }
    atomic_json(precheck_path, precheck)
    if precheck_run.returncode != 0:
        print(f"FATAL: OMP fallback precheck failed; see {precheck_path}", file=sys.stderr)
        return 2
    if not isinstance(effective, dict) or any(effective.get(selector) != [] for selector in suppressed):
        print(f"FATAL: OMP fallback precheck left a selected route eligible; see {precheck_path}",
              file=sys.stderr)
        return 2

    launch_command = [args.omp, "--cwd", str(project), "--config", str(overlay_path), *omp_args]
    environment = os.environ.copy()
    environment["COLOSSEUM_OMP_FALLBACK_OVERLAY"] = str(overlay_path)
    environment["COLOSSEUM_OMP_FALLBACK_PRECHECK"] = str(precheck_path)
    environment["PI_CONFIG_FILES"] = config_sources
    launch = {
        "version": 1,
        "status": "starting",
        "started_at": iso_now(),
        "project_root": str(project),
        "selected_voice_ids": [voice["id"] for voice in route["voices"]],
        "suppressed_selectors": suppressed,
        "overlay_file": str(overlay_path),
        "overlay_sha256": overlay_hash,
        "precheck_file": str(precheck_path),
        "precheck_sha256": sha256_file(precheck_path),
        "command": launch_command,
    }
    atomic_json(launch_path, launch)
    try:
        launched = subprocess.run(launch_command, env=environment, check=False)
        launch["returncode"] = launched.returncode
    except OSError as exc:
        launch["returncode"] = None
        launch["error"] = f"{type(exc).__name__}: {exc}"
    launch["finished_at"] = iso_now()
    launch["status"] = "exited" if "error" not in launch else "launch-error"
    atomic_json(launch_path, launch)
    if launch.get("error"):
        print(f"FATAL: OMP launch failed; see {launch_path}", file=sys.stderr)
        return 2
    return int(launch["returncode"])


if __name__ == "__main__":
    raise SystemExit(main())
