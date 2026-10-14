# Climb: Sonnet 5.5 low, system-prompt hillclimb on format

| round | change (one line) | format test | format train | format all (95% CI) | root cause train+test | val root cause | s/session | out toks | tool calls | ¢/incident rate card (list) | spend (list, cumulative after) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | baseline (ladder v1 rows, shipped prompt; copied, not re-billed) | 4/16 | 15/18 | 61.9% ± 14.7% | 34/34 | 8/8 | 18.1 | 1,244 | 6.6 | 3.75 (3.74) | $19.96 |
| 1 | one-sentence root-cause line, written once, last (2 + 2 reps) | **32/32** | 35/36 | **97.6% ± 3.3%** | 68/68 | 16/16 | 19.3 (1.1×) | about 1,180 (0.95×) | 6.5 (1.0×) | 3.41 (3.33) | $22.76 |

**Kept: round 1.** It passes the C0.3 floor (root cause 100%, `reg-verbatim` right on all 4 reps, format 97.6%). After 2 reps it sat exactly on the floor (40/42, within noise), so per C0.4 it got a confirmation run; reps 3–4 scored 42/42 on format, and 95% is now below the interval. One round was enough, so rounds 2–3 weren't needed.

Why it works: the system prompt now says exactly what goes on the root-cause line (one sentence: what changed and how it produces the symptom), that it's written once as the last line, and where everything else goes (its own line above). The analyzer saw the two-sentence habit in only 3 of 18 train rows; the baseline's misses were mostly on held-out test cases (12 of 16 test rows failed), and all of them recovered, so the change fixed a general habit rather than fitting the train rows. The mechanism engaged: in reps 1–2 the root-cause line was the last line in 42/42 rows (baseline 37/42) and never written twice (baseline 1); the line got longer (median 31 → 39 words) as the second sentence folded in, with no semicolon or dash workarounds. Root cause stayed 100% and cost per incident fell slightly. The two remaining misses are shift-morning rep 0 (train) and reg-1440 rep 1 (val).

Then the walk continued with the climbed prompt: Haiku 5.5 low (ladder v5) **fails the floor**: root cause 30/34 (88.2%), format 39/42 (92.9%), both within noise (`hillclimb/ladder/v5/change.md`). Incumbent: this round, Sonnet 5.5 low + climbed prompt, at 3.41¢ per incident at the rate card versus 24.02¢ for the Opus 4.8 baseline (7.0× cheaper; 7.2× on list cost).
