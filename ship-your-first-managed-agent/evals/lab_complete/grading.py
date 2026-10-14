# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0
"""
Checkpoint 1, finished: grade the root cause.

Reference solution for lab/grading.py. It grades every recorded reply in results/
exactly as the eval's own graders.py does (tests/test_lab.py checks all of them).

    uv run python checkpoint.py 1 --solution
"""
from __future__ import annotations

import re

from graders import find_root_cause_line  # provided: body of the LAST `**Root cause:**` line, or None

SHA = re.compile(r"[0-9a-f]{7,40}", re.I)
SHA_ANYWHERE = re.compile(r"\b[0-9a-f]{7,40}\b", re.I)
# Where the name stops and the mechanism starts: a spaced dash, punctuation, or a verb.
MECHANISM = re.compile(r"\s+[—–-]\s+|\s*[:;,(]|\s+(?:is|was|caused|causing|because)\b", re.I)
LEADING_WORDS = re.compile(r"^(?:the\s+)?(?:commit|deploy|sha)\s+", re.I)


def identifier(body: str) -> str:
    """'`a3f9c21` — refactor…' -> 'a3f9c21';  'primary DB lock contention — …' -> 'primary db lock contention'."""
    name = MECHANISM.split(body, maxsplit=1)[0]
    name = re.sub(r"[`*\"']", "", name).strip().rstrip(".")
    name = LEADING_WORDS.sub("", name)
    return " ".join(name.split()).lower()


def grade_root_cause(text: str, answer: dict) -> int:
    """1 if the reply's root-cause line names the answer key's culprit, else 0."""
    body = find_root_cause_line(text)
    if not body:
        return 0                                            # rule 1: no line, no credit
    name = identifier(body)                                 # rule 2
    if answer["kind"] == "deploy":                          # rule 3
        first = name.split(" ", 1)[0].rstrip(".,;:!?")
        return int(bool(SHA.fullmatch(first)) and first[:7] == answer["culprit_short"])
    if SHA_ANYWHERE.search(name):                           # rule 4: blamed a deploy
        return 0
    return int(any(name == c or name.startswith(c + " ") for c in answer["components"]))
