# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0
"""The lab (Phase 9): the reference solution reproduces every recorded grade and cost, every
checkpoint prints exactly the expected output in README.md, and results/ is an up-to-date
snapshot that spend.py doesn't count twice. Offline; no API key."""
import importlib
import json
import re
import sys
from pathlib import Path

import pytest

import checkpoint
import snapshot
import spend
from cases import load_answer, load_cases
from generate import write
from graders import grade_root_cause
from pricing import _CARD, _HAIKU_OVER_TIER, session_usd
from specs import SPECS, split_of

EVALS = Path(__file__).resolve().parents[1]
README = EVALS / "README.md"
BLOCK = re.compile(r"<!-- expected-output: checkpoint (\d) -->\n```text\n(.*?)\n```", re.S)


@pytest.fixture(scope="module")
def answers(tmp_path_factory):
    root = tmp_path_factory.mktemp("cases")
    for sc in SPECS:
        write(sc, split_of(sc), root=root)
    return {c.id: load_answer(c) for c in load_cases(root=root)}


@pytest.fixture(scope="module")
def sessions():
    """[(cell, row, session)] for every recorded row in results/."""
    out = []
    for d in sorted(p.parent for p in checkpoint.RESULTS.rglob("rows.jsonl")):
        cell = d.relative_to(checkpoint.RESULTS).as_posix()
        out += [(cell, r, s) for r, s in checkpoint.recorded(cell)]
    return out


def test_snapshot_is_current():
    want = snapshot.build()
    for rel, data in want.items():
        assert (snapshot.OUT / rel).read_bytes() == data, f"results/{rel} is stale: run `uv run python snapshot.py`"
    on_disk = {p.relative_to(snapshot.OUT).as_posix() for p in snapshot.OUT.rglob("*") if p.is_file()}
    assert on_disk - set(want) == {"path.svg", "path.png"}


def test_snapshot_is_not_counted_as_spend():
    assert not [f for f in spend.ledger_files() if "results" in f.relative_to(EVALS).parts]


def test_reference_grader_matches_every_recorded_grade(sessions, answers):
    assert len(sessions) > 400
    for cell, row, s in sessions:
        a = answers[row["prompt_id"]]
        assert grade_root_cause(s["reply"], a) == row["grade"]["root_cause"], (cell, row["prompt_id"], row["rep"])
        assert checkpoint.lab("grading", True)[0].grade_root_cause(s["reply"], a) == row["grade"]["root_cause"]


def test_reference_cost_matches_the_rate_card(sessions):
    session_cost = checkpoint.lab("cost", True)[0].session_cost
    for cell, row, s in sessions:
        got = session_cost(row["model"], s["requests"], row["meta"]["active_seconds"])
        assert got == pytest.approx(session_usd(row["model"], s["requests"], row["meta"]["active_seconds"]), abs=1e-12)
        if row.get("rate_card_usd") is not None:  # rows from before pricing.py have none
            assert got == pytest.approx(row["rate_card_usd"], abs=5e-6), (cell, row["prompt_id"])


@pytest.mark.parametrize("pkg", ["lab", "lab_complete"])
def test_lab_rates_are_the_eval_rate_card(pkg):
    cost = importlib.import_module(f"{pkg}.cost")
    as_tuple = lambda r: (r["input"], r["cache_write"], r["cache_read"], r["output"])
    for model, rates in cost.RATES.items():
        inp, w5, _w1, hit, out = _CARD[model]
        assert as_tuple(rates) == (inp, w5, hit, out), model
    inp, w5, _w1, hit, out = _HAIKU_OVER_TIER
    assert as_tuple(cost.HAIKU_LONG_PROMPT) == (inp, w5, hit, out)
    assert set(cost.RATES) == set(_CARD)


def test_haiku_tier_is_per_request():
    session_cost = checkpoint.lab("cost", True)[0].session_cost
    small = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 60_000, "cache_creation_input_tokens": 0}
    # Two 60K-token requests: each under the tier, though their sum is over it.
    assert session_cost("claude-haiku-5-5", [small, small], 0) == pytest.approx(2 * 60_000 * 0.01 / 1e6)


@pytest.mark.parametrize("n", ["1", "2", "3", "4", "5"])
def test_checkpoint_output_is_what_the_readme_says(n, capsys):
    """The README's expected-output block is what a learner with a finished lab/ sees
    (the reference prints lab_complete/ where the learner's run prints lab/)."""
    blocks = dict(BLOCK.findall(README.read_text()))
    assert set(blocks) == set("12345")
    assert checkpoint.main([n, "--solution"]) == 0
    out = capsys.readouterr().out.replace("lab_complete/", "lab/").rstrip("\n")
    assert out == blocks[n], f"README.md checkpoint {n} block is out of date; paste the new output"


def test_stubs_are_unfinished_or_right(capsys):
    """lab/ ships as stubs. Once a learner fills them in, they must agree with the reference."""
    grading = importlib.import_module("lab.grading")
    try:
        grading.grade_root_cause("**Root cause:** `a3f9c21` — N+1.", checkpoint.DEPLOY)
    except NotImplementedError:
        assert checkpoint.main(["1"]) == 1
        assert "not done yet" in capsys.readouterr().out
    else:
        assert checkpoint.main(["1"]) == 0


def test_cell_swap_is_one_line():
    for pkg in ("lab", "lab_complete"):
        src = (EVALS / pkg / "cell.py").read_text()
        assert len([l for l in src.splitlines() if l.startswith("MODEL, EFFORT =")]) == 1
    cell = importlib.import_module("lab_complete.cell")
    assert (cell.MODEL, cell.EFFORT) == ("claude-haiku-5-5", "low")


def test_the_original_lab_keeps_its_shipped_prompt():
    sys.path.insert(0, str(EVALS.parent))
    import config
    climbed = (EVALS / "hillclimb" / "climb" / "v1" / "system.md").read_text()
    assert config.SYSTEM != climbed and "written once" not in config.SYSTEM
