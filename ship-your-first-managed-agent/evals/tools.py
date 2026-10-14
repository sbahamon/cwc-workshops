# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0
"""
The agent's three local tools, answered from one case's fixtures.

Same tools and the same reply strings as agent_complete.handle_tool, with one
deliberate difference: get_diff matches the requested sha against the deploy
list exactly (7-char prefix), instead of substring-searching a single diff.txt.
Reads only cases/<id>/fixtures/; answer.json is never opened here.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

HEX = re.compile(r"^[0-9a-f]{7,40}$")


class CaseTools:
    def __init__(self, case_dir: Path):
        self.fixtures = Path(case_dir) / "fixtures"
        self.metrics = json.loads((self.fixtures / "metrics.json").read_text())
        self.deploys = (self.fixtures / "deploys.json").read_text()
        self.diffs = {p.stem: p.read_text() for p in sorted((self.fixtures / "diffs").glob("*.txt"))}

    def upload_paths(self) -> list[Path]:
        """Files mounted into the agent's sandbox. Only the log."""
        return [self.fixtures / "app.log"]

    def handle(self, name: str, args: dict) -> str:
        if name == "get_metrics":
            series = self.metrics.get(str(args.get("service", "")), {}).get(str(args.get("metric", "")))
            return json.dumps(series or {"error": "not found"})
        if name == "get_recent_deploys":
            return self.deploys
        if name == "get_diff":
            commit = str(args.get("commit", "")).strip().strip("`").lower()
            if HEX.match(commit) and commit[:7] in self.diffs:
                return self.diffs[commit[:7]]
            return "no diff for that commit"
        return f"unknown tool {name}"
