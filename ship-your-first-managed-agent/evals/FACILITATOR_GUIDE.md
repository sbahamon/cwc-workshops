<!-- Copyright 2026 Anthropic PBC -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Facilitator guide: "Your SRE agent works. Now make it cheap."

For whoever teaches [`README.md`](README.md). It's built on Gagan Bhat's original workshop,
*Ship Your First Managed Agent* (Apache-2.0), and assumes the room has done that workshop
or watched it.

The lab runs in 45 minutes with no API key: every checkpoint replays recorded runs from
`results/`. The only live step (`checkpoint.py 4 --live`, about 2¢) is optional.

## Ready to teach? Check yourself first

Do each of these on a fresh clone before you teach:

- [ ] `cd ship-your-first-managed-agent/evals && uv run pytest` passes with no API key set.
- [ ] `uv run python checkpoint.py all --solution` prints what the README's five expected
      blocks show. The tests check this too, but run it yourself so you've seen it.
- [ ] You've written `grade_root_cause` yourself, without `lab_complete/`, and hit at least
      one fixture failure. Learners will hit the same ones (see "Where learners get stuck").
- [ ] You can give the real-data finding on `e2e.py:104-105` from memory (it fails 40
      correct answers out of 289 recorded deploy-case replies and passes no wrong one),
      and say why the lenient case is only theoretical here.
- [ ] You can say what the pre-registered floor is (root cause within 10 points of the
      baseline, `reg-verbatim` right every rep, format ≥ 95%), why it was fixed before any
      result, and the one way it's flawed (the baseline itself scores 92.9% on format).
- [ ] You can explain `list_cost` vs the rate card, and why Haiku's two numbers differ.
- [ ] You've run `checkpoint.py 4 --live` once with a workspace-scoped key, and seen the
      row land in `lab_runs/`.
- [ ] You can answer "is Haiku good enough?" with both halves: the walk's verdict (a
      narrow pass) and the recommendation (climbed Sonnet 5.5 low, because of held-out
      margin).

## Timing plan (45 minutes)

| Minutes | Segment | What happens |
|---|---|---|
| 0–5 | The story | Finance asks if a cheaper model catches the same root causes. Name the two meanings of "harness" now (below). Show the one-command demo from your screen. |
| 5–15 | Checkpoint 1 | Learners write `grade_root_cause`. Circulate. Most time goes here. |
| 15–22 | Checkpoint 2 | The grader moment. Use the talk-track below; this is the segment people remember. |
| 22–30 | Checkpoint 3 | `session_cost`. Land the Haiku list-cost gap at the end. |
| 30–34 | Checkpoint 4 | The one-line swap. Volunteers with a key can try `--live`; everyone else reads the recorded canary. |
| 34–43 | Checkpoint 5 | Read the path chart together, top to bottom (README, "Reading the chart"). |
| 43–45 | Wrap | The recommendation, and what you'd do next (the bold-label prompt round; the stretch). |

If you're behind, cut in this order: the `--live` run, then checkpoint 3's second half
(learners take the reference with `--solution`), then the stretch mention. Never cut
checkpoint 2.

## Two meanings of "harness": say it early

> The *agent harness* is the loop around the model (prompting, tool calls, feeding
> results back). On Managed Agents, Anthropic runs it, and you only configure the
> agent. The *eval harness* is the measuring setup: cases, tools, graders, runner and
> cost calculation. This lab fingerprints the eval harness and requires a human approval
> whenever it changes, so every result is measured with the same ruler and a hillclimb
> can't raise its score by editing the grader. That's a method from the claude-api
> skill's hillclimb process, not something the API requires.

**Talk-track.** Name the two meanings as soon as learners first see `--approve-harness`
(the README's checkpoint 4 mentions it). Then use `docs/plan.md` → "Post-results changes"
as the worked example:

- **Three approvals.** The eval harness was approved at three fingerprints:
  - `9f02ee7a8a03`, before the pilot
  - `64ecf9d86b32`, after the watchdog fix and `pricing.py`
  - `c808e86bdb6d`, after the grader fix
- **Only the last change came after results existed.**
- **Why the grader fix was safe.** Grades are recomputed from saved transcripts. The
  agent saw exactly the same thing, and only the ruler's reading changed: two rows, no
  verdict.
- **Why the case hardening wasn't.** The hardening we declined (the diffs-only shortcut
  finding below) changes what the agent sees. Every existing result would have measured
  a different test, so the ladder would have to be re-run.

## Talk-track: the `e2e.py` grader moment (checkpoint 2, and video segment 1)

Lead with the measurement, not the hypothetical. The memorable fact is what the old check
did to real replies.

1. **Set it up.** Put `e2e.py:104-105` on screen:
   `("n+1" in full or "n + 1" in full) and "a3f9c21" in full`. Say: "This was the lab's
   only test, and it passed. We ran it on 289 real replies from the ladder. Guess how
   many it got wrong, and which way." Take a few guesses; most rooms guess "too lenient".
2. **The reveal.** It failed **40 correct answers** and passed **0 wrong ones**. All 40
   name the right sha but describe the bug in other words, such as a per-row query,
   without writing "N+1". Show the example line checkpoint 2 prints (`ladder/v1`,
   `dc-cart` rep 1). On real data, the old check is too strict.
3. **Why it matters now.** With one model and one test, nobody notices. The moment you
   compare models, a model that phrases things differently gets scored as wrong, and the
   cost decision is made on a broken ruler. "Validate the grader before you trust a
   result" is the habit.
4. **The theoretical side, briefly.** The check could also pass a wrong answer:
   `get_recent_deploys` returns every sha, so an agent that recaps the deploys, floats
   "could be an N+1" as one hypothesis, and then blames the wrong commit would pass.
   That's a written fixture, not something any recorded agent did. Say so plainly. Don't
   present it as the headline.
5. **Close.** The fix isn't a better regex over the whole transcript. It's a closed
   answer space: the runbook fixes a one-line output, and the grader reads only that line.

## Where learners get stuck, and what to say

1. **Checkpoint 1: the identifier.** Learners split on the em dash and stop, then fail
   "a sha followed by a period", "'commit' before the sha", or "component in plain
   words". Say: *"Print what your code thinks the identifier is for the failing fixture.
   The rules in the docstring are in the order you'll need them."* If someone is still
   stuck at minute 13, have them run `--solution` and read `lab_complete/grading.py`.
   Checkpoint 2 needs a working grader.
2. **Checkpoint 3: pricing.** There are three classic bugs:
   - forgetting rates are per **million** tokens (off by a factor of 1e6)
   - forgetting runtime ($0.08 per hour, so off by a fraction of a cent)
   - summing the session's tokens before pricing, which puts Haiku in the long-prompt tier
   Say: *"Your Opus number should round to the session's `list_cost` to the cent. If it
   doesn't, check the units. If only Haiku is wrong, price each request on its own."*
3. **Checkpoint 4: running from the wrong place.** `uv run` must run in
   `ship-your-first-managed-agent/evals/`, or the imports fail. For `--live`:
   - An unscoped API key fails with a 400 asking for `anthropic-workspace-id`. Create the
     key inside a workspace.
   - A cell other than the six recorded canaries prints "No recorded run". That's
     expected. Run it with `--live`, or pick a recorded cell.

## When Haiku fails a case

It will. On the recorded runs, Haiku 5.5 low missed 5 of 68 train+test root causes, all
on held-out test cases. What to say:

- **Open the miss.** Four of the five name the right answer and write a plain
  `Root cause:` without the bold label, so the grader finds no line. One blames an
  innocent deploy on a no-culprit case: that's a real reasoning miss.
- **Two metrics are deliberate.** "Didn't write the line" and "named the wrong commit"
  need different fixes, so they're scored separately. A smaller model drifts from the
  output template before it drifts on the reasoning.
- **Don't loosen the grader to make it pass.** The grader is part of the eval harness. A
  lenient-label rule would lift root cause to 66/68, but changing the ruler after seeing
  the score is exactly what the approval gate exists to stop. The honest next step is a
  prompt round aimed at the label, measured with the same floor.
- **The verdict was close, and the rule decided it.** Haiku failed at 2 reps (30/34,
  39/42) and passed at 4 (63/68, 80/84). The within-noise rule was pre-registered, which
  is the point.

## If the API is slow, rate-limited or down

Nothing in the core lab needs the API. Every checkpoint replays `results/`.

- **`--live` hangs or returns 429/529.** Stop it (Ctrl-C) and run `checkpoint.py 4`
  without `--live`. The recorded canary is the same case on the same cell. Managed Agents
  has per-organization rate limits, so a room of 30 hitting `--live` at once can trip
  them. Make `--live` a single volunteer's demo, not the room's.
- **A learner's environment is broken.** Pair them, or have them follow on your screen
  with `checkpoint.py all --solution`.
- **The `uv` install can't reach the network.** Run the demo from your machine. Ask
  learners to run `uv run pytest` once before the session, so the environment is cached.

## Known setup problems (both hit while building this lab)

- **iCloud-synced folders.** A project inside Desktop or Documents can hang on `import
  anthropic`, because iCloud offloads `.venv` files to the cloud. Clone into a folder like
  `~/code`.
- **Workspace-scoped keys.** An API key not scoped to a workspace fails with a 400 asking
  for the `anthropic-workspace-id` header. Create the key inside a workspace. A dedicated
  workspace with its own spend limit also caps the room's spend.

## Running the eval yourself (beyond the lab)

- **Run one `run.py` process at a time.** Run cells one after another, never two
  `run.py` commands in parallel. Two processes race on the shared registry temp file
  (`.registry.tmp` → `.registry.json`), and the second one crashes in setup. This
  happened once, with no sessions started and nothing billed. Within one cell,
  `--concurrency N` is safe: those are threads in one process, and the in-process lock
  covers them. The race is known and deliberately left unfixed (docs/plan.md,
  Post-results changes).
- **Probe each error path live once before a grid.** The watchdog's first live timeout
  hung. The offline fake couldn't show that; a 1¢ live probe did.
- **Audit the grader before trusting a failure.** Read only the grader's input on the
  failing rows. That's how the trailing-punctuation bug (`a3f9c21`. The…) was found.
- **Costs.**
  - Each walk cell is 42 sessions: about $10 on Opus 4.8, $1.60–2.80 on Sonnet 5.5, and
    $0.18 at the rate card on Haiku 5.5.
  - `run.py` refuses any run whose projection crosses the $50 cap.
  - `uv run python spend.py` shows where the money went.

## What I found in the original lab

Everything below has its evidence named. The first seven are about the workshop as
shipped; the rest came from building and running the eval.

**In the workshop as shipped:**

1. **The log gives away the culprit's deploy.** `data/generate_log.py:143` writes
   `deploy_complete` only for `a3f9c21`, so one grep for deploy events finds the culprit
   without reading anything else. Fix in the eval: every deploy and rollback in the window
   is logged (`evals/generate.py`, `background()`).
2. **The log gives away the query change.**
   - In the original log, the per-row `SELECT … WHERE order_id = ?` lines are the first
     database lines of any kind, so the culprit stands out without any reasoning about
     query shape.
   - The Phase 1 smoke run's agent said it directly: "first-ever `SELECT * FROM
     order_items …` query appears".
   - Fix in the eval: healthy requests log a batched `IN (?)` query, so the agent has to
     notice batched turning into per-row (`evals/generate.py`, `request()`).
3. **The e2e grader fails correct answers.** It passes only when "n+1" and the sha
   appear anywhere in the agent's text (`e2e.py:104-105`). On the 289 recorded replies to
   deploy cases it fails **40 correct answers**, each one describing the bug without the
   word "N+1", and passes **no wrong one** (checkpoint 2). In theory it's also too
   lenient: a recap of every deploy that floats "N+1" and blames the wrong commit would
   pass. But that's a written fixture, and no recorded agent did it.
4. **`get_diff` matches by substring.** `args["commit"][:7] in diff` returns the diff for
   any 7-character fragment of it, for example `order_i` (`agent_complete.py`, `e2e.py`).
   Fix in the eval: an exact sha match against the deploy list (`evals/tools.py`).
5. **e2e tested a different prompt from the one learners ship.** `e2e.py` kept its own
   shorter SYSTEM and TOOLS, so the Oct 13 smoke test didn't exercise the dashboard
   prompt. Fixed by Change 1 (`config.py`).
6. **The default effort isn't what the docs table says.** On Managed Agents, Opus 4.8 with
   no effort set reports `effort: xhigh`, not the skill table's `high`
   (sesn_01Vy3PfLW7MwY35zqBcV6Reg).
7. **Setup drift.**
   - The SDK rename (`display_title` → `display_name`) broke the lab on 1.13.0.
   - The README's license line says MIT, while the repo is Apache-2.0.
   - Streamlit's `use_container_width`, used in `provided.py` and `pages/1_Metrics.py`,
     was scheduled for removal after 2025-12-31.

**From building the eval: I ran a shortcut agent against my own eval.** The first
version of the case set scored 17/21 with a shortcut, so I hardened the cases until it
dropped to 11/21. A second shortcut still scores 19/21. Evidence:
`tests/test_shortcuts.py`, which pins the shortcut scores so these numbers can't drift.

- **The timeline shortcut: 17/21 → 11/21.**
  - The shortcut is "name the latest deploy to the paged service before the page". On
    the first case set it scored 17/21. Every deploy family was solvable from timestamps,
    and the commit-message and rolled-back traps never came into play.
  - The fix: a same-minute, guilty-sounding twin deploy for innocent_message, and a
    slow-burn culprit with a later rolled-back deploy for rolled_back. The shortcut now
    scores 11/21.
  - What's left: the held-out decoy family is still solvable by timing plus service
    matching (4/4). Only no_culprit defeats every shortcut, which is worth saying when
    reading test-split results.
- **The diffs-only shortcut: 19/21.**
  - It calls `get_diff` on every deploy and names the one whose diff adds a per-row query
    (else one that disables a cache, else it guesses `db-primary`). It never reads the
    log, the metrics or the timeline.
  - In this case set exactly one diff per deploy case is defective, so "find the bad
    diff" is enough. Its only misses are the two stripe cases its guess can't reach (it
    scores 18/21 if ties go to the earliest per-row diff).
  - The cases were not hardened, because that would change what the agent sees and
    invalidate the ladder. The natural fix is a decoy whose diff also adds a per-row
    query, on a service that never pages or deployed after onset, so only timing tells
    them apart.
  - This bounds what the ladder shows: 100% root cause means the cheaper models read the
    diffs correctly, not that they triage timing.

**Also from building and running it:**

- **The runner's watchdog hung on its first live timeout.**
  - Closing the event stream from a timer thread doesn't unblock a read already in
    progress.
  - The offline fake couldn't show this. The one-session watchdog probe in the pilot did,
    for 1¢.
  - Lesson: probe each error path live once before running a grid.
- **Haiku's metered cost differs from its rate card.** This is an observed difference,
  not a claimed bug.
  - Four Haiku 5.5 sessions reported `list_cost` of 1–2¢, against 0.16–0.47¢ at the
    published rates, with no request near the 100K tier. A 3.6–5.8× multiplier fits, and
    the >100K tier is 5×.
  - The Console bill for Oct 14 showed Haiku 5.5 at $0.01, against 6¢ summed `list_cost`
    and 1.35¢ at the rate card. Billing follows the rate card, and Haiku's `list_cost`
    reads about 5× the bill.
  - Usage confirmed each model served its own tokens (Sonnet 9.4M, Haiku 276K).
  - The chart's x axis is the rate card. `list_cost` stays the headline the cap enforces,
    and both are reported (`SOURCES.md`).
- **The headline result.**
  - Sonnet 5.5 at low effort, with one system-prompt change, clears the pre-registered
    floor at 3.41¢ per incident at the rate card (3.33¢ list). Opus 4.8 at default
    effort costs 24.02¢ (24.07¢ list), so that's **7.0× cheaper**.
  - Its scores: root cause 100% (68/68 train+test), format 97.6% (82/84).
  - The prompt change: the root-cause line is one sentence, written once, last.
  - Evidence: `hillclimb/climb/narrative.md`, `COST_LEDGER.md`, `results/path.svg`.
- **The deployment recommendation, separate from the walk's incumbent.**
  - **Deploy climbed Sonnet 5.5 low** (`hillclimb/climb/v1`). It passes the floor with
    margin: root cause 32/32 on held-out test (68/68 train+test), format 97.6%, 7×
    cheaper than Opus 4.8.
  - **Haiku 5.5 low is the walk's incumbent**, a narrow pass. It's the cost-optimal
    option, pending a bold-label prompt fix, listed as next work.
  - The walk ends at Haiku low; Haiku medium was not run.
- **The pre-registered confirmation rule ran twice and mattered both ways.**
  - It **confirmed** climb round 1: format 40/42 at 2 reps and 82/84 at 4, a pass both
    times.
  - It **changed** one verdict: Haiku 5.5 low went from fail at 2 reps (root cause 30/34,
    format 39/42) to pass at 4 (63/68, 80/84).
  - Decide the within-noise rule before the results, because it will decide verdicts.
- **One hillclimb round fixed what three effort levels couldn't.**
  - The analyzer saw the two-sentence habit in only 3 of 18 train rows. But most of the
    baseline's misses were on held-out test cases (12/16), and all of them recovered: the
    change described the behavior, not the cases.
  - It landed exactly on the floor at 2 reps (40/42), and the pre-registered within-noise
    rule bought a confirmation run (42/42).
- **Haiku 5.5 low with the climbed prompt passes the floor only narrowly, and only after
  the confirmation run.**
  - First 2 reps: root cause 30/34, format 39/42 (a fail, within noise). Reps 3–4: 33/34
    and 41/42.
  - All 84 rows: root cause 63/68 = 92.6%, format 80/84 = 95.24%, one row of margin.
  - Every miss is on held-out test: 27/32 there, against 32/32 for climbed Sonnet.
  - It costs 0.42¢ per incident at the rate card, 57× cheaper than Opus 4.8.
  - Of its first four root-cause misses, three name the right answer without the bold
    label. A lenient label rule would lift root cause to 33/34, but format would still
    fail.
  - Haiku also used more output tokens: 2,830 against about 1,180 per session for
    climbed Sonnet.
  - Lessons: a pooled train+test floor can hide a weaker held-out split, and a smaller
    model drifts from the output template before it drifts on the reasoning.
- **Before the climb, every cheaper cell matched Opus 4.8 on root cause.**
  - All three Sonnet 5.5 cells scored 100% on train+test once the grader was corrected.
    Sonnet low cost 3.7¢ against 24.1¢ per incident.
  - They failed only the runbook's one-sentence format rule, and more effort made format
    worse (low 61.9%, medium 69.0%, high 52.4%).
  - Evidence: `hillclimb/ladder/narrative.md`, `results/path.svg`.
- **Auditing the grader before trusting a failure paid off live.**
  - Reading only the grader's input on v1's failing rows showed that `dc-after` rep 1
    and `reg-verbatim` rep 1 named the correct sha but scored 0, because "`a3f9c21`.
    The…" read as `a3f9c21.`.
  - It was fixed after the results. The in-place regrade flipped exactly those two rows,
    and no walk verdict changed, so no walk decision depended on the bug.
- **The pre-registered format floor is stricter than the baseline it protects.**
  - Opus 4.8 at default effort scores 92.9% on format, below the ≥ 95% every candidate
    must clear, so a cheaper cell has to be *more* disciplined than the incumbent to pass.
  - The rule was kept as pre-registered.
  - Lesson: before pre-registering an absolute threshold, measure the baseline against
    it. "No worse than baseline" and "≥ X%" are different rules, and only the first
    follows from "make it cheap without making it worse".
