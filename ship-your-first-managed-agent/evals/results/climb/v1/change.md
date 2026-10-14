Round 1: system.md, one-sentence root-cause line written once, last (model=claude-sonnet-5-5, effort=low)

Target: format (higher); guardrail: root_cause. Analyzer: fresh subagent, given only the 18
train-split transcripts and rows (copied to a scratch dir), system.md and the runbook.

Behavior (analyzer): the root-cause line is written as two sentences: the change, then a
follow-on (downstream impact in 2 rows, remediation in 1). Passing rows fold the effect into a
subordinate clause or drop it, and put the fix on its own line. 4/18 train rows show it; 3 cost
format (im-docs rep0, rb-early-n1 rep0, shift-morning rep0); rb-cache rep0 passed only because a
later one-sentence copy of the line is the one graded. The line was also written twice in 2 rows.
Ceiling on train: +3 rows (+16.7 pts train, about +7 pts over 42 rows, inside the ±15 noise floor),
but it's a general habit, so the fix targets the behavior, not these cases.

Change: say exactly what goes on the line (one sentence: what changed and how it produces the
symptom), that it is written once as the last line, and where everything else goes (its own line
above). No sha, service, time or punctuation workaround. De-fluff pass: nothing cut (every
sentence is operational). Expected root_cause effect: none; the identifier keeps its position.

Diff: change.patch. Snapshot: system.md.

Result (4 reps, 84 rows; 0 errors): format 82/84 = 97.6% ± 3.3% (reps 1-2: 40/42; confirmation
reps 3-4: 42/42); root cause 68/68 train+test; reg-verbatim [1, 1, 1, 1]; val root cause 16/16.
Misses: shift-morning rep 0, reg-1440 rep 1. **PASS** the C0.3 floor, outside noise after the
confirmation. **Kept.** 3.33¢ list / 3.41¢ rate card per incident (ladder baseline 24.07¢ / 24.02¢).
