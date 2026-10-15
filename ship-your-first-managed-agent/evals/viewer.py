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

import altair as alt  # noqa: E402  (ships with streamlit)
import streamlit as st  # noqa: E402

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

        points = [dict(r, kind="adopted" if r["#"] else ("reference" if r["floor"] == "reference" else
                                                         "pass" if r["floor"].startswith("pass") else "fail"))
                  for r in table]
        enc = dict(x=alt.X("¢/incident:Q", scale=alt.Scale(type="log"), title="¢ per incident (rate card, log)"),
                   y=alt.Y("root cause:Q", scale=alt.Scale(zero=False), title="root cause, train+test (%)"))
        dots = alt.Chart(alt.Data(values=points)).mark_circle(size=120).encode(
            **enc, color=alt.Color("kind:N", title=""), tooltip=["cell:N", "model, effort, prompt:N", "floor:N"])
        labels = alt.Chart(alt.Data(values=[p for p in points if p["#"]])).mark_text(dy=-12).encode(**enc, text="#:N")
        st.altair_chart(dots + labels, width="stretch")

    st.image(str(checkpoint.RESULTS / "path.png"), caption="The recorded chart (plot_path.py), with confidence intervals")

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
