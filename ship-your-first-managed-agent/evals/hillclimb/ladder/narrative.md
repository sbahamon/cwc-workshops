# Ladder: summary (updated evening 2026-10-14)

**Current result.** The cheapest cell that clears the pre-registered floor is **Sonnet 5.5 at low effort with the climbed system prompt** (`hillclimb/climb/v1`): root cause 100% on train+test (68/68), format 97.6% (82/84), `reg-verbatim` right on all 4 reps, at **3.41¢ per incident at the rate card (3.33¢ list) versus 24.02¢ (24.07¢) for Opus 4.8 at default effort: 7.0× cheaper**. One prompt change did it: the root-cause line is one sentence, written once, last. The walk then stepped down to **Haiku 5.5 low with the climbed prompt (v5): it fails the floor** (root cause 88.2%, format 92.9%; both within noise). Three of Haiku's four root-cause misses name the right answer but drop the bold `**Root cause:**` label, so the grader can't find the line; it would still fail on format with a lenient label rule. C0.4 would give a within-noise fail one more run (about 75¢ list); not run, per Steffany's instruction to stop after the Haiku result.

| cell | model, effort, prompt | root cause train+test | format | reg-verbatim | ¢/incident rate card (list) | floor |
|---|---|---|---|---|---|---|
| baseline | Opus 4.8, default (xhigh), shipped | 100% (34/34) | 92.9% | [1, 1] | 24.02 (24.07) | reference |
| v1 | Sonnet 5.5, low, shipped | 100% | 61.9% | [1, 1] | 3.75 (3.74) | fail |
| v2 | Opus 4.8, low, shipped (diagnostic) | 100% | 100% | [1] | 13.65 (13.71) | off path |
| v3 | Sonnet 5.5, medium, shipped | 100% | 69.0% | [1, 1] | 3.89 (3.81) | fail |
| v4 | Sonnet 5.5, high, shipped | 100% | 52.4% | [1, 1] | 6.52 (6.55) | fail |
| climb/v1 | Sonnet 5.5, low, **climbed** (4 reps) | 100% (68/68) | **97.6%** | [1, 1, 1, 1] | **3.41 (3.33)** | **pass: incumbent** |
| v5 | Haiku 5.5, low, climbed | 88.2% (30/34) | 92.9% | [1, 1] | 0.42 (1.79) | fail (within noise) |

Spend: **$23.53 list / $22.95 rate card** of the $50 cap. Chart: `results/path.svg`; ledger: `COST_LEDGER.md`; climb: `hillclimb/climb/narrative.md`.

---

The overnight summary below is kept as written that morning (with the grader-fix notes added).

## Overnight summary (2026-10-14 morning)

**Headline.** Every cheaper cell found the root cause as reliably as Opus 4.8. All three Sonnet 5.5 cells scored 100% root cause on train+test (after the grader fix below). Sonnet 5.5 low did it at **3.7¢ per incident against 24.1¢, 6.4× cheaper**. But **no cell cleared the pre-registered floor**: every Sonnet cell failed the **format** rule (the root-cause line must be one sentence, ≥ 95% of rows). Sonnet keeps adding a second sentence such as "Reverting it should restore the batched query". More effort made that worse, not better. The walk stopped where its rules say it stops; the incumbent is still the baseline. Phase 8 was not started.

Chart: `results/path.svg` (and `.png`). Per-case table: `hillclimb/ladder/report.html` (lite builder).

## Cells

| cell | model, effort (echoed) | root_cause train+test (95% CI) | before fix* | format (95% CI) | reg-verbatim | list ¢/incident | rate card ¢/incident | floor | errors |
|---|---|---|---|---|---|---|---|---|---|
| baseline | opus-4-8, default (xhigh) | 100.0% ± 0.0% (n=34) | 100.0% | 92.9% ± 7.8% (n=42) | [1, 1] | 24.07 | 24.02 | reference | 0 |
| v1 | sonnet-5-5, low (low) | 100.0% ± 0.0% (n=34) | 97.1% | 61.9% ± 14.7% (n=42) | [1, 1] | 3.74 | 3.75 | FAIL | 0 |
| v2 | opus-4-8, low (low) | 100.0% ± 0.0% (n=17) | 100.0% | 100.0% ± 0.0% (n=21) | [1] | 13.71 | 13.65 | diagnostic (off path) | 0 |
| v3 | sonnet-5-5, medium (medium) | 100.0% ± 0.0% (n=34) | 100.0% | 69.0% ± 14.0% (n=42) | [1, 1] | 3.81 | 3.89 | FAIL | 0 |
| v4 | sonnet-5-5, high (high) | 100.0% ± 0.0% (n=34) | 100.0% | 52.4% ± 15.1% (n=42) | [1, 1] | 6.55 | 6.52 | FAIL | 0 |

Ladder spend: $18.91 list / $18.90 rate card. Project total: $19.96 list / $19.90 rate card (cap $50; overnight stop $20).

\*Before fix = the official grade before the trailing-punctuation grader fix (applied 2026-10-14 morning; every row regraded in place, two v1 rows changed, no verdict changed; `docs/plan.md`, Post-results changes). Wald intervals collapse to ±0.0% at 100%; the Wilson 95% lower bound is 89.8% for 34/34 and 81.6% for 17/17, so "100%" here means "at least about 90%".

## The walk's decisions, and why

1. **baseline: Opus 4.8, default effort.** The session reports `xhigh`. Root cause 34/34 on train+test sets the floor at ≥ 90.0%.
2. **v1: Sonnet 5.5 low.** The entry cell, since the highest cost-plausible tier at low effort is Sonnet once Opus 5.5 is excluded. **Fail**, on format (61.9% ± 14.7%, clearly below 95%, so no retest). Root cause passes. (Before the grader fix it also showed a `reg-verbatim` miss; that was the bug, and the regrade cleared it.)
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

## Three things found overnight, and what was decided (morning)

1. **The grader misreads a sha followed by a period.** In "`de6541f`. The refactor…" the identifier is read as `de6541f.`, which fails the hex match. Two v1 rows were affected, one of them the `reg-verbatim` rep. The fix is one line, in `proposals/grader-trailing-punctuation.patch`, and it's pinned by two strict-xfail tests. Overnight I took walk decisions only where the official and shadow verdicts agreed, and they agreed on every cell. **Decided:** fix applied, all rows regraded in place (exactly the two predicted rows changed; no verdict changed); harness re-approval needed.
2. **Registry race between concurrent runs.** Launching baseline and v1 together crashed v1 in setup: both processes wrote `.registry.json` through the same temp file. I ran everything one at a time afterwards rather than change `run.py`. The fix (a per-process temp file plus a file lock) is described in `docs/plan.md`. **Decided:** no code change; run cells sequentially, one `run.py` at a time (also in `FACILITATOR_NOTES.md`).
3. **The format rule is stricter than the baseline.** Opus 4.8 itself scores 92.9% format, which would fail the ≥ 95% rule it sets for others. The rule is pre-registered and I didn't change it. But as written, a cell has to be more format-disciplined than the incumbent to pass. Every format miss in every cell is an extra sentence on the root-cause line; none is a missing line. **Decided:** keep the floor as pre-registered. **Lesson for the write-up:** the baseline itself scores 92.9% on format, so an absolute threshold set without measuring the baseline against it asks the cheaper model to beat the incumbent, not match it. "No worse than baseline" and "≥ 95%" are different rules.

## What I'd consider next (not started)

- **Phase 8 on Sonnet 5.5 low.** Its only failure looks prompt-addressable: a rule like "the root-cause line is exactly one sentence; put the fix elsewhere". That's the case the hillclimb is for, at 6.4× cheaper. The round-0 diagnostic suggests effort won't fix it.
- **Or reconsider Opus 4.8 low** as a candidate. It passes the floor outright at 13.7¢ (43% cheaper), but it was pre-registered as off-path, so including it is your call, not mine.
- **Haiku 5.5 was never run in the ladder**, and this is the one place the walk's pruning rests on an assumption the data don't support. Tier monotonicity is a *quality* assumption (at fixed effort, quality rises with tier), but what failed every Sonnet cell is *verbosity*, and nothing says verbosity is monotone in tier: a smaller model may well be terser. 42 sessions, about 85¢ list.

**Reading the chart:** it plots the official grades, regenerated after the fix, so Sonnet low now sits at 100% with the other Sonnet cells.

## A fourth finding (morning, offline): the diffs alone solve the deploy cases

A shortcut agent that reads only the diffs (it names the deploy whose diff adds a per-row query, else one that disables a cache, else guesses `db-primary`; no log, no metrics, no timeline) scores **19/21**, against **11/21** for the hardened timeline shortcut. Its only misses are the two stripe cases its guess can't reach. So 100% root cause in this ladder shows that the cheaper models read the diffs correctly; it doesn't show that they triage timing, because no deploy case has a second defective diff to rule out. Pinned in `tests/test_shortcuts.py`; the cases were not hardened (that would change the harness and invalidate these cells). It doesn't affect the Phase 8 target, which is format.
