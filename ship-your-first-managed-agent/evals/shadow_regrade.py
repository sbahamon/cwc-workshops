# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0
"""
Shadow regrade: re-grade stored transcripts with a PROPOSED grader fix, beside the
official grade. Analysis only: it never writes results.jsonl and isn't in the
harness. Used overnight 2026-10-14 so walk decisions could proceed while the fix
waits for Steffany's review (docs/plan.md session log).

    uv run python shadow_regrade.py v1 v2 ...

Proposed fix (graders._identifier): strip trailing punctuation from the
identifier's first token, so "`de6541f`. The refactor..." reads as de6541f
instead of "de6541f." (which fails the hex match). Found in ladder/v1: two
rows named the correct sha in that form and were scored root_cause=0.
"""
from __future__ import annotations

import json
import re
import sys

import graders
from cases import load_answer, load_cases
from walk import LADDER, cell, verdict

_orig_identifier = graders._identifier


def _identifier_fixed(body: str) -> str:
    ident = _orig_identifier(body)
    first, _, rest = ident.partition(" ")
    first = first.rstrip(".,;:!?")
    return (first + (" " + rest if rest else "")).strip()


def shadow_rows(variant: str) -> list[dict]:
    answers = {c.id: load_answer(c) for c in load_cases()}
    out = []
    for r in map(json.loads, (LADDER / variant / "results.jsonl").read_text().splitlines()):
        t = json.loads((LADDER / variant / "traces" / f"{r['prompt_id']}_rep{r['rep']}.json").read_text())
        text = "\n".join(x["content"] for x in t if x["role"] == "assistant")
        graders._identifier = _identifier_fixed
        try:
            g = graders.grade(text, answers[r["prompt_id"]])
        finally:
            graders._identifier = _orig_identifier
        out.append({**r, "grade": g, "official_grade": r["grade"]})
    return out


def shadow_cell(variant: str) -> dict:
    """walk.cell() computed on shadow grades (same code path, via a temp flow)."""
    import shutil
    import tempfile
    from pathlib import Path
    tmp = Path(tempfile.mkdtemp())
    try:
        shutil.copy(LADDER / "_state.json", tmp / "_state.json")
        for v in {"baseline", variant}:
            (tmp / v).mkdir()
            (tmp / v / "results.jsonl").write_text("".join(json.dumps(r) + "\n" for r in shadow_rows(v)))
            if (LADDER / v / "errors.jsonl").exists():
                shutil.copy(LADDER / v / "errors.jsonl", tmp / v / "errors.jsonl")
        return {"cell": cell(variant, tmp), "baseline": cell("baseline", tmp)}
    finally:
        shutil.rmtree(tmp)


def main(argv: list[str]) -> None:
    floor = json.loads((LADDER / "_state.json").read_text())["floor"]
    for v in argv:
        off_base, off = cell("baseline"), cell(v)
        sh = shadow_cell(v)
        flips = [(r["prompt_id"], r["rep"], r["official_grade"], r["grade"]) for r in shadow_rows(v)
                 if r["grade"] != r["official_grade"]]
        vo = verdict(off, off_base, floor) if v != "baseline" else None
        vs = verdict(sh["cell"], sh["baseline"], floor) if v != "baseline" else None
        print(f"{v}: official rc(tt) {off['root_cause_tt']:.1%} fmt {off['format']:.1%} verbatim {off['reg_verbatim']}"
              f" | shadow rc(tt) {sh['cell']['root_cause_tt']:.1%} fmt {sh['cell']['format']:.1%} verbatim {sh['cell']['reg_verbatim']}")
        if vo:
            agree = vo["pass"] == vs["pass"]
            print(f"   verdict official {'PASS' if vo['pass'] else 'FAIL'} {vo['checks']} | shadow {'PASS' if vs['pass'] else 'FAIL'} "
                  f"{vs['checks']} | {'AGREE' if agree else 'DISAGREE -> stop the walk'}")
        for f in flips:
            print(f"   regraded: {f[0]} rep{f[1]} {f[2]} -> {f[3]}")


if __name__ == "__main__":
    main(sys.argv[1:])
