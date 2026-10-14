# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0
"""
The cost-reduction path chart (modeled on Fig. 8 of the claude.dev post
"Automating eval design and hillclimbing with Claude").

    uv run --with matplotlib==3.10.0 python plot_path.py

matplotlib is pulled in for this command only (`--with`), so it never enters
uv.lock and doesn't change the runner's harness sha.

x = mean rate-card cost per incident (log scale): published per-token prices plus
    $0.08/session-hour runtime, which is what the Oct 14 Console bill followed
    (SOURCES.md, Haiku 5.5 billing check). Each label also gives list_cost, the
    session-reported cost the $50 spend cap is enforced on.
y = root_cause accuracy on train+test, with 95% Wald CI bars
Adopted path (numbered, dashed arrows): baseline -> each walk cell kept -> each
kept hillclimb round, in _state.json order. Unadopted cells (including the
round-0 diagnostic) are grey and unconnected. A dashed line marks the starting
accuracy. Every
number is read from results.jsonl via walk.cell(); nothing is typed in.

Writes results/path.svg and results/path.png.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from walk import LADDER, cell  # noqa: E402

EVALS = Path(__file__).parent
OUT = EVALS / "results"
NAMES = {"claude-opus-4-8": "Opus 4.8", "claude-sonnet-5-5": "Sonnet 5.5", "claude-haiku-5-5": "Haiku 5.5"}
X = "rate_card_per_incident"  # x axis; list_cost goes in the labels
INK, MUTED, GRID, ACCENT = "#1f2328", "#9aa0a6", "#e6e8eb", "#c2410c"


def cents(usd: float) -> str:
    c = usd * 100
    return f"{c:.1f}¢" if c < 10 else f"{c:.0f}¢"


def label(entry: dict, c: dict) -> str:
    """Two lines: which cell, then accuracy, both costs, and the floor verdict."""
    model = NAMES.get(entry["model"], entry["model"])
    eff = entry.get("effort") or f"default ({'/'.join(c['effort_echoed'])})"
    line2 = (f"{c['root_cause_tt']:.1%} at {cents(c[X])}"
             f" ({cents(c['list_per_incident'])} list_cost) · format {c['format']:.0%}")
    role = entry.get("role")
    if entry.get("prompt"):
        eff = f"{eff} effort, {entry['prompt']}"
        return f"{model}, {eff} — {'kept' if entry.get('adopted') else 'not kept'}\n{line2}"
    tag = {"baseline": "baseline", "diagnostic": "round-0 diagnostic (off path)"}.get(role)
    if tag is None:
        tag = "kept" if entry.get("adopted") else "fails floor: " + entry.get("verdict", "").split("(")[-1].split(";")[0].rstrip(")")
    return f"{model}, {eff} effort — {tag}\n{line2}"


def points(flow: Path = LADDER) -> list[tuple[dict, dict]]:
    """Ladder walk cells and climb rounds, in path order: the ladder walk up to the climb's
    target, then each climb round (prompt "climbed prompt rN"), then walk cells run with a
    climbed prompt (walk entries carrying "prompt")."""
    state = json.loads((flow / "_state.json").read_text())
    out = []
    walk = state.get("walk", [])
    for entry in [e for e in walk if not e.get("prompt")]:
        c = cell(entry["variant"], flow)
        if c["rows"]:
            out.append((entry, c))
    climb = flow.parent / "climb"
    if (climb / "_state.json").exists():
        cst = json.loads((climb / "_state.json").read_text())
        for i, r in enumerate(cst.get("rounds", []), start=1):
            c = cell(r["variant"], climb)
            if c["rows"]:
                e = {"variant": r["variant"], "model": cst["target"]["model"], "effort": cst["target"]["effort"],
                     "prompt": f"climbed prompt r{i}", "adopted": str(r.get("kept", "")).startswith("kept")}
                out.append((e, c))
    for entry in [e for e in walk if e.get("prompt")]:
        c = cell(entry["variant"], flow)
        if c["rows"]:
            out.append((entry, c))
    return out


def plot(flow: Path = LADDER, out_dir: Path = OUT) -> list[Path]:
    pts = points(flow)
    if not pts:
        raise SystemExit("no walk cells with rows yet")
    fig, ax = plt.subplots(figsize=(11, 6.4), dpi=150)
    ax.set_xscale("log")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.grid(True, which="both", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)

    base = next(c for e, c in pts if e["variant"] == "baseline")
    ax.axhline(base["root_cause_tt"], color=MUTED, linestyle="--", linewidth=1)
    ax.text(min(c[X] for _, c in pts) / 1.55, base["root_cause_tt"] + 0.003,
            "starting accuracy", color=MUTED, fontsize=8, va="bottom")

    adopted = [(e, c) for e, c in pts if e.get("adopted")]
    others = [(e, c) for e, c in pts if not e.get("adopted")]
    # Labels go in a fixed column at the right, cheapest at the bottom, each tied to its point
    # by a leader line, so cells with the same accuracy or nearly the same cost never collide.
    order = sorted(pts, key=lambda ec: ec[1][X])
    for i, (e, c) in enumerate(order):
        on_path = bool(e.get("adopted"))
        color = ACCENT if on_path else MUTED
        p_, hw = c["root_cause_tt"], c["root_cause_tt_hw"]
        yerr = [[min(hw, p_)], [min(hw, 1 - p_)]]  # a proportion's CI can't leave [0, 1]
        ax.errorbar(c[X], p_, yerr=yerr, fmt="o", color=color, ecolor=color,
                    elinewidth=1.2, capsize=3, markersize=7 if on_path else 6, zorder=3 if on_path else 2)
        ax.annotate(label(e, c), (c[X], p_), xycoords="data",
                    xytext=(0.60, 0.06 + i * (0.80 / max(1, len(order) - 1))), textcoords="axes fraction",
                    fontsize=7.5, color=INK if on_path else MUTED, va="center",
                    arrowprops=dict(arrowstyle="-", color=GRID, linewidth=0.8, shrinkA=2, shrinkB=4))
    for i, (e, c) in enumerate(adopted, start=1):
        ax.annotate(f"{i}", (c[X], c["root_cause_tt"]), xytext=(-4, 7),
                    textcoords="offset points", fontsize=9, fontweight="bold", color=ACCENT)
    for (e0, c0), (e1, c1) in zip(adopted, adopted[1:]):
        ax.annotate("", xy=(c1[X], c1["root_cause_tt"]),
                    xytext=(c0[X], c0["root_cause_tt"]),
                    arrowprops=dict(arrowstyle="->", linestyle="--", color=ACCENT, linewidth=1.2), zorder=1)

    xs = [c[X] for _, c in pts]
    ax.set_xlim(min(xs) / 1.6, max(xs) * 14)
    lo = min(c["root_cause_tt"] - c["root_cause_tt_hw"] for _, c in pts)
    ax.set_ylim(max(0.0, lo - 0.02 - 0.012 * len(pts)), 1.02)
    ax.set_yticks([t for t in ax.get_yticks() if t <= 1.0 + 1e-9])
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: cents(v)))
    ax.set_xlabel("mean cost per incident at the rate card (log scale; labels also give list_cost, which the spend cap uses)", color=INK)
    ax.set_ylabel("root-cause accuracy, train + test (95% CI)", color=INK)
    n = base["n_tt"]
    ax.set_title(f"SRE agent: root-cause accuracy vs cost per incident ({n} train+test runs per cell; "
                 f"floor: within 10 pts of baseline, format ≥ 95%)", color=INK, fontsize=10.5, loc="left")
    fig.tight_layout()
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = [out_dir / "path.svg", out_dir / "path.png"]
    for p in paths:
        fig.savefig(p)
    return paths


if __name__ == "__main__":
    for p in plot():
        print(f"wrote {p.relative_to(EVALS)}")
