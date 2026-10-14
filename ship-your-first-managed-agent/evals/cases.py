# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0
"""Load generated cases. The runner uses load_cases(); only graders call load_answer()."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

CASES_DIR = Path(__file__).parent / "cases"


@dataclass(frozen=True)
class Case:
    id: str
    family: str
    split: str
    prompt: str
    tags: tuple[str, ...]
    dir: Path
    log_sha256: str


def load_cases(ids: list[str] | None = None, root: Path = CASES_DIR) -> list[Case]:
    if not root.exists():
        raise SystemExit(f"no cases in {root} - run `uv run python generate.py` first")
    out = []
    for d in sorted(p for p in root.iterdir() if (p / "case.json").exists()):
        c = json.loads((d / "case.json").read_text())
        if ids is None or c["id"] in ids:
            out.append(Case(c["id"], c["family"], c["split"], c["prompt"], tuple(c["tags"]), d, c["log_sha256"]))
    if ids is not None and len(out) != len(set(ids)):
        raise SystemExit(f"unknown case id(s): {sorted(set(ids) - {c.id for c in out})}")
    return out


def load_answer(case: Case) -> dict:
    """Ground truth. Graders only: never pass this to anything the agent can see."""
    return json.loads((case.dir / "answer.json").read_text())
