# Build brief: "Your SRE agent works. Now make it cheap."

For: a Claude Code plan-mode session in Steffany's fork of `anthropics/cwc-workshops`.
Companion doc: `docs/sre-agent-eval-poc-plan.md` (the why, the findings, the deliverables). Read it first.
Window: tonight (Tue Oct 13) and all day Wed Oct 14. Goal: every deliverable in the plan doc (D1–D8) done before the first interview on Thu Oct 15. The scope is the plan doc's scope; nothing is added here.

---

## Paste this into Claude Code to start

> Read `docs/sre-agent-eval-poc-plan.md`, then this brief (`docs/BUILD_BRIEF.md`), then everything in `ship-your-first-managed-agent/`. Load the claude-api skill and read `shared/evals/build-eval.md`, `shared/evals/eval-hillclimb.md`, `shared/evals/cost-hillclimb.md`, `shared/evals/report/SCHEMA.md`, `shared/managed-agents-core.md` and `shared/managed-agents-events.md`.
>
> Stay in plan mode. First, work through the "Verify before planning" checklist below against the actual repo and docs, and report every place the brief is wrong. Then write the implementation plan to `docs/plan.md`, organized by the phases in this brief, with file-level steps and the acceptance check for each phase. Start `SOURCES.md` with every API field, model ID and docs page the plan relies on. Don't write any code until I approve the plan.

---

## Ground rules (apply to every phase)

**Tooling**
- Use `uv` for all Python (`uv run`, `uv add`, a `pyproject.toml` for the new eval folder). Don't use bare `pip` or `python`.
- Credit Gagan Bhat's original workshop in every README you touch. The repo is Apache-2.0.

**Secrets and answer keys**
- Never commit secrets. Confirm `.env` is gitignored before the first commit.
- The answer key must never be reachable by the agent under test. It never goes into an uploaded file, a tool result, the system prompt, or anything mounted into the sandbox. Keep answer keys in `evals/cases/<id>/answer.json`, and only the grader reads them.

**Spending**
- Use a key created inside a dedicated workspace with a spend limit. Unscoped keys fail with a 400 asking for the `anthropic-workspace-id` header.
- Set a session budget (`budget.max_list_cost`) on every eval session. The amount is an integer string in cents (`"100"` = $1.00; decimal forms like `"1.00"` are rejected with a 400). Start at `"100"`, and lower it for Haiku once the pilot shows real costs.
- Don't launch any grid run without first printing the estimated session count × measured pilot cost, then waiting for Steffany's OK.

**Change management**
- Don't break the original lab. `agent.py`, `agent_complete.py` and the dashboard must still work exactly as before. Change 1 below is the only edit to existing files, and it must be behavior-preserving.
- The analyzer that proposes hillclimb changes only ever reads train-split traces, which is the claude-api skill's rule. Neither the analyzer nor the outer Claude Code session uses the README or `e2e.py` as evidence for a prompt change.

---

## Verify before planning

The brief was written without access to the running repo. Check each claim, and report any that are wrong instead of building around them.

**About the repo**
1. `e2e.py` passes when the lowercased transcript contains ("n+1" or "n + 1") **and** "a3f9c21". `get_recent_deploys` returns every commit hash, so the right hash can appear without being concluded. A correct answer that says "per-row query" without saying "N+1" fails.
2. `data/generate_log.py` writes only `app.log`. It's seeded (42) and hardcodes the one scenario. `metrics.json`, `deploys.json` and `diff.txt` are static fixtures.
3. `get_diff` serves only `diff.txt`, and returns "no diff" unless the requested commit's first 7 characters appear in it.
4. The model is hardcoded to `claude-opus-4-8` in `agent_complete.py` and `e2e.py`. `e2e.py` keeps its own `SYSTEM` and `TOOLS` instead of importing them from `provided.py`.
4a. The SDK is pinned to `anthropic==1.13.0`, and `skills.create` takes `display_name` (renamed from `display_title`; fixed in all three files on this branch). Build against this SDK version.

**About Managed Agents**

5. An agent's `model` accepts `{"id": ..., "effort": ...}`. Effort set on the agent is applied. The public docs say effort inside a per-session `agent_with_overrides` model isn't applied, and the claude-api skill says it is. A live probe (`scripts/probe_results.md`) found it applied on Sonnet 5.5, and suggestive on Haiku 5.5. The plan uses agent versions regardless.
6. `sessions.create` accepts `budget={"type": "limit", "max_list_cost": {"amount": "<cents>", "currency": "USD"}}`. Confirmed live: a decimal amount like `"0.25"` returns a 400.
7. The stream emits `span.model_request_end` with `model_usage`, and emits `session.usage` with `list_cost`.
8. `claude-sonnet-5-5` and `claude-haiku-5-5` are accepted as agent models, at low and high effort (confirmed live by the probe).

**About the claude-api skill**

9. Its runner contract: `results.jsonl` rows, `traces/<id>_rep<k>.json`, `errors.jsonl`, `baseline/` and `vN/` directories, `_state.json` with `metrics`, `harness_paths`, `train_ids`, and the harness-integrity gate.

---

## Scope (exactly the plan doc's Changes 1–6, nothing more)

**Change 1. One config.**
- What: a single `config.py` (or `agent_config.toml`) holding the system prompt, model and effort.
- Who reads it: `provided.py`, `agent_complete.py`, `e2e.py`, and the new runner.
- Constraint: it must not change behavior. The original lab still runs on `claude-opus-4-8` with the same prompt.

**Change 2. Parameterized generator and case set.** Refactor `generate_log.py` so a scenario spec (a YAML or dataclass per case) drives everything in one pass:
- the log (target 5–10k lines, not 70k)
- `metrics.json`, derived from the same timeline as the log
- `deploys.json`
- `diffs/<sha>.txt` for every deploy, with plausible harmless diffs for the non-culprits
- `answer.json`

`handle_tool` reads from the case directory, and `get_diff` serves any deploy's diff. The cases are the Level 0 and Level 1 variants of the original story (see the case table below). There are no new failure-type generators.

**Change 3. Runner.** `evals/run.py`, built to the claude-api skill's contract.
- **Flags:** `--variant`, `--model`, `--effort`, `--reps`, `--cases`, `--concurrency` (default 4).
- **Each session:** a fresh session with a budget, pinned to an agent version. Upload that case's log, serve that case's tools, and enforce a timeout (default 600s).
- **Each row records:**
  - `usage`, summed from `span.model_request_end`
  - `list_cost` from `session.usage`
  - `model`, taken from the response or session rather than from config
  - tool-call counts
  - whether `get_recent_deploys` was called before the first sandbox command
  - `latency_s`
- **Failures** go to `errors.jsonl`.
- **Agents:** reuse agents across runs, keyed by (model, effort, prompt hash), instead of creating an agent per run. Keep a small local registry file of the agent IDs.

**Change 4. Two code graders** (`evals/graders.py`, pure functions with no network).
- `format`: the `**Root cause:**` line is present and is one sentence.
- `root_cause`: the commit or component parsed from that line equals the answer key.
  - Accept a 7- or 40-character hash, with or without backticks or bold.
  - Accept the line with Markdown wrapping around it. In the real smoke-test run, Opus 4.8 wrote it inside a blockquote: `> **Root cause:** `a3f9c21` — ...`. Add that exact line as a unit-test fixture.
  - On no-culprit cases, require a component name and reject any commit hash.
- Report-only (not gated): runbook order, tool calls, tokens, cost, latency.
- No LLM judge.

**Change 5. Model × effort ladder.** See "Run plan" below. Use agent-level effort with one agent version per (model, effort). Don't use per-session overrides for model or effort, even though the probe found them working. Agent versions are uncontroversial and free.

**Change 6. One system-prompt hillclimb** via `/claude-api hillclimb` on the chosen target model.
- In scope: the system prompt.
- Off limits: the runbook skill, the tools, the graders, the generator.
- Rounds: 2–4.
- Split: by case family (see below).

**Tests.** `uv run pytest` passes offline and covers:
- grader edge cases
- that the generator is deterministic for a given spec
- that the regression case reproduces the original story: culprit `a3f9c21` on checkout at 14:31:18, with the auth red herring
- that no answer key is reachable from any tool output or uploaded file

**Out of scope** (listed in the plan doc as "what would come next," not built now):
- new failure-type generators
- an LLM judge
- editing the runbook skill
- dashboard changes
- fast mode and the higher model tiers

## Case families and split

| Family | Cases | Split |
|---|---|---|
| Original + rephrased pages ("checkout is throwing 500s", "what happened around 14:40?", "is auth the problem?") | 3–4 | **regression check**: must pass every round, not scored as generalization |
| Shifted deploy (culprit moved in time) | 1–2 | train |
| Rolled back (one deploy marked rolled back) | 1–2 | train |
| Innocent message (harmless-sounding culprit commit) | 1–2 | train |
| Decoy deploy (another service deploys a minute or two before/after the culprit) | 1–2 | **test** |
| No culprit (no deploy lines up; `db-primary` or an upstream dependency is the cause) | 1–2 | **test** |

That's about 10–12 cases. The test families each check a different reasoning step from the train families, so a prompt change that only memorizes the train cases won't carry over. No-culprit also covers the opposite failure: an agent that always blames the nearest deploy shouldn't score well. Expect the skill's noise check to ask for more repetitions; use 2–3.

## Run plan and budget gates

**Known data point** (smoke test, Oct 13): the original `e2e.py` on Opus 4.8 with the full 70k-line log took about 3 minutes and cost $0.22 per session.

**Gate 0. Pilot.** Run the regression case once each on Opus 4.8 and Haiku 5.5. Print the measured cost per session and the wall time. Estimate every later tier from these numbers, never from guesses.

**Tier 1. Baseline ladder** (all cases × 2 reps, at default effort): Opus 4.8 (baseline), Opus 5.5, Sonnet 5.5, Haiku 5.5. Gate: print the session count × pilot cost, then wait for OK.

**Tier 2. Effort** (all cases × 2 reps): Sonnet 5.5 at low, and Haiku 5.5 at low. Add more effort levels only if Tier 1 leaves the target model unclear.

**Sanity check after Tier 1** (the blog's first sign of a healthy eval): stronger models and higher effort should score at least as well.
- If Haiku matches Opus at about 100%, the cost result stands on its own. Skip the hillclimb, and note "harder failure-type cases" as the next step in the write-up.
- If no model clears roughly 50%, look for a grader or harness bug before blaming the models.

**Choosing the target model.** Pick the cheapest (model, effort) within the noise band of the baseline accuracy, or the cheapest one with clear headroom, if hillclimbing could plausibly close the gap.

**Hillclimb rounds.** Use train + test + the regression check, 2 reps, capped at 4 rounds. Stop early once the skill's noise check says a further gain can't be measured.

Run grids in the background (the skill's pattern) while working on the teaching layer.

---

## Lab design (learner-facing)

**Story.** Two weeks after the 2am page, finance flags the SRE agent's per-incident cost and asks whether a cheaper model would catch the same root causes.

**Shape.** 45 minutes, five checkpoints. Learners write about three small functions, mirroring the original's seven; the repo provides the rest.

| # | Learner writes | About | Checkpoint output |
|---|---|---|---|
| 1 | `grade_root_cause(transcript, answer)` | 10 lines | Grader unit tests go green |
| 2 | Fix the e2e grader | (discussion + swap in #1) | A transcript the old check passed now correctly fails |
| 3 | `session_cost(events)` | 6 lines | A pilot case prints its tokens and dollars |
| 4 | Swap the config to `claude-haiku-5-5`, low effort (no new function) | 1 line | One case runs on Haiku at low effort |
| 5 | (none; run the ladder or load recorded results) | – | The skill's report page shows accuracy versus cost per incident by model and effort |

**Stretch, for fast finishers.** Run one `/claude-api hillclimb` round, and read the keep/revert decision in the skill's report.

**Way back.** `lab_complete/` plus the `results/` snapshot. Every checkpoint has an "expected output" block in the README.

---

## Timeline (everything done Wednesday night)

| When | Phase | Done when |
|---|---|---|
| Tue evening, first ~hour | Key and probe (done), fork (done), SDK fix + pin and smoke test (done: PASS, about 3 minutes, $0.22), Change 1, plan mode, plan approved | `docs/plan.md` approved |
| Tue evening | Changes 2–4 + tests; Gate 0 pilot | `uv run pytest` green; pilot cost printed |
| Tue late | Launch Tier 1 in the background | Rows landing in `baseline/` and variant directories |
| Wed morning | `/claude-api build-eval` review: inputs page, grader check, baseline + CI; Tier 2 in the background | Baseline score + noise estimate; ladder table |
| Wed midday | `/claude-api hillclimb` on the target model | Test result with CI, or "within noise, not merged" |
| Wed afternoon | Teaching layer (D2, D3, D5, D6): README checkpoints, `lab/` + `lab_complete/`, `results/` snapshot, SOURCES.md, cost ledger, facilitator guide | A fresh clone completes every checkpoint from the README alone, with no API key |
| Wed evening | D7 + D8: rehearse as a learner on a fresh clone, then record the 5–8 minute video and write the one-page summary | Video + one-pager done |

**If behind schedule, cut in this order:**
1. Tier 2 (effort)
2. Extra repetitions beyond 2
3. The hillclimb (present the ladder result alone)
4. The Spanish segment of the video

Don't cut the regression check, the tests, the cost ledger, the reference solution, or the rehearsal.

## Deliverables checklist (final state of the fork)

- [ ] `ship-your-first-managed-agent/` still works exactly as the original (smoke-tested)
- [ ] `config.py` as the single source for prompt, model and effort
- [ ] `evals/`: generator, cases, runner, graders, tests, `_state.json`, `pyproject.toml`
- [ ] `evals/lab/` + `evals/lab_complete/` + `evals/results/` snapshot
- [ ] `README` for the new lab, with story, checkpoints, expected outputs, credit to the original, and a one-command demo
- [ ] `SOURCES.md`: every API field, model ID and claim mapped to its docs page, including the effort-override finding
- [ ] `COST_LEDGER.md`: real spend per tier, per model, per round, from `session.usage`
- [ ] `FACILITATOR_GUIDE.md`: timing, where learners get stuck, talk track for the grader moment, rate-limit fallback, a "ready to teach" checklist
- [ ] `docs/plan.md`, plus a session log appended after the build
- [ ] Video (5–8 minutes) and a one-page summary

---

## Open questions for Claude Code to raise, not decide

- If Managed Agents rate limits throttle concurrency 4, propose a slower schedule rather than retrying in a tight loop.
- If the original regression case fails on Opus 4.8 in the new runner but passed in `e2e.py`, stop. That's a harness bug, not a model result.
- Any place this brief contradicts the repo, the skill, or the live docs.
