# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0
"""The answer key is structurally out of the agent's reach.

The agent sees three things: the uploaded log, the three tool results, and the
prompts (system + user). None of them may expose answer.json.
"""
import json
import re
import sys
from pathlib import Path

import pytest

from cases import load_cases
from generate import write
from specs import SPECS, split_of
from tools import CaseTools

EVALS = Path(__file__).resolve().parents[1]
MARKERS = re.compile(r"culprit|root_cause|root cause|answer|\"components\"", re.I)


@pytest.fixture(scope="module")
def case_root(tmp_path_factory):
    root = tmp_path_factory.mktemp("cases")
    for sc in SPECS:
        write(sc, split_of(sc), root=root)
    return root


@pytest.fixture(scope="module")
def cases(case_root):
    return load_cases(root=case_root)


def test_only_the_log_is_uploaded(cases):
    for c in cases:
        assert CaseTools(c.dir).upload_paths() == [c.dir / "fixtures" / "app.log"]


def test_fixtures_hold_no_answer(cases):
    for c in cases:
        fixtures = c.dir / "fixtures"
        for p in fixtures.rglob("*"):
            assert "answer" not in p.name.lower()
            if p.is_file():
                hit = MARKERS.search(p.read_text())
                assert hit is None, f"{c.id}: {p.relative_to(c.dir)} contains {hit.group(0)!r}"


def test_tools_only_return_fixture_content(cases):
    probes = [
        ("get_recent_deploys", {}),
        ("get_metrics", {"service": "checkout", "metric": "p99_latency_ms"}),
        ("get_metrics", {"service": "../", "metric": "answer"}),
        ("get_metrics", {}),
        ("get_diff", {"commit": "../answer"}),
        ("get_diff", {"commit": "answer.json"}),
        ("get_diff", {"commit": "order_i"}),  # matched the old substring check
        ("get_diff", {}),
        ("read_file", {"path": "../answer.json"}),
    ]
    for c in cases:
        tools = CaseTools(c.dir)
        answer_text = (c.dir / "answer.json").read_text()
        deploys = json.loads((c.dir / "fixtures/deploys.json").read_text())
        allowed_diffs = set(tools.diffs.values())
        for name, args in probes + [("get_diff", {"commit": d["commit"]}) for d in deploys]:
            out = tools.handle(name, args)
            assert answer_text not in out and MARKERS.search(out) is None, (c.id, name, args)
            if name == "get_diff":
                assert out in allowed_diffs or out == "no diff for that commit"
        # Every deploy's diff is reachable by short and full sha, and nothing else is.
        for d in deploys:
            assert tools.handle("get_diff", {"commit": d["commit"]}) != "no diff for that commit" or c.id == "reg-verbatim"
        assert tools.handle("get_diff", {"commit": "order_i"}) == "no diff for that commit"


def test_case_json_carries_no_ground_truth(cases):
    for c in cases:
        case = json.loads((c.dir / "case.json").read_text())
        assert set(case) == {"id", "family", "split", "prompt", "tags", "log_lines", "log_sha256"}
        # The prompt is a symptom ("checkout p99 spiked ~14:32"): no sha, no component name.
        answer = json.loads((c.dir / "answer.json").read_text())
        deploys = json.loads((c.dir / "fixtures/deploys.json").read_text())
        prompt = case["prompt"].lower()
        assert not [d["commit"] for d in deploys if d["commit"] in prompt]
        assert not [n for n in answer["components"] if n in prompt]


def test_system_prompt_starts_as_the_shipped_prompt():
    sys.path.insert(0, str(EVALS.parent))
    import config
    assert (EVALS / "prompts" / "system.md").read_text() == config.SYSTEM
