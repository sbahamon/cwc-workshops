# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0
"""viewer.py renders on the stubs and on the reference solution, shows checkpoint 5's numbers,
finds checkpoint 2's rows, and never writes into results/. Streamlit isn't a project
dependency (it would change uv.lock and the harness sha), so these skip under plain
`uv run pytest`. Run them with:

    uv run --with streamlit==1.65.0 pytest tests/test_viewer.py
"""
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

import checkpoint  # noqa: E402

EVALS = Path(__file__).resolve().parents[1]
VIEWER = str(EVALS / "viewer.py")


def app() -> AppTest:
    return AppTest.from_file(VIEWER, default_timeout=60)


def text(at: AppTest) -> str:
    return "\n".join(m.value for m in [*at.markdown, *at.caption, *at.warning, *at.info])


def stubs_done() -> bool:
    grading, _ = checkpoint.lab("grading", False)
    try:
        checkpoint.call(grading.grade_root_cause, checkpoint.REAL_OPUS, checkpoint.DEPLOY)
        return True
    except checkpoint.NotDone:
        return False


def test_stubs_render_not_done_yet():
    at = app().run()
    assert not at.exception
    if not stubs_done():
        assert any("not done yet" in w.value for w in at.warning)


def test_reference_shows_checkpoint_5():
    at = app().run()
    at.toggle(key="solution").set_value(True).run()
    assert not at.exception
    grading, _ = checkpoint.lab("grading", True)
    cost, _ = checkpoint.lab("cost", True)
    stats, n, rc_same, usd_same = checkpoint.path_stats(grading, cost)
    assert f"match the recorded ones on **{rc_same}/{n}** rows" in text(at)
    assert f"rate card on **{usd_same}/{n}**" in text(at)
    path_table = next(d for d in at.dataframe if len(d.value) == len(checkpoint.path_cells()))
    assert list(path_table.value["cell"]) == [c["cell"] for c in checkpoint.path_cells()]


def test_e2e_filter_finds_checkpoint_2_rows():
    at = app().run()
    at.toggle(key="solution").set_value(True).run()
    at.selectbox(key="cell").set_value("ladder/v1").run()
    at.radio(key="filter").set_value("e2e.py fails a correct answer").run()
    assert not at.exception
    shown = int(next(c.value for c in at.caption if c.value.endswith(" rows")).split()[0])
    assert shown >= 1


def test_viewer_never_writes_results():
    before = {p: p.stat().st_mtime_ns for p in checkpoint.RESULTS.rglob("*")}
    at = app().run()
    at.toggle(key="solution").set_value(True).run()
    assert not at.exception
    after = {p: p.stat().st_mtime_ns for p in checkpoint.RESULTS.rglob("*")}
    assert before == after
