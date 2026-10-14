# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0
"""
Checkpoint 3, finished: what did one session cost?

Reference solution for lab/cost.py. It reproduces the `rate_card_usd` recorded on
every row in results/ (tests/test_lab.py checks all of them).

    uv run python checkpoint.py 3 --solution
"""
from __future__ import annotations

# $ per million tokens. Source: https://platform.claude.com/docs/en/about-claude/pricing
# (fetched 2026-10-14). cache_write is the 5-minute cache write, the only kind these sessions use.
RATES = {
    "claude-opus-4-8":   {"input": 5.00, "cache_write": 6.25,  "cache_read": 0.50, "output": 25.00},
    "claude-sonnet-5-5": {"input": 2.00, "cache_write": 2.50,  "cache_read": 0.10, "output": 10.00},
    "claude-haiku-5-5":  {"input": 0.10, "cache_write": 0.125, "cache_read": 0.01, "output": 0.50},
}
# Haiku 5.5 charges more for a request whose prompt (input + cache read + cache write
# tokens) is over 100,000 tokens. The tier is decided per request, not per session.
HAIKU_LONG_PROMPT = {"input": 0.50, "cache_write": 0.625, "cache_read": 0.05, "output": 2.50}
HAIKU_TIER_TOKENS = 100_000
RUNTIME_USD_PER_HOUR = 0.08  # Managed Agents session runtime, billed on active (running) time

FIELDS = {"input_tokens": "input", "cache_creation_input_tokens": "cache_write",
          "cache_read_input_tokens": "cache_read", "output_tokens": "output"}


def request_cost(model: str, usage: dict) -> float:
    rates = RATES[model]
    prompt = usage["input_tokens"] + usage["cache_read_input_tokens"] + usage["cache_creation_input_tokens"]
    if model == "claude-haiku-5-5" and prompt > HAIKU_TIER_TOKENS:
        rates = HAIKU_LONG_PROMPT
    return sum(usage[field] * rates[kind] for field, kind in FIELDS.items()) / 1_000_000


def session_cost(model: str, requests: list[dict], active_seconds: float) -> float:
    """Rate-card cost of one session, in US dollars: every request priced on its own, plus runtime."""
    tokens = sum(request_cost(model, u) for u in requests)
    return tokens + (active_seconds or 0) / 3600 * RUNTIME_USD_PER_HOUR
