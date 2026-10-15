# Your SRE agent works. Now make it cheap.

Steffany Bahamon · October 14, 2026 · [the lab](../ship-your-first-managed-agent/evals/README.md) · [build record](plan.md)

**What I built.** A follow-on lab to Gagan Bhat's *Ship Your First Managed Agent* (Apache-2.0).
It asks the question every production agent gets after "does it work?": can a cheaper model
find the same root causes? It adds:

- 21 generated incidents
- two code graders
- a Managed Agents eval runner with per-session budgets and a $50 project cap
- a model × effort walk and one system-prompt hillclimb
- a five-checkpoint lab that replays it all offline

**Why this workshop.** It's the one Anthropic's hiring post holds up as the standard, so a
sequel has to meet the same bar. And it has what an eval needs: a closed answer, a runbook
that defines the failure modes, and a data generator.

## The seven criteria, with evidence

1. **A real problem.** The same 2am page, turned into 21 incidents in six families taken from the runbook's own steps ([`specs.py`](../ship-your-first-managed-agent/evals/specs.py)).
2. **Approachable.** Learners write two small functions and swap one line; [`checkpoint.py`](../ship-your-first-managed-agent/evals/checkpoint.py) `all --solution` runs in 3 s with no key.
3. **Complete.** It covers the eval concepts in the blog's order: cases, grader validation, baseline, held-out split, walk, hillclimb, and overfitting checks.
4. **Fun to build.** The learner's own code re-grades and re-prices 357 recorded sessions, and the payoff is the [path chart](../ship-your-first-managed-agent/evals/results/path.png).
5. **A way back.** [`lab_complete/`](../ship-your-first-managed-agent/evals/lab_complete/) plus `--solution`, and a [`results/`](../ship-your-first-managed-agent/evals/results/README.md) snapshot, so nobody waits on the API.
6. **Something to keep.** [`run.py`](../ship-your-first-managed-agent/evals/run.py) takes any model, effort and system prompt, and the graders and cost function carry over to your own agent.
7. **Tested and rehearsed.**
   - Tested: 241 offline tests pass on a fresh clone with no key, and the README's expected outputs are pinned by [`test_lab.py`](../ship-your-first-managed-agent/evals/tests/test_lab.py).
   - Facilitated: a [facilitator guide](../ship-your-first-managed-agent/evals/FACILITATOR_GUIDE.md) is written.
   - Rehearsed: **not yet**. The live rehearsal is still to do.

## Results

| | ¢ per incident (rate card) | Root cause, train+test | Held-out test | Format | Floor |
|---|---|---|---|---|---|
| Opus 4.8, default effort (baseline) | 24.02 | 34/34 | 16/16 | 92.9% | reference |
| **Sonnet 5.5 low, climbed prompt** | **3.41** | 68/68 | **32/32** | 97.6% | **passes with margin: deploy this** |
| Haiku 5.5 low, climbed prompt | 0.42 | 63/68 | 27/32 | 95.2% | passes narrowly: the walk's incumbent |

The floor was pre-registered before any result. One prompt change made the difference: the
root-cause line is one sentence, written once, last. Sonnet is 7.0× cheaper than Opus; Haiku
is 57× cheaper but clears format by one row. Spend: $24.28 list against the $50 cap.
Evidence: [chart](../ship-your-first-managed-agent/evals/results/path.png), [ledger](../ship-your-first-managed-agent/evals/COST_LEDGER.md), [climb](../ship-your-first-managed-agent/evals/hillclimb/climb/narrative.md).

## What I found

- **The original lab leaks the answer twice.** The log writes `deploy_complete` only for the culprit (`data/generate_log.py:143`), and its per-row queries are the first DB lines of any kind. The generator fixes both.
- **A shortcut agent beat my first case set.** It scored **17/21** without reading any evidence. Hardening brought that to **11/21**, but a diffs-only shortcut still scores **19/21** ([`test_shortcuts.py`](../ship-your-first-managed-agent/evals/tests/test_shortcuts.py)).
- **The old `e2e.py` check fails correct answers.** On 289 recorded replies it failed **40 correct answers** (none says "N+1") and passed **no wrong one**. The lenient case only shows up in a written fixture.
- **The pre-registered confirmation rule changed a verdict.** Haiku failed at 2 reps and passed at 4. The same rule confirmed the climb round.
- **Haiku's metered cost reads about 5× its billed cost.** Its `list_cost` doesn't match the Console bill, which followed the rate card, so the chart uses the rate card ([`SOURCES.md`](../ship-your-first-managed-agent/evals/SOURCES.md)).
- **SDK drift broke the lab.** `display_title` was renamed to `display_name` in SDK 1.13.0. I fixed it and pinned the version.

## What didn't work

- **More effort made format worse.** Sonnet scored 61.9% at low, 69.0% at medium and 52.4% at high. A prompt change fixed it; effort couldn't.
- **My format floor (≥ 95%) is stricter than the baseline it protects.** Opus scores 92.9%. I should have measured the baseline before fixing an absolute threshold.
- **A grader bug surfaced after the results.** A sha followed by a period was graded wrong. Regrading from saved transcripts flipped two rows and no verdicts.
- **My runner's watchdog hung on its first live timeout,** and two `run.py` processes running at once raced on a shared temp file.
- **The case set still leaks through the diffs** (the 19/21 above). So the ladder proves the models read diffs correctly, not that they triage timing.

## What's next

1. **A prompt round for Haiku's dropped bold label.** Four of Haiku's five misses are right answers without the `**Root cause:**` label. Re-measure against the same floor.
2. **Cases that can't be solved by reading diffs alone.** Add a decoy whose diff also adds a per-row query, on a service that never pages, so only timing separates them. This changes what the agent sees, so the ladder must be re-run.
3. **Evals through the dashboard itself.** Today the lab's Streamlit viewer (`evals/viewer.py`) only reads recorded results. Next would be driving the workshop's real chat panel on eval cases with Streamlit AppTest, or replaying eval sessions in its session picker. Both need changes to the original lab (`docs/plan.md`, "What would come next").
