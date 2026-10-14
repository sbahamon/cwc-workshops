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
