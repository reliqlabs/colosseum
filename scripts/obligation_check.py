#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
obligation_check — frozen obligation manifest checker (E3, contracts G1-G3).

The obligation manifest is orchestrator-owned: it derives obligations from
immutable intent IDs, and generators cannot write it (their permission
profile denies `**/.fv/obligations*`). Generators PROPOSE spec
files; this checker is the only thing that ACCEPTS them, by re-running
every obligation mechanically:

  presence     every required invariant and witness is defined in the spec
  frozen       pinned definition hashes match — a modified required
               invariant is a proposal diff, never a silent acceptance
  vacuity      heuristic: an invariant whose definition (one def-level
               deep) references no state variable, or is literally true,
               is vacuous
  safety       every required invariant passes `quint verify` at the
               manifest bounds (evidence class: bounded-checked, depth
               recorded — `quint run` is never accepted here)
  reachability every witness is violated by `quint run` (the trace is the
               witness); a witness that survives escalation to
               `quint verify` denies an unreachable state or tautology
  enabledness  every listed transition is observed to fire in a ghost-
               probe search; if the probe survives `quint verify` the
               transition is disabled within the bound

MANIFEST SCHEMA (.fv/obligations.json), orchestrator-owned:
    {
      "version": 1,
      "intent_path": "intent.md",          # relative to manifest dir
      "intent_sha256": "<hex>|null",       # freeze of the intent text
      "spec_dir": "specs",                 # relative to manifest dir
      "main_file": "main.qnt",             # entry file inside spec_dir
      "module": "main",                    # module the probe imports
      "init": "init", "step": "step",
      "invariants": [ {"id": "B1", "name": "inv_x",
                       "definition_sha256": "<hex>|null"} ],
      "witnesses":  [ {"id": "W1", "name": "witness_r"} ],
      "transitions": ["grow", "stay"],     # zero-arg step-level actions
      "bounds": {"max_steps": 20, "max_samples": 1000, "seed": "0x1"}
    }

VERDICTS (exit code)
    ACCEPTED (0)   every obligation met; with --pin, definition hashes are
                   frozen into the manifest (the only manifest write path)
    PROPOSAL (1)   one or more obligations unmet or definitions changed;
                   the record carries the proposal diff for adjudication
    ERROR    (2)   tool or manifest failure — never silently green

All quint executions happen in a throwaway copy of the spec dir, so probe
files and Apalache output never land in the proposal tree.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DEF_RE = r"^\s*(?:pure\s+def|val|def)\s+{name}\b"
NEXT_DECL_RE = re.compile(r"^\s*(?:pure\s+def|val|def|action|var|const|import|module|})\b")
VAR_RE = re.compile(r"^\s*var\s+(\w+)\s*:", re.MULTILINE)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", "", text)


def extract_definition(spec_text: str, name: str) -> str | None:
    """Extract a definition body from `val|def <name>` to the next top-level
    declaration. Returned normalized (comments stripped, whitespace
    collapsed) for stable hashing."""
    lines = spec_text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if re.match(DEF_RE.format(name=re.escape(name)), line):
            start = i
            break
    if start is None:
        return None
    body = [lines[start]]
    for line in lines[start + 1:]:
        if NEXT_DECL_RE.match(line):
            break
        body.append(line)
    normalized = " ".join(strip_comments("\n".join(body)).split())
    return normalized


def quint(args: list[str], cwd: Path, timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(["quint", *args], cwd=cwd, capture_output=True,
                          text=True, timeout=timeout)


class Checker:
    def __init__(self, manifest_path: Path):
        self.manifest_path = manifest_path.resolve()
        self.manifest = json.loads(self.manifest_path.read_text())
        base = self.manifest_path.parent
        self.spec_dir = (base / self.manifest["spec_dir"]).resolve()
        if not self.spec_dir.is_relative_to(base.parent.resolve()) \
                and not self.spec_dir.is_relative_to(base.resolve()):
            sys.exit(f"ERROR: spec_dir escapes the project tree: {self.spec_dir}")
        self.intent_path = (base / self.manifest["intent_path"]).resolve()
        self.bounds = self.manifest.get("bounds", {})
        self.results: list[dict] = []
        self.proposal_diffs: list[dict] = []

    def record(self, obligation: str, target: str, ok: bool, evidence: str,
               detail: str = "") -> None:
        self.results.append({
            "obligation": obligation, "target": target,
            "ok": ok, "evidence_class": evidence, "detail": detail,
        })
        mark = "ok" if ok else "UNMET"
        line = f"  [{mark:5}] {obligation:12} {target}: {evidence}"
        print(line + (f" — {detail}" if detail and not ok else ""), file=sys.stderr)

    def bound_args(self, samples: bool) -> list[str]:
        args = [f"--max-steps={self.bounds.get('max_steps', 20)}"]
        if samples:
            args.append(f"--max-samples={self.bounds.get('max_samples', 1000)}")
            if self.bounds.get("seed"):
                args.append(f"--seed={self.bounds['seed']}")
        return args

    def run_all(self, workdir: Path) -> None:
        spec_copy = workdir / "spec"
        shutil.copytree(self.spec_dir, spec_copy)
        main_file = spec_copy / self.manifest["main_file"]
        spec_text = "\n".join(
            p.read_text() for p in sorted(spec_copy.glob("*.qnt")))
        state_vars = set(VAR_RE.findall(strip_comments(spec_text)))

        # intent freeze
        if self.manifest.get("intent_sha256"):
            actual = sha256(self.intent_path.read_text())
            self.record("intent", str(self.manifest["intent_path"]),
                        actual == self.manifest["intent_sha256"],
                        "hash-pinned",
                        "intent text changed since the manifest was frozen; "
                        "regenerate the manifest deliberately" )

        # typecheck
        tc = quint(["typecheck", main_file.name], spec_copy)
        self.record("typecheck", main_file.name, tc.returncode == 0,
                    "mechanical", tc.stderr.strip()[:300])
        if tc.returncode != 0:
            return

        # presence + frozen pins + vacuity + safety, per invariant
        for inv in self.manifest.get("invariants", []):
            name = inv["name"]
            definition = extract_definition(spec_text, name)
            self.record("presence", name, definition is not None, "textual",
                        "required invariant not defined in the spec")
            if definition is None:
                continue

            pin = inv.get("definition_sha256")
            actual_hash = sha256(definition)
            if pin:
                frozen_ok = actual_hash == pin
                if not frozen_ok:
                    self.proposal_diffs.append({
                        "invariant": name, "pinned_sha256": pin,
                        "proposed_sha256": actual_hash,
                        "proposed_definition": definition,
                    })
                self.record("frozen", name, frozen_ok, "hash-pinned",
                            "definition differs from the frozen manifest — "
                            "recorded as a proposal diff, not accepted")
            inv["_observed_sha256"] = actual_hash

            expanded = definition
            for other in re.findall(r"\b(\w+)\b", definition):
                if other != name and (odef := extract_definition(spec_text, other)):
                    expanded += " " + odef
            vacuous = (re.fullmatch(rf"(?:pure def|val|def)\s+{re.escape(name)}(?:\s*:\s*bool)?\s*=\s*true", definition)
                       or not any(re.search(rf"\b{re.escape(v)}\b", expanded) for v in state_vars))
            self.record("vacuity", name, not vacuous, "heuristic",
                        "definition references no state variable (one def "
                        "level chased) or is literally true")

            ver = quint(["verify", f"--invariant={name}",
                         *self.bound_args(samples=False), main_file.name], spec_copy)
            depth = self.bounds.get("max_steps", 20)
            self.record("safety", name, ver.returncode == 0,
                        f"bounded-checked (verify, depth={depth})",
                        (ver.stdout + ver.stderr)[-300:])

        # witness reachability
        for wit in self.manifest.get("witnesses", []):
            name = wit["name"]
            present = extract_definition(spec_text, name) is not None
            self.record("presence", name, present, "textual",
                        "witness not defined in the spec")
            if not present:
                continue
            run = quint(["run", f"--invariant={name}",
                         *self.bound_args(samples=True), main_file.name], spec_copy)
            if run.returncode != 0 and "violat" in (run.stdout + run.stderr).lower():
                self.record("reachability", name, True,
                            "witnessed (run trace)", "")
                continue
            ver = quint(["verify", f"--invariant={name}",
                         *self.bound_args(samples=False), main_file.name], spec_copy)
            if ver.returncode == 0:
                self.record("reachability", name, False,
                            f"bounded-checked (verify, depth={self.bounds.get('max_steps', 20)})",
                            "witness cannot be violated: the state it denies is "
                            "unreachable within the bound, or the witness is a tautology")
            else:
                self.record("reachability", name, True,
                            "witnessed (verify counterexample)", "")

        # transition enabledness (ghost probe)
        module = self.manifest["module"]
        stem = Path(self.manifest["main_file"]).stem
        init, step = self.manifest.get("init", "init"), self.manifest.get("step", "step")
        for t in self.manifest.get("transitions", []):
            probe = spec_copy / "__obligation_probe.qnt"
            probe.write_text(f"""module __obligation_probe {{
  import {module}.* from "./{stem}"
  var __fired: bool
  action __init = all {{ {init}, __fired' = false }}
  action __step = any {{
    all {{ {t}, __fired' = true }},
    all {{ {step}, __fired' = __fired }},
  }}
  val __unfired = not(__fired)
}}
""")
            run = quint(["run", "--init=__init", "--step=__step",
                         "--invariant=__unfired", *self.bound_args(samples=True),
                         probe.name], spec_copy)
            if run.returncode != 0 and "violat" in (run.stdout + run.stderr).lower():
                self.record("enabledness", t, True, "witnessed (run trace)", "")
                continue
            ver = quint(["verify", "--init=__init", "--step=__step",
                         "--invariant=__unfired", *self.bound_args(samples=False),
                         probe.name], spec_copy)
            if ver.returncode == 0:
                self.record("enabledness", t, False,
                            f"bounded-checked (verify, depth={self.bounds.get('max_steps', 20)})",
                            "transition never fires within the bound: dead guard "
                            "or unreachable precondition")
            else:
                self.record("enabledness", t, True,
                            "witnessed (verify counterexample)", "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--pin", action="store_true",
                    help="on ACCEPTED, freeze observed definition hashes into "
                         "the manifest (orchestrator-only write path)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        checker = Checker(args.manifest)
        versions = quint(["--version"], Path.cwd()).stdout.strip()
        with tempfile.TemporaryDirectory(prefix="obligations-") as td:
            checker.run_all(Path(td))
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        print("\nVERDICT: ERROR", file=sys.stderr)
        return 2

    unmet = [r for r in checker.results if not r["ok"]]
    verdict = "ACCEPTED" if not unmet else "PROPOSAL"
    record = {
        "gate": "obligation-check",
        "manifest": str(checker.manifest_path),
        "quint_version": versions,
        "bounds": checker.bounds,
        "results": checker.results,
        "proposal_diffs": checker.proposal_diffs,
        "verdict": verdict,
    }
    if args.json:
        print(json.dumps(record, indent=2))

    if verdict == "ACCEPTED" and args.pin:
        for inv in checker.manifest.get("invariants", []):
            if "_observed_sha256" in inv:
                inv["definition_sha256"] = inv.pop("_observed_sha256")
        checker.manifest_path.write_text(json.dumps(checker.manifest, indent=2) + "\n")
        print(f"pinned {len(checker.manifest.get('invariants', []))} definition hash(es) "
              f"into {checker.manifest_path}", file=sys.stderr)

    print(f"\nVERDICT: {verdict}"
          + (f" ({len(unmet)} obligation(s) unmet)" if unmet else ""),
          file=sys.stderr)
    return 0 if verdict == "ACCEPTED" else 1


if __name__ == "__main__":
    sys.exit(main())
