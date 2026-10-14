# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0
"""
Cumulative project spend, recomputed from the files every time (never a counter).

    uv run python spend.py

Sums `list_cost_usd` over every results.jsonl and errors.jsonl under evals/
(failed attempts are billed too) plus evals/pilot/manual.jsonl (runs made
outside run.py, e.g. the Phase 1 e2e smoke test). Rows from --fake runs and
rows copied from another flow (meta.copied_from) are skipped so nothing is
counted twice or counted when it cost nothing.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

EVALS = Path(__file__).parent
CAP_USD = 50.00
SKIP_DIRS = {"cases", ".venv", "__pycache__", "tests"}


def _rows(path: Path):
    for line in path.read_text().splitlines():
        if line.strip():
            yield json.loads(line)


def ledger_files(root: Path = EVALS) -> list[Path]:
    out = []
    for p in sorted(root.rglob("*.jsonl")):
        rel = p.relative_to(root)
        if SKIP_DIRS & set(rel.parts):
            continue
        if p.name in ("results.jsonl", "errors.jsonl") or rel.as_posix() == "pilot/manual.jsonl":
            out.append(p)
    return out


def counted(row: dict) -> bool:
    meta = row.get("meta") or {}
    return not meta.get("fake") and not meta.get("copied_from")


def spend_by_file(root: Path = EVALS) -> dict[str, float]:
    by = defaultdict(float)
    for p in ledger_files(root):
        for r in _rows(p):
            if counted(r) and r.get("list_cost_usd") is not None:
                by[p.relative_to(root).as_posix()] += float(r["list_cost_usd"])
    return dict(by)


def total_spend(root: Path = EVALS) -> float:
    return round(sum(spend_by_file(root).values()), 2)


def main() -> None:
    by = spend_by_file()
    for f, usd in sorted(by.items()):
        print(f"  ${usd:7.2f}  {f}")
    total = round(sum(by.values()), 2)
    print(f"  ${total:7.2f}  total of ${CAP_USD:.2f} cap ({total / CAP_USD:.0%}); ${CAP_USD - total:.2f} left")


if __name__ == "__main__":
    main()
