# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0
"""
Two code graders for the SRE agent's final reply. Pure functions, no network.

The runbook fixes the output: one line at the bottom,

    > **Root cause:** `<sha>` — one sentence on the mechanism.

with a component name (`db-primary`, `stripe-api`) in place of the sha when no
deploy is at fault. So the answer space is closed (a sha from the deploy list,
or a component), and a code check grades it exactly:

  format      the root-cause line is present and its body is one sentence
  root_cause  the sha or component on that line matches the answer key

They're scored separately so "didn't write the line" and "named the wrong
commit" stay distinguishable: a hillclimb aims at different fixes for each.
"""
from __future__ import annotations

import re

LABEL = re.compile(r"\*\*\s*root\s+cause\s*:?\s*\*\*\s*:?", re.I)
LEAD = re.compile(r"^[\s>]*(?:(?:[-*+]|\d+[.)])\s+)?")  # blockquote, bullets, numbers
HEX = re.compile(r"\b[0-9a-f]{7,40}\b", re.I)
SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+(?=[A-Z`*\"'(])")
PHRASE_END = re.compile(r"\s+[—–-]\s+|\s*[:;,(]|\s+(?:is|was|caused|causing|because)\b", re.I)
LEADING_WORDS = re.compile(r"^(?:the\s+)?(?:commit|deploy|sha)\s+", re.I)


def find_root_cause_line(text: str) -> str | None:
    """Body of the LAST `**Root cause:**` line (text after the label), or None."""
    for line in reversed(text.splitlines()):
        stripped = LEAD.sub("", line)
        m = LABEL.match(stripped) or LABEL.search(stripped)
        if m:
            return stripped[m.end():].strip()
    return None


def grade_format(text: str) -> int:
    """1 if the root-cause line exists and its body is exactly one sentence."""
    body = find_root_cause_line(text)
    if not body:
        return 0
    segments = [s for s in SENTENCE_BREAK.split(body) if s.strip()]
    return int(len(segments) == 1)


def _identifier(body: str) -> str:
    """The thing named before the mechanism: '`a3f9c21` — refactor…' -> 'a3f9c21'."""
    phrase = PHRASE_END.split(body, maxsplit=1)[0]
    phrase = re.sub(r"[`*\"']", "", phrase).strip().rstrip(".")
    phrase = LEADING_WORDS.sub("", phrase)
    return re.sub(r"\s+", " ", phrase).lower()


def grade_root_cause(text: str, answer: dict) -> int:
    """1 if the root-cause line names the answer key's sha (deploy cases) or component."""
    body = find_root_cause_line(text)
    if not body:
        return 0
    ident = _identifier(body)
    if answer["kind"] == "deploy":
        first = ident.split(" ", 1)[0]
        return int(bool(HEX.fullmatch(first)) and first[:7] == answer["culprit_short"])
    # No deploy at fault: any sha on the line is a wrong answer.
    if HEX.search(ident):
        return 0
    return int(any(ident == c or ident.startswith(c + " ") for c in answer["components"]))


def grade(text: str, answer: dict) -> dict[str, int]:
    """The `grade` dict for results.jsonl. root_cause first: it's the headline metric."""
    return {"root_cause": grade_root_cause(text, answer), "format": grade_format(text)}


def grade_legacy_e2e(text: str, culprit_short: str = "a3f9c21") -> int:
    """The original e2e.py check, kept for the lab's grader-validation checkpoint."""
    full = text.lower()
    return int(("n+1" in full or "n + 1" in full) and culprit_short in full)
