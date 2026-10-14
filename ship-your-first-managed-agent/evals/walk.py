# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0
"""
Evaluate ladder cells against the pre-registered floor (docs/plan.md C0.3).

    uv run python walk.py                  # every cell in hillclimb/ladder/
    uv run python walk.py v1 --json        # one cell, machine-readable

Reads only results.jsonl / errors.jsonl / _state.json; every number is computed
from the rows. Floor (pre-registered 2026-10-13, reg-verbatim clause clarified
2026-10-14 before any ladder result):
  - root_cause mean on train+test >= baseline's train+test mean - 0.10
  - every reg-verbatim rep has root_cause == 1
  - format mean over all of the cell's rows >= 0.95
"Within noise of the floor" = the floor value lies inside the cell's 95% Wald CI
on train+test root_cause (the cell then gets 2 more reps before its verdict).
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

EVALS = Path(__file__).parent
LADDER = EVALS / "hillclimb" / "ladder"


def rows(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()] if path.exists() else []


def prop(xs: list[int]) -> tuple[float | None, float | None, int]:
    n = len(xs)
    if not n:
        return None, None, 0
    p = sum(xs) / n
    return p, 1.96 * math.sqrt(p * (1 - p) / n), n


def cell(variant: str, flow: Path = LADDER) -> dict:
    vdir = flow / variant
    ok, errs = rows(vdir / "results.jsonl"), rows(vdir / "errors.jsonl")
    done = {(r["prompt_id"], r["rep"]) for r in ok}
    open_errs = [e for e in errs if (e["prompt_id"], e["rep"]) not in done]
    tt = [r for r in ok if "train" in r["tags"] or "test" in r["tags"]]
    split = lambda s: [r["grade"]["root_cause"] for r in ok if s in r["tags"]]
    verb = [r["grade"]["root_cause"] for r in ok if r["prompt_id"] == "reg-verbatim"]
    rc, rc_hw, n_tt = prop([r["grade"]["root_cause"] for r in tt])
    fmt, fmt_hw, n_all = prop([r["grade"]["format"] for r in ok])
    lst = [r["list_cost_usd"] for r in ok]
    card = [r["rate_card_usd"] for r in ok if r.get("rate_card_usd") is not None]
    models = sorted({r["model"] for r in ok})
    efforts = sorted({str(r["meta"].get("effort_echoed")) for r in ok})
    summ = json.loads((vdir / "summary.json").read_text()) if (vdir / "summary.json").exists() else {}
    return {
        "variant": variant, "label": summ.get("label"), "models": models, "effort_echoed": efforts,
        "rows": len(ok), "attempts": len(ok) + len(errs), "errors": len(errs), "open_errors": len(open_errs),
        "error_rate": len(errs) / (len(ok) + len(errs)) if ok or errs else 0.0,
        "error_classes": sorted({e["class"] for e in errs}),
        "root_cause_tt": rc, "root_cause_tt_hw": rc_hw, "n_tt": n_tt,
        "root_cause_all": prop([r["grade"]["root_cause"] for r in ok])[0],
        "by_split": {s: prop(split(s))[:2] for s in ("train", "test", "val")},
        "format": fmt, "format_hw": fmt_hw, "n": n_all,
        "reg_verbatim": verb,
        "list_per_incident": sum(lst) / len(lst) if lst else None,
        "rate_card_per_incident": sum(card) / len(card) if card else None,
        "list_total": sum(lst) + sum(e.get("list_cost_usd") or 0 for e in errs),
        "deploys_first": prop([int(bool(r["meta"].get("deploys_before_first_log_access"))) for r in ok])[0],
        "latency_s": sum(r["latency_s"] for r in ok) / len(ok) if ok else None,
        "tool_calls": sum(r["tool_calls"] for r in ok) / len(ok) if ok else None,
    }


def verdict(c: dict, base: dict, floor: dict) -> dict:
    """Pass/fail against the floor, with the reasons and whether it's within noise."""
    need = base["root_cause_tt"] - floor["root_cause_train_test_within_points_of_baseline"] / 100
    checks = {
        "root_cause": c["root_cause_tt"] is not None and c["root_cause_tt"] >= need - 1e-9,
        "reg_verbatim": bool(c["reg_verbatim"]) and all(v == 1 for v in c["reg_verbatim"]),
        "format": c["format"] is not None and c["format"] >= floor["format_min"] - 1e-9,
    }
    lo, hi = c["root_cause_tt"] - c["root_cause_tt_hw"], c["root_cause_tt"] + c["root_cause_tt_hw"]
    return {"pass": all(checks.values()), "checks": checks, "root_cause_needed": need,
            "within_noise": lo <= need <= hi}


def fmt_pct(p, hw=None):
    if p is None:
        return "n/a"
    return f"{p:.1%}" + (f" ± {hw:.1%}" if hw is not None else "")


def main(argv: list[str]) -> None:
    state = json.loads((LADDER / "_state.json").read_text())
    variants = [a for a in argv if not a.startswith("--")] or sorted(
        (d.name for d in LADDER.iterdir() if d.is_dir() and (d.name == "baseline" or d.name[1:].isdigit())),
        key=lambda v: -1 if v == "baseline" else int(v[1:]))
    base = cell("baseline")
    out = []
    for v in variants:
        c = cell(v)
        c["verdict"] = None if v == "baseline" or base["rows"] == 0 else verdict(c, base, state["floor"])
        out.append(c)
    if "--json" in argv:
        print(json.dumps(out, indent=2))
        return
    for c in out:
        vd = c["verdict"]
        print(f"{c['variant']:8s} {c['label'] or '':28s} rows {c['rows']:3d}  err {c['errors']}  "
              f"root_cause(tt) {fmt_pct(c['root_cause_tt'], c['root_cause_tt_hw'])}  format {fmt_pct(c['format'], c['format_hw'])}  "
              f"verbatim {c['reg_verbatim']}  list ${c['list_per_incident'] or 0:.4f}  card ${c['rate_card_per_incident'] or 0:.4f}"
              + (f"  -> {'PASS' if vd['pass'] else 'FAIL'} {vd['checks']} need {vd['root_cause_needed']:.1%}"
                 f"{' (within noise)' if vd['within_noise'] else ''}" if vd else ""))


if __name__ == "__main__":
    main(sys.argv[1:])
