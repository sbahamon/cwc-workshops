# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0
"""
Cumulative project spend, recomputed from the files every time (never a counter).

Two columns: list_cost (the headline: metered by Managed Agents, enforced by
session budgets and by the cap below) and the rate-card cost of the same tokens
(pricing.py). The cap applies to list_cost only.

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


def rate_card_of(row: dict, ledger: Path) -> float | None:
    """The row's rate-card cost: stored, else priced from its saved raw events, else from
    session-level usage (no per-request tier; fine below 100K-token prompts), else None."""
    from pricing import known, session_usd
    if row.get("rate_card_usd") is not None:
        return float(row["rate_card_usd"])
    model = row.get("model")
    if not known(model):
        return None
    active = (row.get("meta") or {}).get("active_seconds", row.get("active_seconds"))
    raw = ledger.parent / "raw" / f"{row.get('prompt_id')}_rep{row.get('rep')}.jsonl"
    if raw.exists():
        spans = [e["model_usage"] for e in map(json.loads, raw.read_text().splitlines())
                 if e.get("type") == "span.model_request_end"]
        if spans:
            return session_usd(model, spans, active)
    u = row.get("usage")
    return session_usd(model, [u], active) if u and u.get("output_tokens") else None


def spend_by_file(root: Path = EVALS, column: str = "list") -> dict[str, float]:
    """{ledger file: usd}. column "list" (headline, capped) or "rate_card"."""
    by = defaultdict(float)
    for p in ledger_files(root):
        for r in _rows(p):
            if not counted(r):
                continue
            v = r.get("list_cost_usd") if column == "list" else rate_card_of(r, p)
            if v is not None:
                by[p.relative_to(root).as_posix()] += float(v)
    return dict(by)


def unpriced(root: Path = EVALS) -> int:
    """Billed rows with a list cost but no rate-card cost (e.g. sessions orphaned before the fix)."""
    return sum(1 for p in ledger_files(root) for r in _rows(p)
               if counted(r) and r.get("list_cost_usd") is not None and rate_card_of(r, p) is None)


def total_spend(root: Path = EVALS) -> float:
    return round(sum(spend_by_file(root).values()), 2)


def main() -> None:
    lst, card = spend_by_file(), spend_by_file(column="rate_card")
    print(f"  {'list_cost':>9s}  {'rate card':>9s}  ledger file")
    for f in sorted(lst):
        print(f"  ${lst[f]:8.2f}  ${card.get(f, 0):8.4f}  {f}")
    total = round(sum(lst.values()), 2)
    n = unpriced()
    print(f"  ${total:8.2f}  ${sum(card.values()):8.4f}  total; cap ${CAP_USD:.2f} applies to list_cost "
          f"({total / CAP_USD:.0%} used, ${CAP_USD - total:.2f} left)"
          + (f"; {n} billed row(s) have no rate-card cost (no usage recorded)" if n else ""))


if __name__ == "__main__":
    main()
