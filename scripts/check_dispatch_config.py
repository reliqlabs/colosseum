#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
check_dispatch_config — schema gate for opencode_dispatch.py configs (C10).

Validates a dispatch config against the load_config contract in
scripts/opencode_dispatch.py so a malformed dispatch.json fails CI instead
of a field run. The SLUG_RE and required-field set are imported from
opencode_dispatch so this gate cannot drift from the loader.

Structural checks (always): required top-level fields present; voices and
slices non-empty; each voice has id+model, each slice has name+headers;
voice ids and slice names are valid slugs and unique; run_tag_prefix is a
valid slug. Path existence (target_spec is a file, project_root exists) is
checked only with --require-paths, since the shipped example config uses
`/absolute/path/...` placeholders.

USAGE
    check_dispatch_config.py <config.json> [--require-paths]
    check_dispatch_config.py --selftest      # validate the example + bad fixtures

EXIT  0 valid | 1 invalid | 2 usage/IO error
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REQUIRED = ("project_root", "target_spec", "run_tag_prefix", "voices", "slices")


def _slug_re():
    spec = importlib.util.spec_from_file_location(
        "opencode_dispatch", REPO / "scripts" / "opencode_dispatch.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.SLUG_RE


SLUG_RE = _slug_re()


def valid_slug(value) -> bool:
    return isinstance(value, str) and bool(SLUG_RE.match(value)) and ".." not in value


def validate(cfg: dict, *, require_paths: bool = False,
             base: Path | None = None) -> list[str]:
    """Return a list of problems; empty means valid."""
    errors: list[str] = []
    for field in REQUIRED:
        if field not in cfg:
            errors.append(f"missing required field '{field}'")
    if errors:
        return errors  # structural shape unknown; stop before indexing

    if not valid_slug(cfg["run_tag_prefix"]):
        errors.append(f"run_tag_prefix {cfg['run_tag_prefix']!r} is not a valid slug")

    voices = cfg["voices"]
    slices = cfg["slices"]
    if not isinstance(voices, list) or not voices:
        errors.append("voices must be a non-empty list")
        voices = []
    if not isinstance(slices, list) or not slices:
        errors.append("slices must be a non-empty list")
        slices = []

    vids: list[str] = []
    for i, v in enumerate(voices):
        if not isinstance(v, dict) or "id" not in v or "model" not in v:
            errors.append(f"voice[{i}] must have 'id' and 'model'")
            continue
        if not valid_slug(v["id"]):
            errors.append(f"voice id {v['id']!r} is not a valid slug")
        vids.append(v.get("id"))
    snames: list[str] = []
    for i, s in enumerate(slices):
        if not isinstance(s, dict) or "name" not in s or "headers" not in s:
            errors.append(f"slice[{i}] must have 'name' and 'headers'")
            continue
        if not valid_slug(s["name"]):
            errors.append(f"slice name {s['name']!r} is not a valid slug")
        snames.append(s.get("name"))

    for kind, names in (("voice id", vids), ("slice name", snames)):
        dupes = sorted({n for n in names if names.count(n) > 1})
        if dupes:
            errors.append(f"duplicate {kind}(s): {dupes}")

    if require_paths:
        root = base or Path.cwd()
        spec_path = (root / cfg["target_spec"]) if not Path(cfg["target_spec"]).is_absolute() \
            else Path(cfg["target_spec"])
        if not spec_path.is_file():
            errors.append(f"target_spec does not exist: {cfg['target_spec']}")
    return errors


def check_file(path: Path, require_paths: bool) -> list[str]:
    try:
        cfg = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        return [f"cannot parse {path}: {e}"]
    return validate(cfg, require_paths=require_paths, base=path.parent)


def selftest() -> int:
    example = REPO / "scripts" / "dispatch.config.example.json"
    ok = True
    errs = check_file(example, require_paths=False)
    print(f"  [{'ok' if not errs else 'FAIL'}] example config validates",
          "" if not errs else f"({errs})")
    ok &= not errs

    base = json.loads(example.read_text())

    missing = {k: v for k, v in base.items() if k != "target_spec"}
    errs = validate(missing)
    hit = any("target_spec" in e for e in errs)
    print(f"  [{'ok' if hit else 'FAIL'}] missing target_spec rejected")
    ok &= hit

    dup = json.loads(example.read_text())
    dup["voices"] = dup["voices"] + [dict(dup["voices"][0])]
    errs = validate(dup)
    hit = any("duplicate voice id" in e for e in errs)
    print(f"  [{'ok' if hit else 'FAIL'}] duplicate voice id rejected")
    ok &= hit

    print("\nDISPATCH-CONFIG SELFTEST " + ("PASSED" if ok else "FAILED"))
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("config", nargs="?", type=Path)
    ap.add_argument("--require-paths", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()
    if not args.config:
        print("usage: check_dispatch_config.py <config.json> | --selftest", file=sys.stderr)
        return 2

    errors = check_file(args.config, args.require_paths)
    for e in errors:
        print(f"FAIL: {e}", file=sys.stderr)
    if errors:
        print(f"\nDISPATCH-CONFIG INVALID: {len(errors)} problem(s)", file=sys.stderr)
        return 1
    print(f"DISPATCH-CONFIG VALID: {args.config}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
