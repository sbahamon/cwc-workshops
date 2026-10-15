# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0
"""
The recorded results in a browser, graded and priced by your code: checkpoint 5's table and
chart, plus every reply behind them. Read-only: it reads results/ and never calls the API.

    uv run --with streamlit==1.65.0 streamlit run viewer.py

Streamlit stays out of pyproject.toml on purpose: adding it would change uv.lock, and with
it the harness sha that run.py checks. Edit lab/grading.py or lab/cost.py, save, and the
page re-grades on the next rerun. The only write is the one checkpoint.answers() already
makes: it generates the gitignored cases/ once if it's missing.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import math  # noqa: E402
from html import escape  # noqa: E402

import streamlit as st  # noqa: E402
import streamlit.components.v1 as components  # noqa: E402

import checkpoint  # noqa: E402
from checkpoint import NAMES, NotDone, call  # noqa: E402
from graders import find_root_cause_line, grade_legacy_e2e  # noqa: E402

st.set_page_config(page_title="Eval results", layout="wide")


# ── recorded data: static, so cached ────────────────────────────────────
@st.cache_data
def answers() -> dict[str, dict]:
    return checkpoint.answers()


@st.cache_data
def recorded(cell: str) -> list[tuple[dict, dict]]:
    return checkpoint.recorded(cell)


@st.cache_data
def ladder_state() -> dict:
    return checkpoint.state("ladder")


@st.cache_data
def path_cells() -> list[dict]:
    return checkpoint.path_cells()


def pilot_cells() -> list[str]:
    return sorted(f"pilot/{d.name}" for d in (checkpoint.RESULTS / "pilot").iterdir()
                  if (d / "rows.jsonl").exists())


# ── your code: reloaded every run, never cached ─────────────────────────
def load(name: str, solution: bool):
    mod, where = checkpoint.lab(name, solution)
    return importlib.reload(mod), where


def maybe(fn, *args):
    """fn(*args), or None while the function is still a stub."""
    try:
        return call(fn, *args)
    except NotDone:
        return None


def not_done(e: NotDone, n: int) -> None:
    st.warning(f"not done yet: {e}\n\n(or turn on the reference solution in the sidebar, "
               f"the same as `uv run python checkpoint.py {n} --solution`)")


# ── the path chart: the claude.dev hillclimbing figure's look, drawn as SVG ──
INK, MUTED, BG, ACCENT = "#141413", "#65645e", "#faf9f5", "#c15f3c"
LINE, LINE_SOFT = "#14141338", "#1414131c"
HALO = f'stroke="{BG}" stroke-width="3" stroke-linejoin="round" paint-order="stroke"'


def path_svg(stats: list[dict], need: float) -> str:
    """Root cause against ¢ per incident (log): the adopted path numbered and linked by dashed
    arrows, every other visited cell as a hollow point, and the pre-registered floor as a dashed line."""
    W, H, L, R, T, B = 660, 400, 68, 640, 32, 330
    cents = [c["cents"] for c in stats]
    lo, hi = math.log(min(cents) / 1.6), math.log(max(cents) * 1.6)
    ymin = min(5 * math.floor((100 * min(min(c["rc"] for c in stats), need) - 1) / 5), 95) / 100
    x = lambda c: L + (math.log(c) - lo) / (hi - lo) * (R - L)
    y = lambda v: B - (v - ymin) / (1 - ymin) * (B - T)
    out = [f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" xmlns="http://www.w3.org/2000/svg" '
           f'style="background:{BG};font-family:system-ui,-apple-system,sans-serif;'
           f'font-variant-numeric:tabular-nums;border-radius:8px">']
    for v in range(round(100 * ymin), 101, 5):  # gridlines
        out.append(f'<line x1="{L}" x2="{R}" y1="{y(v / 100):.1f}" y2="{y(v / 100):.1f}" stroke="{LINE_SOFT}"/>'
                   f'<text x="{L - 6}" y="{y(v / 100) + 4:.1f}" text-anchor="end" font-size="12" fill="{MUTED}">{v}%</text>')
    out.append(f'<line x1="{L}" x2="{R}" y1="{B}" y2="{B}" stroke="{LINE}"/>')
    for t in (0.25, 0.5, 1, 2, 4, 8, 16, 32, 64):  # log ticks
        if lo <= math.log(t) <= hi:
            out.append(f'<line x1="{x(t):.1f}" x2="{x(t):.1f}" y1="{B}" y2="{B + 5}" stroke="{LINE}"/>'
                       f'<text x="{x(t):.1f}" y="{B + 20}" text-anchor="middle" font-size="12" fill="{MUTED}">{t:g}¢</text>')
    out.append(f'<text x="{(L + R) / 2}" y="{B + 50}" text-anchor="middle" font-size="13" fill="{MUTED}">'
               'Cost per incident at the rate card, log scale</text>'
               f'<text transform="translate(12 {(T + B) / 2}) rotate(-90)" text-anchor="middle" font-size="13" '
               f'fill="{MUTED}">Root cause, train + test</text>')
    out.append(f'<line x1="{L}" x2="{R}" y1="{y(need):.1f}" y2="{y(need):.1f}" stroke="{LINE}" '
               f'stroke-dasharray="3 4" stroke-linecap="round"/>'
               f'<text x="{L + 6}" y="{y(need) - 6:.1f}" font-size="12" fill="{MUTED}" {HALO}>Floor</text>')

    path = [c for c in stats if c.get("adopted")]
    for a, b in zip(path, path[1:]):  # dashed arrows, shortened so they don't touch the dots
        x1, y1, x2, y2 = x(a["cents"]), y(a["rc"]), x(b["cents"]), y(b["rc"])
        d = math.hypot(x2 - x1, y2 - y1) or 1
        ux, uy = (x2 - x1) / d, (y2 - y1) / d
        sx, sy, ex, ey = x1 + 10 * ux, y1 + 10 * uy, x2 - 10 * ux, y2 - 10 * uy
        head = [(ex - 6 * ux + 4 * s * uy, ey - 6 * uy - 4 * s * ux) for s in (1, -1)]
        out.append(f'<path d="M{sx:.1f} {sy:.1f} L{ex:.1f} {ey:.1f}" fill="none" stroke="{MUTED}" '
                   f'stroke-dasharray="4 3" stroke-linecap="round"/>'
                   f'<path d="M{head[0][0]:.1f} {head[0][1]:.1f} L{ex:.1f} {ey:.1f} L{head[1][0]:.1f} {head[1][1]:.1f}" '
                   f'fill="none" stroke="{MUTED}" stroke-linejoin="round" stroke-linecap="round"/>')
    for c in stats:  # visited, not adopted
        if not c.get("adopted"):
            tip = escape(f"{c['cell']}: {NAMES[c['model']]}, {c['effort'] or c['effort_echoed']}, "
                         f"{c['prompt']} prompt, {c['rc']:.1%} at {c['cents']:.2f}¢")
            out.append(f'<circle cx="{x(c["cents"]):.1f}" cy="{y(c["rc"]):.1f}" r="4" fill="{BG}" '
                       f'stroke="{MUTED}"><title>{tip}</title></circle>')
    placed: list[tuple[float, float, float, float]] = []  # label boxes so far
    for n, c in enumerate(path, 1):  # the path: dot, numbered badge, two-line label
        px, py = x(c["cents"]), y(c["rc"])
        name = f"{NAMES[c['model']]}, {c['effort'] or c['effort_echoed']} effort"
        what = "Baseline" if n == 1 else f"{c['prompt'].capitalize()} prompt"
        wide = 30 + 7.2 * max(len(name), len(what) + 18)  # rough text width
        left = px + 16 + wide > W  # right of the point unless it runs off the edge
        x0, x1 = (px - 16 - wide, px - 8) if left else (px + 8, px + 16 + wide)
        by = py + 30
        while any(max(x0, a0) < min(x1, a1) and max(by - 12, b0) < min(by + 28, b1) for a0, b0, a1, b1 in placed):
            by += 42  # move down until clear of earlier labels
        placed.append((x0, by - 12, x1, by + 28))
        bx = px + (-16 if left else 16)
        tx, anchor = bx + (-14 if left else 14), "end" if left else "start"
        out.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="4.5" fill="{ACCENT}" stroke="{BG}"/>'
                   f'<circle cx="{bx:.1f}" cy="{by:.1f}" r="8.5" fill="{BG}" stroke="{INK}"/>'
                   f'<text x="{bx:.1f}" y="{by + 4:.1f}" text-anchor="middle" font-size="11" font-weight="500" '
                   f'fill="{INK}">{n}</text>'
                   f'<text x="{tx:.1f}" y="{by + 5:.1f}" text-anchor="{anchor}" font-size="14" font-weight="500" '
                   f'fill="{INK}" {HALO}>{escape(name)}</text>'
                   f'<text x="{tx:.1f}" y="{by + 22:.1f}" text-anchor="{anchor}" font-size="12" fill="{MUTED}" '
                   f'{HALO}>{escape(what)}, {c["rc"]:.1%} at {c["cents"]:.2f}¢</text>')
    out.append("</svg>")
    return "".join(out)


solution = st.sidebar.toggle("Use the reference solution (lab_complete/)", key="solution")
grading, grading_at = load("grading", solution)
cost, cost_at = load("cost", solution)
cell_mod, cell_at = load("cell", solution)

st.sidebar.markdown("**Your code**")
for label, at, fn, args in (
        ("grade_root_cause", grading_at, grading.grade_root_cause, (checkpoint.REAL_OPUS, checkpoint.DEPLOY)),
        ("session_cost", cost_at, cost.session_cost, ("claude-opus-4-8", [], 0))):
    try:
        call(fn, *args)
        st.sidebar.markdown(f"`{label}` ({at}): done")
    except NotDone as e:
        st.sidebar.markdown(f"`{label}` ({at}): not done yet, {e}")
st.sidebar.markdown(f"cell ({cell_at}): `{cell_mod.MODEL}`, effort `{cell_mod.EFFORT or 'default'}`")
st.sidebar.caption("No live runs here. To run your cell for real (one session, about 2¢): "
                   "`uv run python checkpoint.py 4 --live`. Run one run.py at a time.")

st.title("Recorded results, graded by your code")
path_tab, cases_tab = st.tabs(["Path", "Cases"])

# ── Path: checkpoint 5 in a browser ─────────────────────────────────────
with path_tab:
    floor = ladder_state()["floor"]
    try:
        stats, rows_n, rc_same, usd_same = checkpoint.path_stats(grading, cost, answers())
    except NotDone as e:
        not_done(e, 5)
        stats = None
    if stats:
        base = stats[0]
        need = checkpoint.floor_need(base, floor)
        st.markdown(f"Floor, pre-registered: root cause on train+test ≥ {need:.1%} (baseline − 10 points), "
                    f"reg-verbatim right on every rep, format ≥ {floor['format_min']:.0%}.")
        table, step = [], 0
        for c in stats:
            step += bool(c.get("adopted"))
            table.append({
                "#": str(step) if c.get("adopted") else "",
                "cell": c["cell"],
                "floor": checkpoint.floor_verdict(c, base, need, floor),
                "model, effort, prompt": f"{NAMES[c['model']]}, {c['effort'] or c['effort_echoed']}, {c['prompt']}",
                "rows": c["rows"],
                "root cause": round(100 * c["rc"], 1),
                "format": round(100 * c["fmt"], 1),
                "verbatim": f"{sum(c['verb'])}/{len(c['verb'])}",
                "¢/incident": round(c["cents"], 2),
            })
        st.dataframe(table, width="stretch", hide_index=True, key="path_table")
        st.markdown(f"Your grades match the recorded ones on **{rc_same}/{rows_n}** rows; "
                    f"your costs match the recorded rate card on **{usd_same}/{rows_n}**.")

        st.markdown("##### The cost-reduction path")
        st.caption(f"{len([c for c in stats if c.get('adopted')])} configurations along the adopted path. "
                   "Hollow points were visited but not adopted; hover one for its cell.")
        components.html(f'<body style="margin:0">{path_svg(stats, need)}</body>', height=405)

    with st.expander("The recorded chart (plot_path.py), with 95% confidence intervals"):
        st.image(str(checkpoint.RESULTS / "path.png"))

# ── Cases: every reply behind the numbers ───────────────────────────────
with cases_tab:
    cells = [c["cell"] for c in path_cells()] + pilot_cells()
    cell = st.selectbox("Cell", cells, key="cell")
    keys = answers()
    rows = []
    for i, (row, s) in enumerate(recorded(cell)):
        a = keys[row["prompt_id"]]
        yours = maybe(grading.grade_root_cause, s["reply"], a)
        usd = maybe(cost.session_cost, row["model"], s["requests"], row["meta"]["active_seconds"])
        rows.append({
            "i": i, "case": row["prompt_id"], "rep": row["rep"], "tags": ", ".join(row["tags"]),
            "recorded rc": row["grade"]["root_cause"], "yours": yours,
            "e2e.py": grade_legacy_e2e(s["reply"], a["culprit_short"]) if a["kind"] == "deploy" else None,
            "format": row["grade"]["format"],
            "recorded $": row.get("rate_card_usd"), "your $": None if usd is None else round(usd, 6),
        })

    graded = rows and rows[0]["yours"] is not None
    if not graded:
        st.info("Your grade_root_cause isn't done yet, so the \"yours\" column is empty "
                "(checkpoint 1, or the reference solution in the sidebar).")
    deploy = [r for r in rows if r["e2e.py"] is not None]
    if graded and deploy:
        count = lambda old, new: sum((r["e2e.py"], r["yours"]) == (old, new) for r in deploy)
        st.markdown("**e2e.py's check next to yours** on this cell's deploy cases (checkpoint 2):")
        st.dataframe([{"": "e2e.py passes", "yours passes": count(1, 1), "yours fails": count(1, 0)},
                      {"": "e2e.py fails", "yours passes": count(0, 1), "yours fails": count(0, 0)}],
                     hide_index=True, key="two_by_two")

    show = st.radio("Show", ["all rows", "yours ≠ recorded", "e2e.py fails a correct answer"],
                    horizontal=True, key="filter", disabled=not graded)
    if graded and show == "yours ≠ recorded":
        rows = [r for r in rows if r["yours"] != r["recorded rc"]]
    elif graded and show == "e2e.py fails a correct answer":
        rows = [r for r in rows if (r["e2e.py"], r["yours"]) == (0, 1)]
    st.caption(f"{len(rows)} rows")
    st.dataframe(rows, width="stretch", hide_index=True, key="rows_table",
                 column_config={"i": None})

    if rows:
        pick = st.selectbox("Row", [r["i"] for r in rows], key="row",
                            format_func=lambda i: f"{recorded(cell)[i][0]['prompt_id']} rep {recorded(cell)[i][0]['rep']}")
        row, s = recorded(cell)[pick]
        a = keys[row["prompt_id"]]
        left, right = st.columns(2)
        with left:
            st.markdown("**Answer key**")
            st.json({k: a[k] for k in ("kind", "culprit_short", "culprit_service", "components") if k in a})
            st.markdown("**Root-cause line** (`find_root_cause_line`)")
            st.code(find_root_cause_line(s["reply"]) or "(none found)", language=None, wrap_lines=True)
        with right:
            st.markdown("**Cost, request by request** (your `session_cost`)")
            per = [maybe(cost.session_cost, row["model"], [req], 0) for req in s["requests"]]
            runtime = maybe(cost.session_cost, row["model"], [], row["meta"]["active_seconds"])
            if runtime is None:
                st.caption("session_cost isn't done yet (checkpoint 3).")
            else:
                st.dataframe([dict(request=n + 1, **req, usd=round(u, 6)) for n, (req, u) in enumerate(zip(s["requests"], per))]
                             + [{"request": "runtime", "usd": round(runtime, 6)}],
                             hide_index=True, key="per_request")
            st.caption(f"session `{row['meta'].get('session_id')}` · {row['meta'].get('console_url', '')}")
        st.markdown("**The agent's reply**, as the grader saw it")
        st.code(s["reply"], language=None, wrap_lines=True)
