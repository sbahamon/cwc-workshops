model=claude-haiku-5-5, effort=low, prompt=climbed system.md (climb v1, sha f5795bebac50)

Why the walk went here: the climb made Sonnet 5.5 low + climbed prompt pass the C0.3 floor
(climb/v1: format 97.6%, root cause 100%, 3.33¢ list per incident), so it is the new incumbent.
C0.4: on a pass, step down to Haiku 5.5 low if projected under the incumbent's cost. Projection
from the canary (pilot/haiku-5-5-low-climbed, reg-500s: root_cause 1, format 1, 2¢ list /
0.40¢ rate card) is under 3.33¢ on either basis. Steffany authorized this step (2026-10-14).
Verdict against the C0.3 floor: written after the run, below.

Verdict (walk.py, 2026-10-14; 42 rows, 0 errors): **FAIL** on two checks, both within noise.
- root_cause (train+test): 30/34 = 88.2% ± 10.8% vs >= 90.0%: fail (90% is inside the CI).
  Misses (all test): dc-after rep 1, nc-db-2 rep 0, nc-stripe-2 reps 0 and 1. Grader audit (only
  the graded line read): three of the four name the right answer but write a plain "Root cause:"
  without the bold label, so the grader finds no root-cause line and scores 0 on both metrics;
  nc-db-2 rep 0 is a real miss (it blames an innocent deploy on a no-culprit case). A shadow grade
  that accepts the unbolded label for root_cause gives 33/34 = 97.1%. Not applied: the grader is
  harness, and the template asks for the bold label.
- format: 39/42 = 92.9% ± 7.8% vs >= 95%: fail (95% inside the CI). The same three rows; format
  fails them under either grading, so the cell fails the floor whatever the label rule.
- reg-verbatim [1, 1]: pass. Train and val: 26/26 on both metrics.
- Cost: 1.79¢ list / 0.42¢ rate card per incident (incumbent climb/v1: 3.33¢ / 3.41¢). Haiku's list
  cost reads about 4× its rate card again, consistent with the billing check in SOURCES.md.
- Output tokens 2,830/session (climbed Sonnet low: about 1,180); latency 24.8 s; 8.4 tool calls.
Walk: C0.4 gives a within-noise fail one more run (42 sessions, about 75¢ list) before the walk
moves. Not run: Steffany's instruction was to stop after this result. Incumbent: climb/v1.
