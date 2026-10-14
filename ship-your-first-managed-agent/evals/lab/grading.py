# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0
"""
Checkpoint 1: grade the root cause.

The runbook makes the agent end every answer with one line:

    > **Root cause:** `a3f9c21` — the refactor replaced a batched query with a per-row loop.

or, when no deploy is at fault, a component in place of the sha:

    **Root cause:** `db-primary` — lock waits on the primary exhausted every service's pool.

So the answer space is closed (a sha from the deploy list, or a component name),
and a few lines of code grade it exactly. No LLM judge needed.

Check your work:  uv run python checkpoint.py 1
Stuck?            lab_complete/grading.py has a finished version.
"""
from __future__ import annotations

import re  # noqa: F401  (you'll probably want it)

from graders import find_root_cause_line  # provided: body of the LAST `**Root cause:**` line, or None


def grade_root_cause(text: str, answer: dict) -> int:
    """1 if the reply's root-cause line names the answer key's culprit, else 0.

    `text` is the agent's final reply. `answer` is the case's answer key
    (cases/<id>/answer.json), which the agent never sees:

        kind            "deploy" or "component"
        culprit_short   the culprit's 7-character sha on deploy cases, else None
        components      accepted names on component cases,
                        e.g. ["db-primary", "db primary", "primary db", "primary database"]

    Rules (checkpoint 1 has a fixture for each):
      1. No root-cause line: 0. `find_root_cause_line(text)` gives you the text after the label.
      2. The identifier is what the line names first, before the mechanism. It ends at a
         spaced dash (" — ", " - "), a colon, semicolon, comma or "(", or a verb such as
         "is", "was", "caused" or "because". Strip backticks, `*` and quotes, and a leading
         "commit", "deploy" or "sha".
      3. Deploy case: the identifier's first word, minus trailing punctuation
         ("`a3f9c21`. The…"), is a 7–40 character hex sha whose first 7 characters
         equal `culprit_short`. A full 40-character sha counts.
      4. Component case: any sha on the line is wrong (the agent blamed a deploy).
         Otherwise the identifier, lowercased, must equal one of `components`
         or start with one followed by a space ("db-primary lock waits").
    """
    raise NotImplementedError("write grade_root_cause in lab/grading.py")
