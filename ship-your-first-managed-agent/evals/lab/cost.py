# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0
"""
Checkpoint 3: what did one session cost?

Every model request in a Managed Agents session ends with a `span.model_request_end`
event carrying that request's token usage. Price each request from the published rate
card, add the session's runtime, and you have the cost of one incident.

Check your work:  uv run python checkpoint.py 3
Stuck?            lab_complete/cost.py has a finished version.
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


def session_cost(model: str, requests: list[dict], active_seconds: float) -> float:
    """Rate-card cost of one session, in US dollars.

    `requests` has one dict per model request, as the event stream reports it:

        {"input_tokens": 4, "output_tokens": 70,
         "cache_read_input_tokens": 6695, "cache_creation_input_tokens": 132}

    For each request: tokens × rate ÷ 1,000,000 for each of the four kinds
    (cache_read_input_tokens -> "cache_read", cache_creation_input_tokens -> "cache_write").
    On Haiku 5.5, a request whose prompt is over HAIKU_TIER_TOKENS uses HAIKU_LONG_PROMPT.
    Then add runtime: active_seconds at RUNTIME_USD_PER_HOUR.
    """
    raise NotImplementedError("write session_cost in lab/cost.py")
