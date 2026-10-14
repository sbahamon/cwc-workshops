# Ladder: morning summary (overnight 2026-10-14)

**Headline.** Every cheaper cell found the root cause as reliably as Opus 4.8. All three Sonnet 5.5 cells scored 100% root cause on train+test once the grader bug below is corrected. Sonnet 5.5 low did it at **3.7¢ per incident against 24.1¢, 6.4× cheaper**. But **no cell cleared the pre-registered floor**: every Sonnet cell failed the **format** rule (the root-cause line must be one sentence, ≥ 95% of rows). Sonnet keeps adding a second sentence such as "Reverting it should restore the batched query". More effort made that worse, not better. The walk stopped where its rules say it stops; the incumbent is still the baseline. Phase 8 was not started.

Chart: `results/path.svg` (and `.png`). Per-case table: `hillclimb/ladder/report.html` (lite builder).

## Cells

| cell | model, effort (echoed) | root_cause train+test (95% CI) | shadow* | format (95% CI) | reg-verbatim | list ¢/incident | rate card ¢/incident | floor | errors |
|---|---|---|---|---|---|---|---|---|---|
| baseline | opus-4-8, default (xhigh) | 100.0% ± 0.0% (n=34) | 100.0% | 92.9% ± 7.8% (n=42) | [1, 1] | 24.07 | 24.02 | reference | 0 |
| v1 | sonnet-5-5, low (low) | 97.1% ± 5.7% (n=34) | 100.0% | 61.9% ± 14.7% (n=42) | [1, 0] | 3.74 | 3.75 | FAIL | 0 |
| v2 | opus-4-8, low (low) | 100.0% ± 0.0% (n=17) | 100.0% | 100.0% ± 0.0% (n=21) | [1] | 13.71 | 13.65 | diagnostic (off path) | 0 |
| v3 | sonnet-5-5, medium (medium) | 100.0% ± 0.0% (n=34) | 100.0% | 69.0% ± 14.0% (n=42) | [1, 1] | 3.81 | 3.89 | FAIL | 0 |
| v4 | sonnet-5-5, high (high) | 100.0% ± 0.0% (n=34) | 100.0% | 52.4% ± 15.1% (n=42) | [1, 1] | 6.55 | 6.52 | FAIL | 0 |

Ladder spend: $18.91 list / $18.90 rate card. Project total: $19.96 list / $19.90 rate card (cap $50; overnight stop $20).

\*Shadow = re-graded from the stored transcripts with the proposed grader fix (below); the official grades are unchanged. Wald intervals collapse to ±0.0% at 100%; the Wilson 95% lower bound is 89.8% for 34/34 and 81.6% for 17/17, so "100%" here means "at least about 90%".

## The walk's decisions, and why

1. **baseline: Opus 4.8, default effort.** The session reports `xhigh`. Root cause 34/34 on train+test sets the floor at ≥ 90.0%.
2. **v1: Sonnet 5.5 low.** The entry cell, since the highest cost-plausible tier at low effort is Sonnet once Opus 5.5 is excluded. **Fail**, on format (61.9% ± 14.7%, clearly below 95%, so no retest). Root cause passes. The official `reg-verbatim` miss is the grader bug.
3. **v2: Opus 4.8 low, the round-0 diagnostic.** The effort dial is alive on Opus: output tokens 4,371 → 1,735 per session, cost 24.1¢ → 13.7¢, latency 68 s → 32 s, with root cause and format both 100%. Off the path, as pre-registered.
4. **v3: Sonnet 5.5 medium.** One notch right after the fail. **Fail**, on format (69.0%).
5. **v4: Sonnet 5.5 high.** The second and last notch right. **Fail**, on format (52.4%).
6. **Stop.**
   - The Sonnet row is exhausted after two notches right.
   - On a fail, tier monotonicity presumes Haiku fails at the same effort.
   - The only extension tier is Opus 5.5, which is excluded.
   - Cumulative list cost reached $19.96, which is also the $20 overnight stop.

Every cell got a one-session canary first: `pilot/sonnet-5-5-{low,medium,high}`, `pilot/opus-4-8-low`. Each canary reported the requested effort level back.

## errors.jsonl

- **Ladder cells:** none. 189 sessions, 0 failed attempts, 0 retries recorded.
- **pilot/probe-budget:** 1 row, class `budget`. That was deliberate (1¢ cap).
- **pilot/probe-timeout:** 1 row, class `timeout`. Deliberate, after the watchdog fix.
- **Not in any errors file:** the first launch of v1 crashed in setup, before any session ran (registry race, below). Nothing was billed.

## Three things found overnight that need your decision

1. **The grader misreads a sha followed by a period.** In "`de6541f`. The refactor…" the identifier is read as `de6541f.`, which fails the hex match. Two v1 rows were affected, one of them the `reg-verbatim` rep. The fix is one line, in `proposals/grader-trailing-punctuation.patch`, and it's pinned by two strict-xfail tests. It's not applied, because `graders.py` is a harness path. I took walk decisions only where the official and shadow verdicts agreed, and they agreed on every cell.
2. **Registry race between concurrent runs.** Launching baseline and v1 together crashed v1 in setup: both processes wrote `.registry.json` through the same temp file. I ran everything one at a time afterwards rather than change `run.py`. The fix (a per-process temp file plus a file lock) is described in `docs/plan.md`. It's not applied.
3. **The format rule is stricter than the baseline.** Opus 4.8 itself scores 92.9% format, which would fail the ≥ 95% rule it sets for others. The rule is pre-registered and I didn't change it. But as written, a cell has to be more format-disciplined than the incumbent to pass. Every format miss in every cell is an extra sentence on the root-cause line; none is a missing line.

## What I'd consider next (not started)

- **Phase 8 on Sonnet 5.5 low.** Its only failure looks prompt-addressable: a rule like "the root-cause line is exactly one sentence; put the fix elsewhere". That's the case the hillclimb is for, at 6.4× cheaper. The round-0 diagnostic suggests effort won't fix it.
- **Or reconsider Opus 4.8 low** as a candidate. It passes the floor outright at 13.7¢ (43% cheaper), but it was pre-registered as off-path, so including it is your call, not mine.
- **Haiku 5.5 was never run in the ladder**, and this is the one place the walk's pruning rests on an assumption the data don't support. Tier monotonicity is a *quality* assumption (at fixed effort, quality rises with tier), but what failed every Sonnet cell is *verbosity*, and nothing says verbosity is monotone in tier: a smaller model may well be terser. 42 sessions, about 85¢ list.

**Reading the chart:** it plots the *official* grades, so Sonnet low sits at 97.1% with an error bar the other Sonnet cells don't have. After the grader fix and an in-place regrade it moves to 100%. It isn't less accurate than Sonnet medium.
