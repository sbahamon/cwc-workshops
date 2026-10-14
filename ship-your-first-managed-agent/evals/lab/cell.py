# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0
"""
Checkpoint 4: which model, at which effort?

The model and effort are the cost dials. The workshop's agent runs Opus 4.8 at its
default effort (on Managed Agents that default reports as `xhigh`). Change the one
line below to Haiku 5.5 at low effort: "claude-haiku-5-5", "low".

Effort is one of "low", "medium", "high", "xhigh", "max", or None for the model's default.
This file only feeds the lab's checkpoint runs; the workshop's own config.py is unchanged.

Check your work:  uv run python checkpoint.py 4
"""

MODEL, EFFORT = "claude-opus-4-8", None  # checkpoint 4: swap this line
