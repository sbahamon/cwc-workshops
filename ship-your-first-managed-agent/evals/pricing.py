# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0
"""
Rate-card cost of a session, computed from its tokens: reported beside list_cost.

list_cost (from sessions.retrieve) stays the headline: it's what Managed Agents
meters, what session budgets and the project cap enforce. This module prices the
same session from the published rate card, so every row, the ledger and the
chart can show both. On the 2026-10-14 pilot they agreed for Opus 4.8 and Sonnet
5.5 but not for Haiku 5.5 (list_cost about 5x the rate card); see SOURCES.md.

Source: https://platform.claude.com/docs/en/about-claude/pricing (fetched 2026-10-14):
  - Model pricing table: base input, 5m / 1h cache writes, cache hits, output
  - Haiku 5.5 is priced per request by prompt length: a request whose prompt
    (input + cache reads + cache writes) is over 100,000 tokens pays the higher row
  - Managed Agents: tokens at the model-pricing rates; session runtime
    $0.08 per session-hour of `running` time (we use usage.active_seconds)
"""
from __future__ import annotations

RATE_CARD_DATE = "2026-10-14"
RUNTIME_USD_PER_HOUR = 0.08
HAIKU_TIER_TOKENS = 100_000

# $/MTok: input, 5m cache write, 1h cache write, cache hit, output
_CARD = {
    "claude-opus-4-8": (5.00, 6.25, 10.00, 0.50, 25.00),
    "claude-sonnet-5-5": (2.00, 2.50, 4.00, 0.10, 10.00),
    "claude-haiku-5-5": (0.10, 0.125, 0.20, 0.01, 0.50),       # prompts <= 100,000 tokens
}
_HAIKU_OVER_TIER = (0.50, 0.625, 1.00, 0.05, 2.50)               # prompts > 100,000 tokens


def prompt_tokens(u: dict) -> int:
    return u["input_tokens"] + u["cache_read_input_tokens"] + u["cache_creation_input_tokens"]


def request_usd(model: str, u: dict, cache_write: str = "5m") -> float:
    """One model request (one span.model_request_end's model_usage)."""
    if model not in _CARD:
        raise KeyError(f"no rate card for {model}; add it to pricing.py from the pricing page")
    card = _CARD[model]
    if model == "claude-haiku-5-5" and prompt_tokens(u) > HAIKU_TIER_TOKENS:
        card = _HAIKU_OVER_TIER
    inp, w5, w1, hit, out = card
    write = w5 if cache_write == "5m" else w1
    return (u["input_tokens"] * inp + u["cache_creation_input_tokens"] * write
            + u["cache_read_input_tokens"] * hit + u["output_tokens"] * out) / 1e6


def session_usd(model: str, spans: list[dict], active_seconds: float | None, cache_1h_tokens: int = 0) -> float:
    """Rate-card cost of a whole session: every request priced on its own, plus runtime.

    Spans don't say which cache-write TTL they used; they're priced at 5m (all pilot
    sessions reported 0 one-hour tokens). If the session reports 1h writes, the
    difference is added at the base tier."""
    usd = sum(request_usd(model, u) for u in spans)
    if cache_1h_tokens:
        inp, w5, w1, *_ = _CARD[model]
        usd += cache_1h_tokens * (w1 - w5) / 1e6
    return usd + (active_seconds or 0) / 3600 * RUNTIME_USD_PER_HOUR


def known(model: str | None) -> bool:
    return model in _CARD
