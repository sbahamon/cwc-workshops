# Climb: Sonnet 5.5 low, system-prompt hillclimb on format

| round | change (one line) | format test | format train | format all (95% CI) | root cause train+test | val root cause | s/session | out toks | tool calls | ¢/incident rate card (list) | spend (list, cumulative after) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | baseline (ladder v1 rows, shipped prompt; copied, not re-billed) | 4/16 | 15/18 | 61.9% ± 14.7% | 34/34 | 8/8 | 18.1 | 1,244 | 6.6 | 3.75 (3.74) | $19.96 |
| 1 | one-sentence root-cause line, written once, last (2 + 2 reps) | **32/32** | 35/36 | **97.6% ± 3.3%** | 68/68 | 16/16 | 19.3 (1.1×) | about 1,180 (0.95×) | 6.5 (1.0×) | 3.41 (3.33) | $22.76 |

**Kept: round 1.** It passes the C0.3 floor (root cause 100%, `reg-verbatim` right on all 4 reps, format 97.6%). After 2 reps it sat exactly on the floor (40/42, within noise), so per C0.4 it got a confirmation run; reps 3–4 scored 42/42 on format, and 95% is now below the interval. One round was enough, so rounds 2–3 weren't needed.

Why it works: the system prompt now says exactly what goes on the root-cause line (one sentence: what changed and how it produces the symptom), that it's written once as the last line, and where everything else goes (its own line above). The analyzer saw the two-sentence habit in only 3 of 18 train rows; the baseline's misses were mostly on held-out test cases (12 of 16 test rows failed), and all of them recovered, so the change fixed a general habit rather than fitting the train rows. The mechanism engaged: in reps 1–2 the root-cause line was the last line in 42/42 rows (baseline 37/42) and never written twice (baseline 1); the line got longer (median 31 → 39 words) as the second sentence folded in, with no semicolon or dash workarounds. Root cause stayed 100% and cost per incident fell slightly. The two remaining misses are shift-morning rep 0 (train) and reg-1440 rep 1 (val).

Then the walk continued with the climbed prompt to Haiku 5.5 low (ladder v5). After the pre-registered confirmation run it **passes the floor narrowly** over 84 rows: root cause 63/68 (92.6%), format 80/84 (95.24%), both within noise, every miss on held-out test cases (`hillclimb/ladder/v5/change.md`). This round, climbed Sonnet 5.5 low, is the cheapest cell that passes with margin: 3.41¢ per incident at the rate card versus 24.02¢ for Opus 4.8 (7.0× cheaper). Haiku with the same prompt costs 0.42¢ at the rate card.

## Deployment recommendation

Separate from the walk's incumbent (Haiku 5.5 low, a narrow pass, as recorded; the walk ends there and Haiku medium was not run, Steffany's decision 2026-10-14):

- **Deploy climbed Sonnet 5.5 low** (`hillclimb/climb/v1`). It passes the floor with margin: root cause 68/68 on train+test including **32/32 on held-out test**, format 97.6%, `reg-verbatim` 4/4, at 3.41¢ per incident at the rate card (3.33¢ list) versus 24.02¢ (24.07¢) for Opus 4.8: **7× cheaper**.
- **Haiku 5.5 low is the cost-optimal option, pending a bold-label prompt fix (next work).** It costs 0.42¢ per incident (57× cheaper than Opus 4.8) but passes narrowly: test root cause 27/32, format one row above the bar. Four of its five root-cause misses are a correct answer with the bold `**Root cause:**` label dropped, so the next step is a prompt round targeting the label, re-measured with the same floor.

**The confirmation rule mattered twice.** The pre-registered within-noise rule (C0.4) ran twice: it **confirmed** climb round 1 (40/42 → 82/84 on format, a pass both times) and **changed** one verdict, Haiku 5.5 low, from fail at 2 reps (root cause 30/34, format 39/42) to pass at 4 reps (63/68, 80/84).

