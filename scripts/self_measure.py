#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
self_measure — the M2 self-measurement aggregator.

Computes the three metrics defined in docs/self-measurement.md over a run's
own artifacts: adversarial yield, cost, and cheapest-capable-layer routing.
Read that document for what each number means. These are self-observations,
not evidence of external benefit (that is M3/M6).

Every metric is computed only over data actually present. When the input a
metric needs is absent, the subcommand exits 3 (INCOMPLETE) and says which
input is missing. No metric is ever backfilled with a default or a zero.

SUBCOMMANDS
    yield   --findings F.json [--run run.json]
        Per-voice adversarial yield, bucketed by severity, confirmed vs
        refuted at adjudication. A finding raised by k voices counts 1/k to
        each source (raised_any keeps the whole-finding view).

    cost    --events E.json [--findings F.json]
        Per-voice token cost and cost per confirmed finding. A voice with no
        token data is reported "unmeasured", never 0.

    routing --findings F.json --layer-map M.json
        Fraction of defects caught at or below their cheapest-capable layer.
        Requires a layer-map (per-defect cheapest_capable + actual_caught);
        without it the metric is not honestly computable and this exits 3.

EXIT CODES
    0  metric computed
    2  usage / unreadable input
    3  metric not computable from the given data (INCOMPLETE)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_LAYER_ORDER = [
    "types", "lints", "property-tests", "fuzz", "kani", "verus", "aeneas-lean",
]


def _load_json(path: Path) -> object:
    return json.loads(path.read_text())


def _adjudicated(findings: dict) -> list[dict]:
    """Findings that reached adjudication carry a verdict.confirmed flag."""
    out = []
    for key in ("confirmed", "refuted"):
        for f in findings.get(key, []):
            if isinstance(f, dict):
                out.append(f)
    return out


def _sources(f: dict) -> list[str]:
    s = f.get("sources")
    if isinstance(s, list) and s:
        return [str(x) for x in s]
    return ["(unattributed)"]


def _is_confirmed(f: dict) -> bool:
    v = f.get("verdict")
    return isinstance(v, dict) and bool(v.get("confirmed"))


# -----------------------------------------------------------------------------
# yield
# -----------------------------------------------------------------------------

def cmd_yield(args: argparse.Namespace) -> int:
    try:
        findings = _load_json(args.findings)
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: cannot read findings: {e}", file=sys.stderr)
        return 2
    if not isinstance(findings, dict):
        print("ERROR: findings JSON must be an object", file=sys.stderr)
        return 2

    phase = None
    if args.run:
        try:
            run = _load_json(args.run)
            phase = run.get("phase") if isinstance(run, dict) else None
        except (OSError, json.JSONDecodeError) as e:
            print(f"ERROR: cannot read run manifest: {e}", file=sys.stderr)
            return 2

    adjudicated = _adjudicated(findings)
    if not adjudicated:
        print("INCOMPLETE: no adjudicated findings (confirmed/refuted empty)",
              file=sys.stderr)
        return 3

    per_voice: dict[str, dict] = {}
    tot_conf = tot_ref = 0
    for f in adjudicated:
        srcs = _sources(f)
        w = 1.0 / len(srcs)
        sev = str(f.get("severity", "unknown"))
        confirmed = _is_confirmed(f)
        tot_conf += 1 if confirmed else 0
        tot_ref += 0 if confirmed else 1
        for s in srcs:
            v = per_voice.setdefault(s, {
                "raised_any": 0, "total_attr": 0.0,
                "confirmed_attr": 0.0, "refuted_attr": 0.0, "by_severity": {},
            })
            v["raised_any"] += 1
            v["total_attr"] += w
            v["confirmed_attr" if confirmed else "refuted_attr"] += w
            sv = v["by_severity"].setdefault(sev, {"total_attr": 0.0,
                                                   "confirmed_attr": 0.0})
            sv["total_attr"] += w
            if confirmed:
                sv["confirmed_attr"] += w

    for v in per_voice.values():
        v["yield"] = (round(v["confirmed_attr"] / v["total_attr"], 4)
                      if v["total_attr"] else None)
        v["total_attr"] = round(v["total_attr"], 4)
        v["confirmed_attr"] = round(v["confirmed_attr"], 4)
        v["refuted_attr"] = round(v["refuted_attr"], 4)
        for sv in v["by_severity"].values():
            sv["total_attr"] = round(sv["total_attr"], 4)
            sv["confirmed_attr"] = round(sv["confirmed_attr"], 4)

    report = {
        "metric": "adversarial-yield",
        "phase": phase,
        "totals": {"confirmed": tot_conf, "refuted": tot_ref},
        "per_voice": per_voice,
    }
    _emit(report, args.json, _fmt_yield)
    return 0


def _fmt_yield(r: dict) -> str:
    lines = [f"adversarial yield  (phase={r['phase']})",
             f"  adjudicated: {r['totals']['confirmed']} confirmed, "
             f"{r['totals']['refuted']} refuted"]
    for voice, v in sorted(r["per_voice"].items()):
        lines.append(
            f"  {voice:<24} raised={v['raised_any']:<3} "
            f"attr={v['total_attr']:<6} confirmed={v['confirmed_attr']:<6} "
            f"yield={v['yield']}")
    return "\n".join(lines)


# -----------------------------------------------------------------------------
# cost
# -----------------------------------------------------------------------------

def cmd_cost(args: argparse.Namespace) -> int:
    try:
        events = _load_json(args.events)
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: cannot read events: {e}", file=sys.stderr)
        return 2
    voices_tokens = events.get("voices") if isinstance(events, dict) else None
    if not isinstance(voices_tokens, dict):
        print("ERROR: events JSON needs a 'voices' object "
              "({voice: {tokens: N}})", file=sys.stderr)
        return 2

    confirmed_attr: dict[str, float] = {}
    if args.findings:
        try:
            findings = _load_json(args.findings)
        except (OSError, json.JSONDecodeError) as e:
            print(f"ERROR: cannot read findings: {e}", file=sys.stderr)
            return 2
        for f in _adjudicated(findings):
            if _is_confirmed(f):
                srcs = _sources(f)
                w = 1.0 / len(srcs)
                for s in srcs:
                    confirmed_attr[s] = confirmed_attr.get(s, 0.0) + w

    per_voice: dict[str, dict] = {}
    for voice, data in voices_tokens.items():
        tokens = data.get("tokens") if isinstance(data, dict) else None
        if tokens is None:
            per_voice[voice] = {"tokens": "unmeasured",
                                "cost_per_confirmed": "unmeasured"}
            continue
        entry = {"tokens": tokens}
        if args.findings:
            ca = confirmed_attr.get(voice, 0.0)
            entry["cost_per_confirmed"] = (round(tokens / ca, 1) if ca
                                           else "no-confirmed-findings")
        per_voice[voice] = entry

    report = {"metric": "cost", "per_voice": per_voice}
    _emit(report, args.json, _fmt_cost)
    return 0


def _fmt_cost(r: dict) -> str:
    lines = ["cost"]
    for voice, v in sorted(r["per_voice"].items()):
        lines.append(f"  {voice:<24} tokens={v['tokens']} "
                     f"per_confirmed={v.get('cost_per_confirmed', '-')}")
    return "\n".join(lines)


# -----------------------------------------------------------------------------
# routing
# -----------------------------------------------------------------------------

def cmd_routing(args: argparse.Namespace) -> int:
    if not args.layer_map:
        print("INCOMPLETE: routing needs --layer-map; the cheapest-capable "
              "layer cannot be inferred from a field run (see M3)",
              file=sys.stderr)
        return 3
    try:
        lm = _load_json(args.layer_map)
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: cannot read layer-map: {e}", file=sys.stderr)
        return 2
    if not isinstance(lm, dict):
        print("ERROR: layer-map must be an object", file=sys.stderr)
        return 2

    order = lm.get("order", DEFAULT_LAYER_ORDER)
    if not isinstance(order, list) or not order:
        print("ERROR: layer-map 'order' must be a non-empty list",
              file=sys.stderr)
        return 2
    rank = {name: i for i, name in enumerate(order)}

    defects = lm.get("defects")
    if not isinstance(defects, list) or not defects:
        print("INCOMPLETE: layer-map has no defects to score", file=sys.stderr)
        return 3

    scored = []
    misses = []
    for d in defects:
        if not isinstance(d, dict):
            print("ERROR: each defect must be an object", file=sys.stderr)
            return 2
        cheapest = d.get("cheapest_capable")
        actual = d.get("actual_caught")
        did = d.get("id", "?")
        if cheapest is None or actual is None:
            print(f"INCOMPLETE: defect {did!r} missing cheapest_capable or "
                  f"actual_caught", file=sys.stderr)
            return 3
        if cheapest not in rank or actual not in rank:
            print(f"ERROR: defect {did!r} names a layer not in order "
                  f"(cheapest={cheapest!r}, actual={actual!r})",
                  file=sys.stderr)
            return 2
        at_or_below = rank[actual] <= rank[cheapest]
        scored.append({"id": did, "cheapest_capable": cheapest,
                       "actual_caught": actual, "at_or_below": at_or_below})
        if not at_or_below:
            misses.append(did)

    routing = round(sum(1 for s in scored if s["at_or_below"]) / len(scored), 4)
    report = {
        "metric": "cheapest-capable-layer-routing",
        "order": order,
        "n_defects": len(scored),
        "routing_fraction": routing,
        "routing_misses": misses,
        "per_defect": scored,
    }
    _emit(report, args.json, _fmt_routing)
    return 0


def _fmt_routing(r: dict) -> str:
    lines = [f"cheapest-capable-layer routing over {r['n_defects']} defect(s)",
             f"  routing fraction: {r['routing_fraction']}",
             f"  routing misses:   {r['routing_misses'] or 'none'}"]
    for d in r["per_defect"]:
        mark = "ok" if d["at_or_below"] else "MISS"
        lines.append(f"  [{mark:>4}] {d['id']}: cheapest={d['cheapest_capable']}"
                     f" actual={d['actual_caught']}")
    return "\n".join(lines)


# -----------------------------------------------------------------------------

def _emit(report: dict, as_json: bool, fmt) -> None:
    if as_json:
        print(json.dumps(report, indent=2))
    else:
        print(fmt(report))


def main() -> int:
    ap = argparse.ArgumentParser(description="M2 self-measurement aggregator")
    sub = ap.add_subparsers(dest="cmd", required=True)

    py = sub.add_parser("yield")
    py.add_argument("--findings", required=True, type=Path)
    py.add_argument("--run", type=Path, default=None)
    py.add_argument("--json", action="store_true")
    py.set_defaults(func=cmd_yield)

    pc = sub.add_parser("cost")
    pc.add_argument("--events", required=True, type=Path)
    pc.add_argument("--findings", type=Path, default=None)
    pc.add_argument("--json", action="store_true")
    pc.set_defaults(func=cmd_cost)

    pr = sub.add_parser("routing")
    pr.add_argument("--findings", type=Path, default=None)
    pr.add_argument("--layer-map", type=Path, default=None)
    pr.add_argument("--json", action="store_true")
    pr.set_defaults(func=cmd_routing)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
