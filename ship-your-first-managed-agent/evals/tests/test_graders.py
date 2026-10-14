# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0
"""Grader fixtures, registered before any eval run (docs/plan.md, Phase 3)."""
import pytest

from graders import find_root_cause_line, grade, grade_format, grade_legacy_e2e, grade_root_cause

DEPLOY = {"kind": "deploy", "culprit_short": "a3f9c21",
          "culprit_sha": "a3f9c21e8b4d2f1a9c0e7d3b5f8a2c4e6d9b1f0a", "components": []}
DB = {"kind": "component", "culprit_short": None, "culprit_sha": None,
      "components": ["db-primary", "db primary", "primary db", "primary database"]}
STRIPE = {"kind": "component", "culprit_short": None, "culprit_sha": None,
          "components": ["stripe-api", "stripe api", "stripe"]}

# Verbatim from the Phase 1 smoke run (evals/pilot/phase1-e2e-smoke.log:41), Opus 4.8.
REAL_OPUS_LINE = ("> **Root cause:** `a3f9c21` — refactor swapped a single batched `order_id__in` query "
                  "for a per-order query inside a loop (N+1), multiplying DB round-trips per checkout "
                  "request and driving p99 from ~60 ms to multiple seconds.")

# Passes the old e2e check: names N+1 and the right hash, but concludes a different commit.
RECAP_WRONG = """Recent deploys: e21b6c9 (cart), 9f1e2d4 (auth), a3f9c21 (checkout), 7b3e8f0 (inventory).
The a3f9c21 diff could be an N+1, but the timing fits auth's rate limiter better.

**Root cause:** `9f1e2d4` — the new /refresh rate limiter throttles checkout's token refresh."""

# Fails the old e2e check (never says "N+1") but is right.
PER_ROW_RIGHT = """Deploy a3f9c21 lines up with the p99 jump; the diff swaps a batched lookup for a loop.

**Root cause:** `a3f9c21` — the summary builder now issues a per-row query for every open order."""


def test_real_opus_line_passes_both():
    text = "Evidence above.\n\n" + REAL_OPUS_LINE
    assert grade(text, DEPLOY) == {"root_cause": 1, "format": 1}


def test_full_40_char_hash_with_bold():
    text = f"**Root cause:** **{DEPLOY['culprit_sha']}** — per-row query loop replaced a batched query."
    assert grade(text, DEPLOY) == {"root_cause": 1, "format": 1}


def test_recap_with_wrong_conclusion_passes_legacy_fails_new():
    assert grade_legacy_e2e(RECAP_WRONG) == 1
    assert grade_root_cause(RECAP_WRONG, DEPLOY) == 0


def test_per_row_wording_fails_legacy_passes_new():
    assert grade_legacy_e2e(PER_ROW_RIGHT) == 0
    assert grade_root_cause(PER_ROW_RIGHT, DEPLOY) == 1


def test_no_culprit_with_a_hash_fails():
    text = "**Root cause:** `a3f9c21` — db-primary lock waits started after this deploy."
    assert grade_root_cause(text, DB) == 0


@pytest.mark.parametrize("line", [
    "**Root cause:** `db-primary` — lock waits on the primary exhausted every service's pool.",
    "**Root cause:** db-primary: lock contention starved the connection pools.",
    "**Root cause:** primary DB lock contention — not a deploy; three services degraded together.",
    "> **Root cause:** `db-primary` (Postgres primary) — slow queries held connections until pools ran dry.",
])
def test_no_culprit_component_passes(line):
    assert grade_root_cause(line, DB) == 1


@pytest.mark.parametrize("line,answer,want", [
    ("**Root cause:** `stripe-api` — upstream timeouts at 5 s tie up checkout workers.", STRIPE, 1),
    ("**Root cause:** Stripe — the payments upstream is timing out.", STRIPE, 1),
    ("**Root cause:** checkout — the service is slow.", STRIPE, 0),   # names the symptom, not the cause
    ("**Root cause:** `stripe-api` — upstream timeouts.", DB, 0),     # wrong component
    ("**Root cause:** `db-primary` — lock waits.", DEPLOY, 0),        # component on a deploy case
])
def test_component_matching(line, answer, want):
    assert grade_root_cause(line, answer) == want


def test_missing_line_scores_zero_on_both():
    text = "Probably a3f9c21, the N+1 in checkout. Revert it."
    assert find_root_cause_line(text) is None
    assert grade(text, DEPLOY) == {"root_cause": 0, "format": 0}


def test_two_sentence_line_fails_format_but_still_grades_root_cause():
    text = "**Root cause:** `a3f9c21` — per-row queries replaced a batch. Revert it to recover."
    assert grade(text, DEPLOY) == {"root_cause": 1, "format": 0}


@pytest.mark.parametrize("line", [
    "**Root cause:** `a3f9c21` — the loop in `checkout/handlers.py` runs one query per order.",  # dot in a filename
    "**Root cause:** `a3f9c21` — p99 went from ~60 ms to 3.6 s because of a per-row query.",      # decimal
    "**Root cause:** `a3f9c21` — an N+1 (e.g. one query per order) replaced the batched lookup.",  # abbreviation
])
def test_dots_inside_a_sentence_dont_split_it(line):
    assert grade_format(line) == 1


@pytest.mark.parametrize("prefix", ["", "> ", "- ", "* ", "1. ", "  > "])
def test_markdown_wrappers_are_tolerated(prefix):
    assert grade_root_cause(prefix + "**Root cause:** `a3f9c21` — N+1 query.", DEPLOY) == 1


@pytest.mark.parametrize("label", ["**Root cause:**", "**Root Cause:**", "**root cause:**", "**Root cause**:"])
def test_label_variants(label):
    assert grade_root_cause(f"{label} `a3f9c21` — N+1 query.", DEPLOY) == 1


def test_commit_word_before_the_sha_is_tolerated():
    assert grade_root_cause("**Root cause:** commit `a3f9c21` — N+1 query.", DEPLOY) == 1


def test_last_root_cause_line_wins():
    text = ("**Root cause:** `9f1e2d4` — first guess.\n\nOn reflection the timing is off.\n\n"
            "**Root cause:** `a3f9c21` — per-row query loop.")
    assert grade_root_cause(text, DEPLOY) == 1
    assert grade_root_cause(text.replace("a3f9c21", "7b3e8f0"), DEPLOY) == 0


def test_wrong_sha_and_non_hex_fail():
    assert grade_root_cause("**Root cause:** `a3f9c22` — N+1 query.", DEPLOY) == 0
    assert grade_root_cause("**Root cause:** the checkout deploy — N+1 query.", DEPLOY) == 0
    assert grade_root_cause("**Root cause:**", DEPLOY) == 0


def test_null_outputs_score_zero():
    for text in ["", " ", "I don't know.", "**Root cause:** unknown."]:
        assert grade(text, DEPLOY) == {"root_cause": 0, "format": int(text.startswith("**"))}
        assert grade_root_cause(text, DB) == 0


def test_grading_is_deterministic():
    for text in [REAL_OPUS_LINE, RECAP_WRONG, PER_ROW_RIGHT]:
        assert grade(text, DEPLOY) == grade(text, DEPLOY)


# Found overnight 2026-10-14 in ladder/v1 (two rows scored 0 for naming the right sha
# followed by a period). Fixed in graders.py after the Phase 6 results; every stored
# row was regraded in place by regrade.py (docs/plan.md, post-results bug fix).
@pytest.mark.parametrize("line", [
    "> **Root cause:** `a3f9c21`. The \"readability\" refactor turned one batched order-items query into one query per order (N+1).",
    "**Root cause:** `a3f9c21`. Per-row queries replaced the batched lookup.",
])
def test_sha_followed_by_punctuation(line):
    assert grade_root_cause(line, DEPLOY) == 1
