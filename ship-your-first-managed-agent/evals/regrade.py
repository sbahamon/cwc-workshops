# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0
"""
Re-grade stored rows in place with the current graders.py, from their saved traces.

    uv run python regrade.py            # report what would change
    uv run python regrade.py --write    # rewrite results.jsonl files

Used once, 2026-10-14, after the trailing-punctuation grader fix (planning/plan.md,
post-results bug fix). A row whose grade changes keeps its previous grade in
meta.grade_before_regrade, so the change is auditable from the file itself.
Never calls the API; costs nothing.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from cases import load_answer, load_cases
from graders import grade

EVALS = Path(__file__).parent


def flows() -> list[Path]:
    return sorted(p for root in ("hillclimb", "pilot") for p in (EVALS / root).rglob("results.jsonl"))


def regrade(path: Path, answers: dict, write: bool) -> list[tuple]:
    out, flips = [], []
    for r in map(json.loads, filter(str.strip, path.read_text().splitlines())):
        trace = path.parent / "traces" / f"{r['prompt_id']}_rep{r['rep']}.json"
        text = "\n".join(t["content"] for t in json.loads(trace.read_text()) if t["role"] == "assistant")
        g = grade(text, answers[r["prompt_id"]])
        if g != r["grade"]:
            flips.append((r["prompt_id"], r["rep"], r["grade"], g))
            r["meta"] = {**r.get("meta", {}), "grade_before_regrade": r["grade"]}
            r["grade"] = g
        out.append(r)
    if write and flips:
        path.write_text("".join(json.dumps(r, separators=(",", ":"), default=str) + "\n" for r in out))  # as run.py writes rows
    return flips


def main(argv: list[str]) -> None:
    write = "--write" in argv
    answers = {c.id: load_answer(c) for c in load_cases()}
    for p in flows():
        flips = regrade(p, answers, write)
        print(f"{p.relative_to(EVALS)}: {len(flips)} changed" + (" (written)" if write and flips else ""))
        for f in flips:
            print(f"   {f[0]} rep{f[1]}: {f[2]} -> {f[3]}")


if __name__ == "__main__":
    main(sys.argv[1:])
