# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0
"""
The cost-reduction path chart, in the style of Fig. 8 of the claude.dev post
"Automating eval design and hillclimbing with Claude" (the same look as viewer.py's chart).

    uv run --with matplotlib==3.10.0 python plot_path.py

matplotlib is pulled in for this command only (`--with`), so it never enters
uv.lock and doesn't change the runner's harness sha.

x = mean rate-card cost per incident (log scale): published per-token prices plus
    $0.08/session-hour runtime, which is what the Oct 14 Console bill followed
    (SOURCES.md, Haiku 5.5 billing check).
y = root_cause accuracy on train+test, with 95% Wald CI bars
Adopted path (filled, numbered, linked by dashed arrows): baseline -> each walk cell kept ->
each kept hillclimb round, in _state.json order. Every other visited cell (including the
round-0 diagnostic) is a hollow point, listed with its reason under the chart. A dashed
line marks the pre-registered floor. Every number is read from results.jsonl via
walk.cell(); nothing is typed in.

Writes results/path.svg and results/path.png.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.patheffects as pe  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

from walk import LADDER, cell  # noqa: E402

EVALS = Path(__file__).parent
OUT = EVALS / "results"
NAMES = {"claude-opus-4-8": "Opus 4.8", "claude-sonnet-5-5": "Sonnet 5.5", "claude-haiku-5-5": "Haiku 5.5"}
X = "rate_card_per_incident"  # x axis
# The claude.dev figure palette (light theme); viewer.py uses the same values.
INK, MUTED, BG, ACCENT = "#141413", "#65645e", "#faf9f5", "#c15f3c"
LINE, LINE_SOFT = (0.078, 0.078, 0.075, 0.22), (0.078, 0.078, 0.075, 0.11)
HALO = [pe.withStroke(linewidth=3, foreground=BG)]
FONTS = ["Arial", "Helvetica", "DejaVu Sans"]  # Arial first: it ships a bold weight on macOS and Windows


def cents(usd: float) -> str:
    return f"{usd * 100:.2f}¢"


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


def effort(e: dict, c: dict) -> str:
    return e.get("effort") or "/".join(c["effort_echoed"])


def why_not(e: dict, c: dict, need: float, fmt_min: float) -> str:
    """Why a visited cell isn't on the path, from its own numbers."""
    if e.get("role") == "diagnostic":
        return "diagnostic, off the path by design"
    fails = ([f"root cause {c['root_cause_tt']:.1%}"] if c["root_cause_tt"] < need - 1e-9 else []) + \
            ([f"format {c['format']:.1%}"] if c["format"] < fmt_min - 1e-9 else [])
    return "fails " + ", ".join(fails) if fails else "not adopted"


def plot(flow: Path = LADDER, out_dir: Path = OUT) -> list[Path]:
    pts = points(flow)
    if not pts:
        raise SystemExit("no walk cells with rows yet")
    floor = json.loads((flow / "_state.json").read_text())["floor"]
    base = next(c for e, c in pts if e["variant"] == "baseline")
    need = base["root_cause_tt"] - floor["root_cause_train_test_within_points_of_baseline"] / 100
    adopted = [(e, c) for e, c in pts if e.get("adopted")]
    others = [(e, c) for e, c in pts if not e.get("adopted")]

    plt.rcParams.update({"font.family": "sans-serif", "font.sans-serif": FONTS, "svg.fonttype": "path"})
    fig = plt.figure(figsize=(8.8, 6.5), dpi=150, facecolor=BG)
    ax = fig.add_axes((0.09, 0.29, 0.88, 0.56), facecolor=BG)

    # axes: horizontal gridlines only, a baseline rule, log cost ticks in cents
    xs = [c[X] for _, c in pts]
    lo_x, hi_x = min(xs) / 1.6, max(xs) * 1.6
    ax.set_xscale("log")
    ax.set_xlim(lo_x, hi_x)
    low = min(min(c["root_cause_tt"] - c["root_cause_tt_hw"] for _, c in pts), need)
    ymin = min(5 * math.floor((100 * low - 1) / 5), 95) / 100
    ax.set_ylim(ymin, 1.0 + 0.012)
    yt = [v / 100 for v in range(round(100 * ymin), 101, 5)]
    ax.set_yticks(yt, [f"{round(100 * v)}%" for v in yt])
    xt = [t / 100 for t in (0.25, 0.5, 1, 2, 4, 8, 16, 32, 64) if lo_x <= t / 100 <= hi_x]
    ax.set_xticks(xt, [f"{100 * t:g}¢" for t in xt])
    ax.xaxis.set_minor_locator(matplotlib.ticker.NullLocator())
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(LINE)
    ax.tick_params(axis="y", length=0, labelsize=9, labelcolor=MUTED, pad=6)
    ax.tick_params(axis="x", length=4, color=LINE, labelsize=9, labelcolor=MUTED)
    for v in yt:
        ax.axhline(v, color=LINE_SOFT, linewidth=0.8, zorder=0)
    ax.set_xlabel("Cost per incident at the rate card, log scale", color=MUTED, fontsize=10, labelpad=8)
    ax.set_ylabel("Root cause, train + test (95% CI)", color=MUTED, fontsize=10, labelpad=8)

    # the pre-registered floor
    ax.axhline(need, color=LINE, linewidth=1, linestyle=(0, (1.5, 3)), dash_capstyle="round", zorder=1)
    ax.annotate("Floor", (0, need), xycoords=("axes fraction", "data"), xytext=(6, 4), textcoords="offset points",
                fontsize=9, color=MUTED, path_effects=HALO)

    # every other visited cell: hollow, with its CI
    for e, c in others:
        p_, hw = c["root_cause_tt"], c["root_cause_tt_hw"]
        ax.errorbar(c[X], p_, yerr=[[min(hw, p_)], [min(hw, 1 - p_)]], fmt="o", markersize=6, mfc=BG, mec=MUTED,
                    mew=1, ecolor=MUTED, elinewidth=0.8, capsize=2.5, zorder=2)

    # the path: dashed arrows with a solid head, shortened so they don't touch the dots
    to_px, to_data = ax.transData.transform, ax.transData.inverted().transform
    pt = fig.dpi / 72
    for (_, a), (_, b) in zip(adopted, adopted[1:]):
        (x0, y0), (x1, y1) = to_px((a[X], a["root_cause_tt"])), to_px((b[X], b["root_cause_tt"]))
        d = math.hypot(x1 - x0, y1 - y0) or 1
        ux, uy = (x1 - x0) / d, (y1 - y0) / d
        start, end = (x0 + 8 * pt * ux, y0 + 8 * pt * uy), (x1 - 8 * pt * ux, y1 - 8 * pt * uy)
        ax.annotate("", to_data(end), to_data(start), arrowprops=dict(arrowstyle="-", color=MUTED, linewidth=0.9,
                    linestyle=(0, (4, 3)), shrinkA=0, shrinkB=0), zorder=2)
        ax.annotate("", to_data(end), to_data((end[0] - 6 * pt * ux, end[1] - 6 * pt * uy)),
                    arrowprops=dict(arrowstyle="->,head_length=0.45,head_width=0.28", color=MUTED, linewidth=0.9,
                                    shrinkA=0, shrinkB=0), zorder=2)

    # the path: dot with CI, numbered badge, two-line label placed clear of earlier labels
    right_edge = to_px((hi_x, 1.0))[0] / pt
    placed: list[tuple[float, float, float, float]] = []
    for n, (e, c) in enumerate(adopted, 1):
        p_, hw = c["root_cause_tt"], c["root_cause_tt_hw"]
        ax.errorbar(c[X], p_, yerr=[[min(hw, p_)], [min(hw, 1 - p_)]], fmt="o", markersize=6.5, mfc=ACCENT,
                    mec=BG, mew=1, ecolor=ACCENT, elinewidth=0.9, capsize=2.5, zorder=4)
        name = f"{NAMES.get(e['model'], e['model'])}, {effort(e, c)} effort"
        what = ("Baseline" if e["variant"] == "baseline" and not e.get("prompt")
                else ("Climbed prompt" if e.get("prompt") else "Shipped prompt")) + f", {p_:.1%} at {cents(c[X])}"
        wide = 24 + max(0.58 * 10.5 * len(name), 0.52 * 9 * len(what))  # rough width, points
        px, py = (v / pt for v in to_px((c[X], p_)))
        left = px + 12 + wide > right_edge
        x0, x1 = (px - 12 - wide, px - 6) if left else (px + 6, px + 12 + wide)
        dy = -24
        while any(max(x0, a0) < min(x1, a1) and max(py + dy - 16, b0) < min(py + dy + 9, b1) for a0, b0, a1, b1 in placed):
            dy -= 32  # move down until clear
        placed.append((x0, py + dy - 16, x1, py + dy + 9))
        bdx = -12 if left else 12
        ax.annotate(str(n), (c[X], p_), xytext=(bdx, dy), textcoords="offset points", ha="center", va="center",
                    fontsize=8, fontweight="medium", color=INK, zorder=5,
                    bbox=dict(boxstyle="circle,pad=0.28", fc=BG, ec=INK, lw=0.8))
        tdx, ha = (bdx - 10, "right") if left else (bdx + 10, "left")
        ax.annotate(name, (c[X], p_), xytext=(tdx, dy + 1), textcoords="offset points", ha=ha, va="center",
                    fontsize=10.5, fontweight="medium", color=INK, path_effects=HALO, zorder=5)
        ax.annotate(what, (c[X], p_), xytext=(tdx, dy - 12), textcoords="offset points", ha=ha, va="center",
                    fontsize=9, color=MUTED, path_effects=HALO, zorder=5)

    # title block, as the post's figure header; then the key to the hollow points
    ns = sorted({c["n_tt"] for _, c in pts})
    n = f"{ns[0]}" if len(ns) == 1 else f"{ns[0]}–{ns[-1]}"
    fig.text(0.02, 0.955, "The cost-reduction path", fontsize=13, fontweight="bold", color=INK, va="top")
    fig.text(0.02, 0.915, f"{len(adopted)} configurations along the adopted path · {n} train+test runs per cell",
             fontsize=10, color=MUTED, va="top")
    key = ["Hollow points were visited but not adopted:"] + [
        f"{e['variant']}  {NAMES.get(e['model'], e['model'])}, {effort(e, c)} effort, {cents(c[X])}: "
        f"{why_not(e, c, need, floor['format_min'])}" for e, c in sorted(others, key=lambda ec: ec[1][X])]
    fig.text(0.09, 0.165, "\n".join(key), fontsize=8.5, color=MUTED, va="top", linespacing=1.6)

    out_dir.mkdir(parents=True, exist_ok=True)
    paths = [out_dir / "path.svg", out_dir / "path.png"]
    for p in paths:
        fig.savefig(p, facecolor=BG)
    return paths


if __name__ == "__main__":
    for p in plot():
        print(f"wrote {p.relative_to(EVALS)}")
