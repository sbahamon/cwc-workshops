# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0
"""Shortcut agents that don't read evidence must score badly (eval-audit: annotation artifacts).

Each policy writes a root-cause line from deploys.json and the prompt alone, with
no log, no diff and no metrics. If one of these scores well, the cases measure
the shortcut, not triage. Scores here are pinned; a case change that makes a
shortcut work again fails this file.
"""
import json
import re
from datetime import datetime

import pytest

from cases import load_answer, load_cases
from generate import write
from graders import grade
from specs import SPECS, split_of


def T(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


@pytest.fixture(scope="module")
def cases(tmp_path_factory):
    root = tmp_path_factory.mktemp("cases")
    for sc in SPECS:
        write(sc, split_of(sc), root=root)
    return load_cases(root=root)


def deploys(c):
    return json.loads((c.dir / "fixtures/deploys.json").read_text())


def page_deadline(c, ds):
    """End of the paged minute, or end of window for prompts without a time."""
    sc = next(s for s in SPECS if s.id == c.id)
    m = re.search(r"~(\d\d):(\d\d) UTC", c.prompt)
    if not m:
        return sc.end
    return sc.start.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=59)


def paged_service(c):
    return next(s.affected_service for s in SPECS if s.id == c.id)


def say(ident):
    return f"**Root cause:** `{ident}` — mechanism."


def latest(ds):
    return max(ds, key=lambda d: d["ts"])["commit"] if ds else "unknown"


POLICIES = {
    "latest deploy before page": lambda c, ds: say(latest([d for d in ds if T(d["ts"]) <= page_deadline(c, ds)])),
    "latest paged-service deploy before page": lambda c, ds: say(latest(
        [d for d in ds if T(d["ts"]) <= page_deadline(c, ds) and d["service"] == paged_service(c)])),
    "same, skipping rolled-back deploys": lambda c, ds: say(latest(
        [d for d in ds if T(d["ts"]) <= page_deadline(c, ds) and d["service"] == paged_service(c)
         and d["status"] == "success"])),
    "always a3f9c21": lambda c, ds: say("a3f9c21"),
}

# Pinned per-family scores (correct / cases). Change only with a recorded reason.
EXPECTED = {
    "latest deploy before page":
        {"regression": 2, "shifted": 3, "rolled_back": 0, "innocent_message": 0, "decoy": 2, "no_culprit": 0},
    "latest paged-service deploy before page":
        {"regression": 4, "shifted": 3, "rolled_back": 0, "innocent_message": 0, "decoy": 4, "no_culprit": 0},
    "same, skipping rolled-back deploys":
        {"regression": 4, "shifted": 3, "rolled_back": 3, "innocent_message": 0, "decoy": 4, "no_culprit": 0},
    "always a3f9c21":
        {"regression": 4, "shifted": 0, "rolled_back": 0, "innocent_message": 0, "decoy": 0, "no_culprit": 0},
}


@pytest.mark.parametrize("name", POLICIES)
def test_shortcut_scores_are_pinned(name, cases):
    got = {f: 0 for f in EXPECTED[name]}
    for c in cases:
        got[c.family] += grade(POLICIES[name](c, deploys(c)), load_answer(c))["root_cause"]
    assert got == EXPECTED[name]


def test_no_shortcut_clears_two_thirds(cases):
    for name, pol in POLICIES.items():
        total = sum(grade(pol(c, deploys(c)), load_answer(c))["root_cause"] for c in cases)
        assert total <= 14, (name, total)


def test_oracle_and_null(cases):
    for c in cases:
        a = load_answer(c)
        assert grade(say(a["culprit_short"] or a["components"][0]), a)["root_cause"] == 1
        assert grade("", a) == {"root_cause": 0, "format": 0}
