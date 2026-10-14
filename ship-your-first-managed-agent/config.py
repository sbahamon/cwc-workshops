# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0
"""
The one place the agent's model, effort, system prompt and tools are defined.
provided.py, agent_complete.py, e2e.py and the evals/ runner all read from here,
so updating the model each release is a one-line change. No Streamlit import:
headless scripts can use this file without starting the dashboard.
"""
from pathlib import Path

HERE = Path(__file__).parent
RUNBOOK_DIR = HERE / "incident-triage-runbook"

MODEL = "claude-opus-4-8"
EFFORT = None  # None = model's default effort; or "low" | "medium" | "high" | "xhigh" | "max"


def model_param(model: str = MODEL, effort: str | None = EFFORT):
    """The `model` field for agents.create(): a bare ID, or {"id", "effort"} when effort is set."""
    return model if effort is None else {"id": model, "effort": effort}


SYSTEM = """\
You are the SRE Agent — an SRE/data-analyst agent embedded in an incident
dashboard. The application log is mounted at /mnt/session/uploads/app.log (large; use
grep/python to analyze it, don't read it whole). You have local tools that
query the same data the dashboard shows. Correlate evidence and state findings
plainly and concisely.
"""

TOOLS = [
    {"type": "agent_toolset_20260401", "default_config": {"enabled": True}},
    {"type": "custom", "name": "get_metrics",
     "description": "Timeseries for a service+metric over the incident window.",
     "input_schema": {"type": "object",
                      "properties": {"service": {"type": "string"}, "metric": {"type": "string"}},
                      "required": ["service", "metric"]}},
    {"type": "custom", "name": "get_recent_deploys", "description": "Deploys in the last 6h.",
     "input_schema": {"type": "object", "properties": {}}},
    {"type": "custom", "name": "get_diff", "description": "Unified diff for a commit SHA.",
     "input_schema": {"type": "object", "properties": {"commit": {"type": "string"}},
                      "required": ["commit"]}},
]
