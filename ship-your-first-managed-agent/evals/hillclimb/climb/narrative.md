# Climb: Sonnet 5.5 low, system-prompt hillclimb on format

| round | change (one line) | format test | format train | format all (95% CI) | root cause train+test | val root cause | s/session | out toks | tool calls | list ¢/incident (rate card) | spend (list, cumulative) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | baseline (ladder v1 rows, shipped prompt) | 4/16 | 15/18 | 61.9% ± 14.7% | 34/34 | 8/8 | 18.1 | 1,244 | 6.6 | 3.74 (3.75) | $19.96 |
| 1 | one-sentence root-cause line, written once, last | **16/16** | 17/18 | **95.2% ± 6.4%** | 34/34 | 8/8 | 19.2 (1.1×) | 1,182 (0.95×) | 6.5 (1.0×) | 3.43 (3.54) | $21.40 |

**Floor (C0.3):** root cause ≥ 90.0% train+test ✓, reg-verbatim [1, 1] ✓, format ≥ 95% ✓ at 95.2%, **within noise** (one more format miss in 42 would be 92.9%). Per C0.4 a pass within noise of the floor gets one more run before the walk moves: pending Steffany's OK.

Round 1 is winning, and it's one change: the system prompt now says exactly what the root-cause line holds (one sentence: what changed and how it produces the symptom), that it's written once as the last line, and where anything else goes (its own line above). The analyzer saw the two-sentence habit in 3 of 18 train rows; most of the baseline's misses were on held-out test cases (12 of 16 test rows), and all of them recovered, so the fix generalized rather than fitting the train rows. The mechanism engaged: the root-cause line is the last line in 42/42 rows (baseline 37/42), written twice in 0 rows (baseline 1); the line got longer (median 31 → 39 words) as the second sentence folded into one, with no semicolon or dash workarounds (0 in both rounds). Root cause stayed 100%, and cost per incident fell slightly (3.74¢ → 3.43¢ list). Remaining misses: shift-morning rep 0 (train) and reg-1440 rep 1 (val).
