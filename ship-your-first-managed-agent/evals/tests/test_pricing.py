# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0
"""Rate-card pricing, checked against sessions measured on 2026-10-14."""
import json
from pathlib import Path

import pytest

from pricing import request_usd, session_usd

EVALS = Path(__file__).resolve().parents[1]


def spans(raw: Path):
    return [e["model_usage"] for e in map(json.loads, raw.read_text().splitlines())
            if e["type"] == "span.model_request_end"]


def test_opus_smoke_matches_its_list_cost():
    # Phase 1 smoke (session-level usage only): reported list_cost 20 cents.
    u = {"input_tokens": 14, "output_tokens": 2741, "cache_read_input_tokens": 67674,
         "cache_creation_input_tokens": 15288}
    assert session_usd("claude-opus-4-8", [u], 40.854) == pytest.approx(0.1989, abs=5e-4)


@pytest.mark.parametrize("cell,case,list_cents", [
    ("opus-4-8-default", "reg-500s", 25), ("opus-4-8-default", "reg-verbatim", 23),
    ("opus-4-8-low", "reg-500s", 15), ("sonnet-5-5-low", "reg-500s", 6),
])
def test_rate_card_agrees_with_list_cost_for_opus_and_sonnet(cell, case, list_cents):
    vdir = EVALS / "pilot" / cell / "baseline"
    row = next(r for r in map(json.loads, (vdir / "results.jsonl").read_text().splitlines()) if r["prompt_id"] == case)
    usd = session_usd(row["model"], spans(vdir / "raw" / f"{case}_rep0.jsonl"), row["meta"]["active_seconds"])
    assert round(usd * 100) == list_cents  # nearest-cent rounding of the session total


def test_haiku_rate_card_is_well_under_its_list_cost():
    """The observed difference (SOURCES.md): rate card ~0.5 cents, list_cost 2 cents."""
    vdir = EVALS / "pilot" / "haiku-5-5-low" / "baseline"
    row = json.loads((vdir / "results.jsonl").read_text().splitlines()[0])
    usd = session_usd("claude-haiku-5-5", spans(vdir / "raw" / "reg-500s_rep0.jsonl"), row["meta"]["active_seconds"])
    assert usd == pytest.approx(0.0047, abs=2e-4) and row["list_cost_usd"] == 0.02


def test_haiku_tier_is_per_request():
    small = {"input_tokens": 0, "output_tokens": 1000, "cache_read_input_tokens": 90_000, "cache_creation_input_tokens": 0}
    big = dict(small, cache_read_input_tokens=100_001)
    assert request_usd("claude-haiku-5-5", small) == pytest.approx((90_000 * 0.01 + 1000 * 0.50) / 1e6)
    assert request_usd("claude-haiku-5-5", big) == pytest.approx((100_001 * 0.05 + 1000 * 2.50) / 1e6)
    # Each request on its own: one big request doesn't reprice the small one.
    assert session_usd("claude-haiku-5-5", [small, big], 0) == pytest.approx(
        request_usd("claude-haiku-5-5", small) + request_usd("claude-haiku-5-5", big))


def test_sonnet_cache_hits_are_five_percent_of_input():
    u = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 1_000_000, "cache_creation_input_tokens": 0}
    assert request_usd("claude-sonnet-5-5", u) == pytest.approx(0.10)


def test_unknown_model_is_loud():
    with pytest.raises(KeyError):
        request_usd("claude-opus-5-5", {"input_tokens": 1, "output_tokens": 1,
                                        "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0})
