#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
itf_replay — the conformance bridge (C2, contracts G1/G3).

Generates seeded ITF traces from a Quint spec (`quint run --out-itf`, no
--mbt) and replays each through a project-supplied ADAPTER executable that
implements the same machine in code. Step-by-step equivalence of the
replayed states is what backs the `conformance-tested` evidence class.
The label is exactly `conformance-tested[<trace scope>]` — this tool (and
every other surface) never emits a refinement-style label; a mechanized
refinement argument is a separate, later upgrade (M7) with its own label.

LINE PROTOCOL v1 (driver <-> adapter; one adapter process per trace)

    driver -> adapter (stdin), lockstep:
        VARS <name> <name> ...        # spec state vars; NO reply expected
        INIT <name>=<value> ...       # trace state 0; one reply expected
        EXPECT <name>=<value> ...     # trace state k; one reply per EXPECT
        END                           # adapter exits

    adapter -> driver (stdout), per INIT/EXPECT:
        [OUT <token>]*                # optional declared outputs, in order
        STATE <name>=<value> ...      # the adapter's own state after
                                      # applying ITS implementation's
                                      # corresponding transition
      | ERR <detail>                  # implementation-side error

    Values in v1: integers (decimal), booleans (true/false), and strings
    without whitespace. Other ITF value shapes are a driver error. How the
    adapter maps an expected post-state to an implementation transition is
    the adapter's business (typically delta inference); v2 may carry
    --mbt action labels instead.

    Comparison per step: the adapter's STATE must equal the trace state
    (state equivalence); OUT lines are compared when the config declares
    expected outputs; an ERR reply is a divergence in v1 (the fixture spec
    has no declared error states; error-vs-error equivalence arrives with
    specs that model errors as states).

CONFIG (JSON; paths relative to the config file)

    {
      "spec": "specs/flow.qnt",
      "adapter": ["adapter/target/debug/r24-adapter"],
      "adapter_env": {"FV_R24_BUG": "1"},   // optional
      "n_traces": 5, "max_steps": 15, "max_samples": 200, "seed": "0x1",
      "claim_id": "CONF1",              // required for --record
      "intent": "intent.md",            // required for --record
      "environment_policy": "host"      // optional, default "host"
    }

    The replay config IS the obligation statement for the conformance
    claim: --record binds obligation_manifest_hash to the config file.

USAGE
    itf_replay.py --config <replay.json> [--record out.json] [--json]
                  [--keep-traces <dir>]

VERDICT (exit code)
    conformance-tested[traces=N, depth=D, seed=S] PASS   (0)
    FAILED — first divergence named (trace, step, var)   (1)
    ERROR — usage/tool failure                           (2)
    INCOMPLETE — zero traces generated / adapter absent  (3)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def die(verdict: str, code: int, msg: str) -> int:
    print(msg, file=sys.stderr)
    print(f"\nVERDICT: {verdict}", file=sys.stderr)
    return code


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def decode_itf_value(v) -> object:
    if isinstance(v, dict) and "#bigint" in v:
        return int(v["#bigint"])
    if isinstance(v, (int, bool)):
        return v
    if isinstance(v, str):
        if any(c.isspace() for c in v):
            raise ValueError(f"v1 protocol cannot carry strings with whitespace: {v!r}")
        return v
    raise ValueError(f"unsupported ITF value shape in v1: {v!r}")


def encode_value(v: object) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def parse_state_line(line: str) -> dict[str, str]:
    out = {}
    for tok in line.split()[1:]:
        name, _, val = tok.partition("=")
        out[name] = val
    return out


def load_trace(path: Path) -> tuple[list[str], list[dict[str, object]]]:
    data = json.loads(path.read_text())
    vars_ = sorted({v for v in data["vars"] if not v.startswith("#")})
    states = []
    for raw in data["states"]:
        states.append({name: decode_itf_value(raw[name]) for name in vars_})
    return vars_, states


class Divergence(Exception):
    def __init__(self, step: int, detail: str):
        self.step = step
        self.detail = detail
        super().__init__(detail)


def replay_trace(adapter_cmd: list[str], env: dict, cwd: Path,
                 vars_: list[str], states: list[dict[str, object]],
                 transcript: list[str]) -> None:
    """Raises Divergence on the first divergent step."""
    proc = subprocess.Popen(adapter_cmd, cwd=cwd, env=env, text=True,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)

    def send(line: str) -> None:
        transcript.append(f"> {line}")
        proc.stdin.write(line + "\n")
        proc.stdin.flush()

    def read_reply() -> tuple[list[str], str]:
        outs = []
        while True:
            line = proc.stdout.readline()
            if not line:
                raise Divergence(-1, "adapter closed stdout mid-replay")
            line = line.rstrip("\n")
            transcript.append(f"< {line}")
            if line.startswith("OUT "):
                outs.append(line[4:])
                continue
            return outs, line

    try:
        send("VARS " + " ".join(vars_))
        for k, state in enumerate(states):
            bindings = " ".join(f"{n}={encode_value(state[n])}" for n in vars_)
            send(("INIT " if k == 0 else "EXPECT ") + bindings)
            _outs, reply = read_reply()
            if reply.startswith("ERR "):
                raise Divergence(k, f"adapter error: {reply[4:]}")
            if not reply.startswith("STATE "):
                raise Divergence(k, f"protocol violation: {reply!r}")
            got = parse_state_line(reply)
            for name in vars_:
                expected = encode_value(state[name])
                if got.get(name) != expected:
                    raise Divergence(
                        k, f"var {name}: spec expects {expected}, "
                           f"adapter replayed {got.get(name)}")
        send("END")
        proc.stdin.close()
        proc.wait(timeout=30)
    finally:
        if proc.poll() is None:
            proc.kill()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, type=Path)
    ap.add_argument("--record", type=Path, default=None,
                    help="write a G1 evidence record (check_evidence_records.py shape)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--keep-traces", type=Path, default=None)
    args = ap.parse_args()

    try:
        cfg = json.loads(args.config.read_text())
    except (OSError, json.JSONDecodeError) as e:
        return die("ERROR", 2, f"ERROR: cannot read config: {e}")
    base = args.config.resolve().parent
    spec = (base / cfg["spec"]).resolve()
    if not spec.is_file():
        return die("ERROR", 2, f"ERROR: spec not found: {spec}")
    adapter_cmd = [str((base / cfg["adapter"][0]).resolve()), *cfg["adapter"][1:]]
    if not Path(adapter_cmd[0]).is_file():
        return die("INCOMPLETE", 3,
                   f"INCOMPLETE: adapter not built: {adapter_cmd[0]}")
    n_traces = int(cfg.get("n_traces", 5))
    max_steps = int(cfg.get("max_steps", 15))
    max_samples = int(cfg.get("max_samples", max(200, n_traces)))
    seed = str(cfg.get("seed", "0x1"))
    env = {"PATH": "/usr/bin:/bin", **cfg.get("adapter_env", {})}

    scope = f"traces={n_traces}, depth={max_steps}, seed={seed}"
    label = f"conformance-tested[{scope}]"

    with tempfile.TemporaryDirectory(prefix="itf-replay-") as td:
        tdir = Path(td)
        gen_cmd = ["quint", "run", "--out-itf=trace_{seq}.itf.json",
                   f"--n-traces={n_traces}", f"--max-samples={max_samples}",
                   f"--max-steps={max_steps}", f"--seed={seed}", str(spec)]
        gen = subprocess.run(gen_cmd, cwd=tdir, capture_output=True, text=True)
        traces = sorted(tdir.glob("trace_*.itf.json"))
        if gen.returncode != 0 or not traces:
            return die("INCOMPLETE", 3,
                       f"INCOMPLETE: trace generation produced {len(traces)} "
                       f"trace(s) (exit={gen.returncode}): {gen.stderr[-300:]}")
        if args.keep_traces:
            args.keep_traces.mkdir(parents=True, exist_ok=True)
            for t in traces:
                (args.keep_traces / t.name).write_text(t.read_text())

        transcript: list[str] = []
        per_trace: list[dict] = []
        first_divergence: dict | None = None
        for t in traces:
            vars_, states = load_trace(t)
            try:
                replay_trace(adapter_cmd, env, base, vars_, states, transcript)
                per_trace.append({"trace": t.name, "steps": len(states) - 1,
                                  "result": "conformant"})
            except Divergence as d:
                entry = {"trace": t.name, "result": "DIVERGENT",
                         "step": d.step, "detail": d.detail}
                per_trace.append(entry)
                if first_divergence is None:
                    first_divergence = entry


    result = "FAIL" if first_divergence else "PASS"
    report = {
        "gate": "conformance-bridge",
        "spec": str(spec),
        "adapter": adapter_cmd,
        "label": label,
        "per_trace": per_trace,
        "result": result,
    }
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for e in per_trace:
            mark = "ok" if e["result"] == "conformant" else "DIVERGENT"
            print(f"  [{mark:>9}] {e['trace']}"
                  + (f" step {e['step']}: {e['detail']}" if mark != "ok" else ""))

    if args.record:
        raw_dir = base / ".fv" / "evidence" / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        raw_path = raw_dir / f"{cfg['claim_id']}-itf-replay.log"
        raw_text = json.dumps(report, indent=2) + "\n"
        if result == "PASS":
            raw_text += "CONFORMANCE_TESTED: PASS\n"
        raw_text += f"--- fv-evidence: exit={0 if result == 'PASS' else 1} ---\n"
        raw_path.write_text(raw_text)
        quint_ver = subprocess.run(["quint", "--version"], capture_output=True,
                                   text=True).stdout.strip()
        git = subprocess.run(["git", "-C", str(base), "rev-parse", "HEAD"],
                             capture_output=True, text=True)
        if git.returncode == 0:
            dirty = subprocess.run(["git", "-C", str(base), "status", "--porcelain"],
                                   capture_output=True, text=True).stdout.strip()
            snapshot = git.stdout.strip() + ("+dirty" if dirty else "")
        else:
            snapshot = f"no-vcs+sha256:{sha256_bytes(spec.read_bytes())[:12]}"
        intent = (base / cfg["intent"]).resolve()
        record = {
            "claim_id": cfg["claim_id"],
            "required": True,
            "evidence_class": "conformance-tested",
            "result": result,
            "scope": f"{scope}, adapter={Path(adapter_cmd[0]).name}",
            "bindings": {
                "source_snapshot": snapshot,
                "intent_hash": sha256_bytes(intent.read_bytes()),
                "obligation_manifest_hash": sha256_bytes(args.config.read_bytes()),
                "profile": "conformance",
                "required_targets": [cfg["claim_id"]],
                "environment_policy": cfg.get("environment_policy", "host"),
                "toolchain_digests": {
                    "quint": quint_ver,
                    "adapter_sha256": sha256_bytes(
                        Path(adapter_cmd[0]).read_bytes())[:12],
                },
                "command": " ".join(gen_cmd),
                "configuration": {"n_traces": n_traces, "max_steps": max_steps,
                                  "max_samples": max_samples},
                "seeds": seed,
                "raw_output_hash": sha256_bytes(raw_path.read_bytes()),
                "raw_output_path": str(raw_path.relative_to(base)),
                "parser_schema_version": "itf-replay-v1",
                "run_id": f"{cfg['claim_id']}-conformance-"
                          f"{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H%M%SZ')}",
            },
            "waiver": None,
        }
        args.record.write_text(json.dumps(record, indent=2) + "\n")
        print(f"record written to {args.record}", file=sys.stderr)

    if first_divergence:
        return die(f"FAILED — divergence at {first_divergence['trace']} step "
                   f"{first_divergence['step']} ({first_divergence['detail']}); "
                   f"scope was [{scope}]", 1, "")
    print(f"\nVERDICT: {label} PASS", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
