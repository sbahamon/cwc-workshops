# Proof of Concept: "Your SRE agent works. Now make it cheap."

A follow-on lab to Anthropic's *Ship Your First Managed Agent* workshop that adds an eval, a model cost ladder, and one system-prompt hillclimb, built with the `claude-api` skill's `build-eval` and `hillclimb` commands.

Author: Steffany Bahamon · Drafted October 13, 2026 · Updated October 14, 2026 with what actually happened (`docs/plan.md` is the detailed record)

## Results

| | Cost per incident (rate card) | Root cause, train+test | Held-out test root cause | Format | Floor |
|---|---|---|---|---|---|
| Opus 4.8, default effort (the workshop's model) | 24.02¢ | 100% (34/34) | 16/16 | 92.9% | baseline |
| **Sonnet 5.5, low effort, climbed prompt** | **3.41¢** | 100% (68/68) | **32/32** | 97.6% | **passes with margin** |
| Haiku 5.5, low effort, climbed prompt | 0.42¢ | 92.6% (63/68) | 27/32 | 95.2% | passes narrowly |

- **Deployment recommendation: Sonnet 5.5 at low effort with the climbed system prompt**, 7× cheaper than Opus 4.8 and passing the pre-registered floor with margin.
- **Haiku 5.5 at low effort is the walk's incumbent**, a narrow pass at 0.42¢: the cheapest cell that clears the floor, but only after the pre-registered confirmation run, and with every miss on held-out cases. It's the cost-optimal option once a prompt fix stops it dropping the bold root-cause label.
- Full numbers and spend: [`COST_LEDGER.md`](../ship-your-first-managed-agent/evals/COST_LEDGER.md). Chart: [`results/path.png`](../ship-your-first-managed-agent/evals/results/path.png).

---

## Part 1 — Why this exists

### The two roles this PoC targets

**1. Technical Enablement — Technical Curriculum Developer (12-month contract, via BayOne; SF, NYC, or remote)**

Tech Enablement owns the technical curriculum that Anthropic's go-to-market teams run on: courses, labs, demos, and presentations across Enterprise, Claude Apps, Claude Code, the Developer Platform, and Models/Protocol. The content backlog is growing faster than the team can curate it, and the Basecamp portfolio is live and scaling.

The role covers:

- curating existing materials into structured, reusable curriculum
- building new courses, labs, demos, and presentations
- keeping materials current every release cycle
- building hands-on exercises that work reliably in a live classroom
- documenting sources and structure so the curriculum survives handoff

The requirements that matter most here:

- able to build working demos and labs against APIs and AI products, not just describe them
- strong technical writing and instructional design
- self-directed

The hiring manager specifically wants someone who has built with LLM APIs. The first interview, with the hiring manager (Technical Enablement), is on October 15, 2026.

**2. Lead Technical Instructor (Anthropic, New York City)**

About half the time is spent delivering hands-on, instructor-led technical training in New York and remotely across European time zones. The other half is spent developing other instructors: train-the-trainer programs, observation and coaching, readiness calibration, and improving quality and consistency across programs. The role reports to the Head of Technical Training.

The posting describes the person as "an engineer who teaches and a teacher who makes other teachers better." It explicitly says this is *not* primarily an instructional design role. The candidate has to:

- write code
- debug technical systems
- build an agent live in front of a skeptical staff engineer
- fix a broken lab while the room waits

Minimum qualifications include recent hands-on AI development (LLM APIs, agents, tool use, MCP) and instructor development experience. Preferred qualifications include a portfolio of sessions or labs you designed and taught, plus material that lets others teach them.

### The LinkedIn post that sets the bar

Anthropic's hiring post for the Head of Technical Training and the Lead Technical Instructor names a specific workshop as the standard. It's Gagan Bhat's Code with Claude workshop, where a room of engineers built their first Claude Managed Agent in under an hour. That workshop is `ship-your-first-managed-agent` in `anthropics/cwc-workshops`, the same one this PoC extends.

The post lists seven things that made it great. They're the design checklist for this PoC:

1. **A real problem.** It opens with a 2am page for a checkout latency spike; attendees build the SRE agent that finds the cause.
2. **Approachable.** A repo handled setup and shipped a working dashboard, so people only wrote the agent: seven functions, about 38 lines.
3. **Complete.** Every core Managed Agents concept, in the order the docs introduce them.
4. **Fun to build.** The agent came online one function at a time, then searched a 70,000-line log and named the commit.
5. **A way back for anyone stuck.** A finished reference file let people catch up without stopping the room.
6. **Something to keep.** Swap the mock data for real monitoring tools and the same code works.
7. **Tested and rehearsed.** An end-to-end test proved the lab worked before anyone ran it, and the delivery was practiced.

The post closes by asking for a link to something you taught. This PoC is designed to be that link, for both roles.

### Why this particular project

- **It builds on the exact workshop the hiring post holds up as the standard.** A sequel that meets the same seven criteria shows curriculum built to Anthropic's own bar.
- **It closes a specific gap.** I've built against OpenRouter but not against Anthropic's first-party API. This project uses the Managed Agents API, the Files and Skills APIs, the session event stream, and the `claude-api` skill.
- **It's useful beyond the interview.** "Can a cheaper model do the same job?" is the most common production question after "does it work?" The lab answers it with measurement instead of opinion.
- **It's small.** It fits about five days of part-time work and a small, hard-capped API budget.

### Candidate background, as it relates to this PoC

- Six years at Darktrace as a technical curriculum developer and senior instructor:
  - grew the course catalog from 4 to 16
  - built 10 lab environments and 10 demo scenarios
  - built a 9-exam proctored certification program from zero
  - delivered 600+ live sessions in English and Spanish
  - onboarded four other instructors
  - taught remotely to Europe and in person across the Americas
- Prior software engineering at Capital One: REST APIs, cloud infrastructure, security data pipelines.

---

## Part 2 — Source material and what we found

### Sources

| Source | What it contributes |
|---|---|
| `github.com/anthropics/cwc-workshops/tree/main/ship-your-first-managed-agent` | The base workshop (Apache-2.0): Streamlit incident dashboard, `agent.py` with seven stub functions, `agent_complete.py`, `provided.py`, `e2e.py`, `incident-triage-runbook/SKILL.md`, and `data/` |
| claude.dev blog, *Automating eval design and hillclimbing with Claude* (Lance Martin, Sep 28, 2026) | The method: four elements of a good eval, adversarial sampling, grader validation, train/test splits, overfitting checks, and the cost-reduction and performance-improvement examples |
| `github.com/anthropics/skills/tree/main/skills/claude-api` | The `build-eval` and `hillclimb` commands, the cost-reduction guide (`shared/evals/cost-hillclimb.md`), the runner scaffold, and the Managed Agents reference docs |
| platform.claude.com Managed Agents docs and API reference | Supported models, the effort parameter, per-session overrides |

### Why this workshop and not another

All nine workshops in `cwc-workshops` were reviewed for whether they could support an eval and a hillclimb at all:

| Workshop | Verdict | Reason |
|---|---|---|
| `how-we-claude-code` | Not possible | The app is a plain to-do app with no model calls, so there's nothing to grade |
| `agents-that-remember` | Not possible | Only a README and a bootstrap script; needs research-preview access |
| `production-ready-agent` | Impractical | No eval at all; hard-to-grade multi-agent output; needs Linear |
| `research-desk` | Possible, but expensive | Already grades against a checkable-claims rubric, but each case is a full SEC-filing session |
| `agent-battle` | Possible, but fragile | Needs Minecraft and a self-hosted event server; results depend heavily on luck |
| `rightmodel` | Possible | A skill with no code, run on tau2-bench (a public benchmark, with leak risk) |
| `eval-driven-agent-development` | Possible, but heavy | Only 5 tasks; needs Docker, LibreOffice, and an Opus vision judge per slide |
| `agent-decomposition` | Strong | A real 12-task eval, but the lesson is a harness rewrite, which the blog says suits hillclimbing poorly |
| **`ship-your-first-managed-agent`** | **Chosen** | The workshop the hiring post praises. It's small, has a clear right answer, and contains a data generator and runbook that map directly onto eval cases |

### What's in the base workshop's data

- **`data/generate_log.py`** writes a seeded, deterministic, roughly 70k-line JSON log for 14:00–15:00 UTC on 2026-04-22. The story: commit `a3f9c21` deploys to checkout at 14:31:18 and replaces a batched query with a per-row loop (an N+1 query). The DB connection pool runs out at 14:40 and checkout starts failing. Unrelated auth errors around 14:15 that recover on their own act as a red herring.
- **`metrics.json`, `deploys.json`, `diff.txt`** are static, hand-written files the generator doesn't touch. There are four deploys: cart, auth, checkout (the culprit), and inventory.
- **`get_diff`** knows exactly one diff and returns "no diff" for any other commit.
- **The runbook skill** fixes the triage procedure:
  1. Check deploys first.
  2. Line them up against p99 latency and error rate.
  3. Read the diff.
  4. Grep the log only to confirm.
  5. If no deploy lines up, check DB pool utilization and upstream dependencies.

  It also lists five failure types that "have burned us": a per-row query replacing a batch, a removed cache decorator, a new query with no index, a blocking call in an async handler, and a retry loop with no backoff. And it fixes the output format: the reply ends with `**Root cause:** <sha> — one sentence on the mechanism`, with a component name in place of the commit when no deploy is at fault.
- **`e2e.py`** runs the full path headlessly and passes if the transcript contains both "n+1" and `a3f9c21` anywhere. This grader is the first teaching moment:
  - **Too strict, measured.** On the 289 recorded replies to deploy cases, the same check (each case's own sha) fails **40 correct answers**, every one of them describing the bug without the word "N+1", and passes **no wrong one** (`evals/checkpoint.py 2`).
  - **Too lenient, in theory only.** `get_recent_deploys` returns every commit hash, so a reply that recaps the deploys and floats "N+1" as one hypothesis would pass even if it blamed another commit. A written fixture shows this; no recorded agent did it.
- **The workshop no longer ran on the current SDK (found Oct 13).** `requirements.txt` only says `anthropic>=0.97.0`, and the current SDK (1.13.0) renamed `skills.create`'s `display_title` parameter to `display_name`. `e2e.py` and `agent_complete.py` crashed with a `TypeError`, and the hint in `agent.py` taught the old name. Fixed with a three-file rename, plus pinning `anthropic==1.13.0` so the next SDK release can't break the lab again.
- **Smoke test after the fix:** `e2e.py` passed on Opus 4.8 in about 3 minutes, at $0.22 for the session. The agent followed the runbook in order (deploys, then metrics, then diff, then log search to confirm) and ended with the root-cause line inside a Markdown blockquote (`> **Root cause:** ...`). The new grader has to handle that.
- **Model and prompt are duplicated.** The model is hardcoded to `claude-opus-4-8` in both `agent_complete.py` and `e2e.py`. `e2e.py` also keeps its own shorter copy of the system prompt and tool list instead of importing them from `provided.py`.

**Implication.** As shipped, there's one case and the model almost certainly solves it, so there's no headroom and no eval. The runbook supplies both the scenario catalog and the grading target, so nothing has to be invented.

### What we verified about Managed Agents

- **Models.** Claude 4.5 and later are supported on agents (public docs, and the `claude-api` skill's own reference). The model field accepts any model ID string, so current models work even though the API reference's list of model names doesn't show them yet.
- **Effort** is set inside the agent's model object, with levels low/medium/high/xhigh/max. Not every model accepts xhigh. Haiku 4.5 has no effort parameter, so use **Haiku 5.5**, which supports effort from low through max.
- **A documentation conflict.** The public docs say an effort level set inside a **per-session model override is not applied**: the session runs at the model's default effort, and you should set effort on the agent instead. The `claude-api` skill's docs say the override *is* applied.
  - **Tested live (Oct 13, $0.13, `scripts/probe_results.md`):** overrides *do* apply effort. On Sonnet 5.5, whose default is high, an override to low used 852 median output tokens versus 1,106 at agent-level high and 727 at agent-level low. If the override had been ignored, it would have run at high. Haiku 5.5 points the same way, but its low and high runs overlap at 3 repetitions, so it's suggestive rather than proof. The skill's docs are right; the public docs line looks out of date.
  - **Decision anyway:** create one agent version per (model, effort) and pin each session to that version. Both sources agree that works, creating agents is free, and it removes any dependence on the disputed behavior.
- **Session budgets** are hard spend caps per session, priced at list rates, that pause the session when reached. They're a built-in way to enforce the project's spend cap. The amount is an integer string in **cents** (`"25"` = $0.25); a decimal like `"0.25"` returns a 400, confirmed live.
- **API keys must be scoped to a workspace,** or every request needs an `anthropic-workspace-id` header (confirmed live). A key created inside a dedicated workspace with its own spend limit also caps the whole project's spend. The Admin API isn't needed.
- **Cost data is on the event stream.** `session.usage` carries cumulative tokens and list cost, including session running time at $0.08/hour. `span.model_request_end` carries usage per model call.

Model ladder pricing (per million input/output tokens, from the `claude-api` skill's model table):

| Model | Input | Output | Default effort |
|---|---|---|---|
| Opus 4.8 (workshop default, baseline) | $5 | $25 | high |
| Opus 5.5 | $4 | $20 | medium |
| Sonnet 5.5 | $2 | $10 | high |
| Haiku 5.5 | $0.10 | $0.50 (prompts ≤100K tokens) | medium |

### What we verified about the `claude-api` skill

- **It handles agents, though not Managed Agents specifically.** The `build-eval` and `hillclimb` guides are written for any Claude-powered app, and they cover agent cases explicitly:
  - inputs that include a workspace or container
  - a fresh, isolated environment for every trial
  - keeping answers structurally out of the agent's reach, including files its bash tool can open
  - proving that the knobs being tuned actually reach the agent
- **It has full Managed Agents reference docs** (agents, sessions, events, overrides, budgets), so Claude has what it needs to write the runner.
- **What we write ourselves:** the Managed Agents part of `runCase`. The runner scaffold is a Node file whose `runCase` stub is left for you to fill in. For projects without Node, the skill says to write the runner in the project's own language against the same output format, so a **Python runner run with `uv`** is within its instructions.
- **Its cost-reduction procedure:**
  1. Check that prompt caching is working, and recheck after every change.
  2. Walk model × effort early. With an eval in place, a cheaper model at lower effort is something you can measure safely.
  3. Edit the prompt after that.
- **It defaults to Opus** and won't move to a cheaper model on its own initiative, so the hillclimb setup must say explicitly that model and effort are in scope.

---

## Part 3 — The changes, what to do, and why

### Scope decisions

| In scope | Out of scope (and why) |
|---|---|
| Generated incident variants built from the existing story | New bug-type generators, unless Haiku aces everything (no need for harder cases without evidence of saturation) |
| Two code graders: format and root cause | LLM judge (the output is constrained, so a code check is cheaper and stable) |
| Model × effort staircase walk (the `claude-api` skill's `cost-hillclimb.md` Step 2), from Opus 4.8 down through Sonnet 5.5 to Haiku 5.5 | Opus 5.5 (excluded deliberately: cost, and to keep the story Opus 4.8 → Sonnet → Haiku); fast mode, Fable/Mythos tiers (cost goes the wrong way) |
| Effort as part of the walk: each cell visited is one (model, effort) agent version (the probe confirmed effort works) | A full four-model grid or effort grid (the walk visits only the cells it needs) |
| One system-prompt hillclimb on the cheapest viable model | Editing the runbook skill (it's the client's runbook; keep it fixed so attribution stays clean) |
| Cost per case from session usage events | Hand-maintained price math as the source of truth |

### Change 1 — One config file for what gets tuned

**What:** Move the system prompt, model, and effort into a single config file that `provided.py`, the dashboard, and the eval runner all read. Change `e2e.py` to import its prompt and tools instead of keeping its own copies.

**Why:** Each hillclimb patch should touch exactly one file. Today there are two system prompts and two hardcoded models, so you could tune one while the dashboard keeps using the other. A single source also makes "update the model each release," a core curriculum responsibility, a one-line change.

### Change 2 — A parameterized incident generator (the case set)

**What:** A new generator, `evals/generate.py`, where a scenario spec drives the log, the metrics, the deploys, and the diffs together (`data/generate_log.py` is left untouched, because the original dashboard imports it), keeping the metrics consistent with the log timeline instead of hand-written. Each scenario is written to its own folder with:

- a smaller log (target 5–10k lines instead of 70k)
- `metrics.json`
- `deploys.json`
- `diffs/<sha>.txt`
- an answer key stored *outside* anything that gets uploaded or returned by a tool

**Cases (21 total, 3–4 per family):**

| Family | Cases | What it tests |
|---|---|---|
| Original (regression) | The original incident, plus 2–3 rephrased pages ("checkout is throwing 500s", "what happened around 14:40?", "is auth the problem?") | That nothing breaks; the last one leans into the red herring |
| Shifted deploy | The culprit deploy moved in time | Reads the timeline rather than a remembered timestamp |
| Decoy deploy | Another service deploys a minute or two before or after the culprit | Matches deploy to the affected service, not just to the nearest time |
| Rolled back | One deploy marked rolled back | Reads deploy status |
| Innocent message | Culprit commit message sounds harmless (the original already does this) | Reads the diff instead of trusting the commit message |
| No culprit | No deploy lines up; pool exhaustion caused by `db-primary` or an upstream dependency | Doesn't blame a deploy that didn't cause it |

**Why:** The runbook already defines the failure modes and the no-deploy branch, so the cases come straight from the client's own procedure, which is what the blog means by "eval tasks mirror production." Each variant tests one specific reasoning step, so a failure points at a cause. The no-culprit case covers the opposite direction: an agent that always blames the latest deploy shouldn't score perfectly. Smaller logs keep repeated runs affordable.

### Change 3 — A headless eval runner (from `e2e.py`)

**What:** A Python runner, run with `uv run`, built to the skill's output format. For each case and repetition:

1. Create a fresh session with a budget, pinned to the variant's agent version.
2. Upload that case's log.
3. Serve the custom tools from that case's fixtures.
4. Stream events with a timeout.
5. Record `session.usage` and per-call usage.

Outputs: `results.jsonl` (one row per case and repetition), a trace file per run, `errors.jsonl` for failed runs, and `baseline/` and `vN/` directories so the skill's report builder and hillclimb loop can read them directly. Flags: `--variant`, `--model`, `--reps`.

**Why:** A fresh session and log upload per case means no state leaks between runs. Writing to the skill's exact format lets `/claude-api hillclimb` drive the loop and generate the results page without custom glue. Session budgets enforce the spend cap structurally rather than through a running counter.

### Change 4 — Two code graders

**Grader A, format:** the `**Root cause:**` line is present and is one sentence.

**Grader B, root cause:** parse the commit or component from that line and compare it to the answer key. Accept the short 7-character hash or the full 40-character hash, with or without backticks or bold. On no-culprit cases, require a component name and reject any commit hash.

**Reported but not graded:**

- whether `get_recent_deploys` was called before the first log search (the runbook's step 1)
- tool-call count
- tokens
- list cost
- wall time (it mostly reflects infrastructure, so it's reported only)

**Why:** The answer space is a small closed set (a hash from the deploy list, or a component name), so the blog says use the cheapest grader that fits: a code check. It's deterministic and free, so the "grade the same output twice" diagnostic passes trivially. Reporting format failures separately matters: if Haiku forgets the line, you can tell "didn't write the line" apart from "found the wrong commit," and the hillclimb aims at the right problem.

### Change 5 — A model × effort staircase walk

**What happened:** instead of running all four models at default effort, the lab walks the skill's staircase (`shared/evals/cost-hillclimb.md` Step 2) against a floor pre-registered before any result: root cause on train+test within 10 points of the Opus 4.8 baseline, the original incident right on every rep, and format ≥ 95%. Opus 5.5 is excluded deliberately (cost, and to keep the story Opus 4.8 → Sonnet → Haiku).

- **Baseline:** Opus 4.8 at default effort (it reports `xhigh` on Managed Agents).
- **Round-0 diagnostic, off the path:** Opus 4.8 at low effort, to check the effort dial is alive. It is: output tokens fell 4,371 → 1,735 per session.
- **Entry:** Sonnet 5.5 at low. It failed on format only, as did one and two notches right (medium, high). More effort made format worse.
- **After the prompt climb (Change 6):** Sonnet 5.5 low passed, and the walk stepped down to Haiku 5.5 low with the same prompt, which passed narrowly after the pre-registered confirmation run.

**Why:** the walk visits only the cells a decision needs, which is the skill's procedure and the blog's cost example (Opus 4.8 at high effort → a cheaper model at low → prompt edits). Every cheaper cell matched Opus 4.8 on root cause; what separated them was the format rule.

### Change 6 — One system-prompt hillclimb on the cheapest viable model

**What happened:** the target was Sonnet 5.5 at low effort, the walk's entry cell. Root cause was already saturated at 100%, so the working target was **format**, with root cause held. **One round, kept after a confirmation run:**

- **The change:** a fresh analyzer, given only train-split transcripts, found the root-cause line written as two sentences. One `system.md` change followed: the line is one sentence, written once, last, with anything else on its own line above.
- **First run:** format 40/42 (95.2%), right at the bar, so the pre-registered within-noise rule required a confirmation run.
- **Confirmation run:** 42/42. That gives 82/84 (97.6%) over 4 reps, with root cause 68/68 and 32/32 on held-out test.

The setup was as planned:

- **In scope:** the system prompt only. Model and effort were fixed at the target.
- **Off limits:** the runbook skill, the tool code and the graders.
- **Harness paths** (the runner, generator and graders) were registered, so the integrity check stops any round that edits them.
- **Split:**
  - **Train:** shifted, rolled-back, and innocent-message families.
  - **Test:** whole held-out families, decoy and no-culprit.
  - **Regression check:** the original family, which must stay passing every round but isn't scored as generalization.

**Why:** This mirrors the last step of the blog's cost example, where prompt edits on the cheaper model took it from 88.9% to 98.9%. A five-line system prompt is cheap to change and easy to attribute, which is what the blog says suits hillclimbing. Holding out whole families tests generalization rather than memorization.

The original stays out of the test set for three reasons:

- **It's one case**, so its score can only be 0% or 100%.
- **Its relatives would leak into training.** The rephrased variants share its identical log, and the other families are perturbations of the same story.
- **Its answer is visible to whatever proposes the prompt changes.** The README and `e2e.py` spell out `a3f9c21` and "N+1". The agent's sandbox can't see them, but the Claude Code session proposing changes can read the repo.

### Guardrails and risks

- **Keep the answer key structurally out of reach.** It never goes into the upload, a tool result, or the system prompt.
- **Watch for scenario-specific patches.** A prompt patch that names commit hashes, "checkout," or specific times is overfitting and gets reverted.
- **Noise.** With about 21 cases at 2 reps, the 95% interval on the full set is about ±15 points (`docs/plan.md` §B item 9). Expect the skill's noise check to ask for more repetitions; budget for 2–3.
- **Cost control.**
  - Run a one-case pilot first to measure real cost per session.
  - Set a budget on every session.
  - Pre-record the results for every walk cell and hillclimb round so the live lab never has to rerun Opus.
- **Rate limits in a live room.** Managed Agents has per-organization request limits, so the facilitator guide includes the pre-recorded fallback.
- **Beta API drift.** Managed Agents is in beta. Every model ID, field, and parameter used gets an entry in SOURCES.md with its docs page, so the next release cycle's update is a checklist rather than a rediscovery.

---

## Part 4 — Deliverables for the role proof of concept, and why

Each deliverable is mapped to the job requirements and to the LinkedIn post's seven criteria. The point is to show both halves of the bar: building curriculum, and teaching it in a way other instructors can repeat.

### D1 — Public repo: a fork of `cwc-workshops` with the new lab folder

**Contents:** the refactored generator, the case set, the Python runner (`uv`), the two graders, the shared config, the original workshop untouched beside it, and a clear credit line to Gagan Bhat's original (Apache-2.0).

**Why:**
- *TCD:* "build working demos and labs against APIs and AI products, not just describe them"; "build hands-on exercises that work reliably in live classroom settings."
- *Lead Instructor:* "recent hands-on AI development (LLM APIs, agents, tool use)"; "production engineering experience."
- *Post criterion 6 (something to keep):* the runner points at any Managed Agent, including the learner's own.
- Crediting the original shows the curation habit the TCD role asks for: building on existing material instead of starting over.

### D2 — Lab README written as checkpoints, with a "run it yourself" path

**Contents:**
- the story (two weeks after the 2am page, finance asks whether a cheaper model would catch the same root causes)
- prerequisites, and a one-command demo that runs in about 60 seconds
- five checkpoints, each with an expected output to compare against:
  1. Write `grade_root_cause`; the grader unit tests go green.
  2. Find and fix the `e2e.py` grader flaw: on the recorded replies the old check fails 40 correct answers and passes no wrong one; a written fixture shows the theoretical lenient case.
  3. Write `session_cost`; a pilot case prints its tokens and dollars.
  4. Swap the config to Haiku 5.5 at low effort; one case runs on it.
  5. Run the model ladder (or load the recorded results) and read the cost-reduction path chart (accuracy versus cost per incident).

  The final checkpoint list, with expected outputs, is the one in `docs/plan.md` (Phase 9).
- stretch for fast finishers: one `/claude-api hillclimb` round
- learners write two small functions plus a one-line config swap, mirroring the original's seven-function shape

**Why:**
- *Post criteria 2 and 4 (approachable, fun):* the repo does the setup, learners write only the interesting part, and the payoff is the path chart, where accuracy holds while cost per incident drops one step at a time.
- *Post criterion 3 (complete):* it covers eval concepts in the order the blog introduces them: cases, grader validation, baseline, headroom, split, hillclimb, overfitting.
- *TCD:* "strong technical writing and instructional design."

### D3 — Reference solution and pre-recorded results

**Contents:** `runner_complete.py` and `graders_complete.py`, plus a `results/` folder with real runs for every walk cell and the hillclimb round (traces, `results.jsonl`, `report.html`) and the path chart (`results/path.svg`/`.png`).

**Why:**
- *Post criterion 5 (a way back):* anyone stuck, out of budget, or rate-limited can follow along from recorded results without stopping the room.
- *Lead Instructor:* "diagnose a broken lab while a room of learners waits." The fallback is designed in from the start.

### D4 — Tests and a cost ledger

**Contents:**
- grader unit tests that run without network access, covering hash normalization, the no-culprit rule, and a missing root-cause line
- a generator determinism test
- one recorded end-to-end run
- `COST_LEDGER.md`: the actual spend per model, per case, and per round, taken from `session.usage`, with the budget each session ran under

**Why:**
- *Post criterion 7 (tested):* proves the lab works before anyone runs it.
- The ledger turns the lab's claim ("cheaper at the same accuracy") into evidence. It also shows working under a fixed budget, which matters for anything run at classroom scale.

### D5 — SOURCES.md

**Contents:** every API feature, field, model ID, and claim in the lab, mapped to its docs page or source file, including the per-session effort override conflict and how the lab avoids it.

**Why:**
- *TCD:* "document sources and structure so the curriculum is maintainable after handoff"; "keep materials current as products ship."
- When a model or beta field changes, this file is the update checklist.

### D6 — Facilitator guide (one to two pages)

**Contents:**
- a timing plan for a 45-minute delivery
- the three places learners usually get stuck, and what to say at each
- the talk track for the `e2e.py` grader moment
- what to say when Haiku fails a case
- the recovery plan if Managed Agents is slow or rate-limited (switch to pre-recorded results)
- known setup problems, both hit while building this lab: projects inside an iCloud-synced folder (Desktop or Documents) can hang on `import anthropic` because iCloud offloads `.venv` files to the cloud, so clone into a folder like `~/code`; and an API key not scoped to a workspace fails with a 400 asking for the `anthropic-workspace-id` header
- a short "ready to teach this" checklist another instructor can use to self-assess before delivering

**Why:**
- *Lead Instructor:* half the role is "making other instructors better"; "train-the-trainer"; "material you created so others could teach it."
- The readiness checklist echoes the Head of Technical Training's job of defining what "ready to teach" means, and it draws directly on having built and run a 9-exam certification program and onboarded four instructors.

### D7 — Short teaching video (5–8 minutes)

**Contents:** a recorded delivery of one checkpoint, not a tour of the repo.

- **Segment 1 (about 3 minutes):** the grader-validation moment. Lead with the measurement: on 289 real replies the original `e2e.py` check failed 40 correct answers and passed no wrong one. Mention the lenient case (it could pass without the agent concluding the right commit) as theoretical only. Explain why that matters for anyone deciding which model to ship, and fix it live with the two new graders.
- **Segment 2 (about 2 minutes):** run the model ladder from pre-recorded results and read the cost-reduction path chart.
- **Segment 3 (about 1 minute):** what changes when the learner points the runner at their own agent.

**Why:**
- The hiring post asks directly for "a link to something you taught."
- *Lead Instructor:* "make difficult technical concepts click"; "model excellent technical teaching."
- The grader moment is a self-contained concept with a reveal, which suits a short video.
- A Spanish-language version of one segment is an option worth considering, since bilingual delivery is a real differentiator for European and Americas audiences.

### D8 — One-page write-up for the interview

**Contents:**
- what was built and why this workshop
- the seven-criteria checklist with evidence for each point
- results, including the cheapest model that held accuracy and at what cost
- what didn't work
- what would come next: harder bug-type generators, an effort sweep, editing the runbook skill

**Why:** It gives the hiring manager a two-minute read that connects the artifact to the role, and the "what didn't work" section shows judgment rather than a polished demo.

### Timeline

**Done (as of Wed Oct 14 evening).** The build, the walk and the hillclimb are complete. The teaching layer (D2, D3, D5 final, D6, D7, D8) moved to a separate session, `docs/plan.md` Phase 9.

| When | Milestone | Status |
|---|---|---|
| Tue Oct 13 | Effort probe run ($0.13); fork created; SDK drift fixed and pinned; `e2e.py` smoke test passed on Opus 4.8 (about 3 minutes, $0.22) | done |
| Tue evening | Smoke-run `e2e.py`; Change 1; Claude Code plan approved; Changes 2–4 + tests (D1, D4); pilot cost; ladder started in the background | done |
| Wed morning | `build-eval` review and baseline; staircase walk; target model chosen | done |
| Wed midday | Hillclimb on the target model's system prompt | done (one round, kept) |
| Wed afternoon | README checkpoints, reference solution, recorded results, SOURCES.md, cost ledger, facilitator guide (D2, D3, D5, D6) | cost ledger and SOURCES.md done; the rest moved to Phase 9 |
| Wed evening | Rehearse on a fresh clone; video (D7) and one-pager (D8) | moved to Phase 9 |
| Thu Oct 15 | First interview. Full schedule and cut order are in `docs/BUILD_BRIEF.md`. | — |
