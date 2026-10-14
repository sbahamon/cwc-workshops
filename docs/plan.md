# Implementation plan: "Your SRE agent works. Now make it cheap."

Status: approved Oct 13, 2026, with Steffany's amendments (§C0). Companion docs: `docs/sre-agent-eval-poc-plan.md` (why) and `docs/BUILD_BRIEF.md` (brief). §B is the verification report against the repo, the installed SDK and the claude-api skill docs; where §B or §C0 disagrees with the brief, this file wins. Paths in §C are relative to `ship-your-first-managed-agent/`.

---

## A. Context

The workshop's agent works on Opus 4.8. The open question is whether a cheaper model, or a lower effort level, finds the same root causes. This build adds:
- a case set generated from the original story
- two code graders
- a Managed Agents eval runner built to the claude-api skill's contract
- a model × effort ladder
- one system-prompt hillclimb
- the teaching layer (D1–D8)

Everything goes in a new `evals/` folder. Change 1 is the only edit to existing files.

---

## B. Verify-before-planning report (where the brief is wrong)

| # | Claim | Verdict | Evidence / correction |
|---|---|---|---|
| 1 | e2e passes on ("n+1" or "n + 1") and "a3f9c21" in the lowercased transcript | **Confirmed**, with a nuance | `e2e.py:104-105`. The transcript is only `agent.message` text; tool results aren't in it. So the hash passes only when the agent *writes* it, for example while recapping deploys. "Per-row query" without "N+1" fails. |
| 2 | `generate_log.py` writes only `app.log`, seeded 42, one hardcoded scenario; the other three files are static | **Confirmed** | The docstring says "~60k lines". The actual file has 69,740 lines (the README says 70k). |
| 2b | (brief Change 2) "Refactor `generate_log.py`" | **Conflicts with the brief's own ground rule** | Only Change 1 may edit existing files, and `app.py:21` imports `data.generate_log.main` to auto-build the log. **Plan:** a new generator in `evals/generate.py`; `data/generate_log.py` stays untouched. |
| 3 | `get_diff` serves only `diff.txt`, "no diff" unless the first 7 characters appear | **Confirmed**, quirk noted | It's a substring test against the *whole diff text* (`args["commit"][:7] in diff`), so any 7-character fragment such as `order_i` returns the diff. The two copies' miss strings also differ: e2e returns `"no diff"`, `agent_complete` returns `"no diff for that commit"`. The new handler does an exact sha-prefix match against the deploy list. |
| 4 | Model hardcoded to `claude-opus-4-8` in `agent_complete.py` and `e2e.py`; e2e keeps its own SYSTEM/TOOLS | **Confirmed**, with a hidden decision | e2e's SYSTEM is a *different, shorter* prompt, and its tool descriptions differ too. **The $0.22 smoke test ran the e2e prompt, not the dashboard prompt.** Pointing e2e at the shared config changes e2e's behavior, so Change 1 is not purely behavior-preserving for e2e. **Plan:** `provided.py`'s prompt and tools become canonical (it's what learners and the dashboard run), and e2e gets re-smoke-tested after Change 1 (≈$0.22, gated). |
| 4b | (brief Change 1) config read by `provided.py` and the runner | **Needs a constraint** | `provided.py` imports streamlit and reads `Path("data")` relative to the working directory at import time. `config.py` must be importable without streamlit; `provided.py` and `e2e.py` import *from* it, never the reverse. |
| 4a | SDK pinned `anthropic==1.13.0`; `skills.create(display_name=)` | **Confirmed** | `requirements.txt`; the installed `.venv` is 1.13.0. Note: the stable `client.skills` and `client.files` namespaces also exist (Skills and Files are out of beta per the skill), and the workshop's `client.beta.*` calls still work. New code mirrors the workshop's proven `beta` calls, and SOURCES.md records the drift risk. |
| 5 | Agent `model` takes `{id, effort}`; override effort disputed | **Skill side confirmed; public-docs side unverified here** | `managed-agents-core.md` §Effort/§Override says override effort **is** applied, which matches `scripts/probe_results.md`. I didn't re-read the public docs page in this session, so SOURCES.md marks the "public docs say not applied" line as *unverified, per Oct 13 notes*. Plan uses agent versions regardless. Note: the probe file lives at the **repo root** `scripts/`, not in the workshop folder. |
| 6 | `budget={"type":"limit","max_list_cost":{"amount":"<cents>","currency":"USD"}}` | **Confirmed** | SDK `sessions.create(budget=BetaManagedAgentsBudgetLimitParam)`; core doc §Session budgets (integer-string cents, USD only). |
| 7 | Stream emits `span.model_request_end.model_usage` and `session.usage.list_cost` | **First half confirmed; second half unreliable as stated** | `model_usage` has 4 token fields, **and no model id**. `session.usage` is documented in the budget-pause sequence; the SDK docstring says "periodic snapshot", but nothing guarantees it on a normal `end_turn`. **Plan:** after idle, `sessions.retrieve(id).usage` (`list_cost`, `active_seconds`) is the source of truth, and any streamed `session.usage` is logged as a bonus. The Gate 0 pilot records which one actually arrives. |
| 7b | (brief Change 3) row `model` "taken from the response" | **Not available** | No event carries a served-model id. The closest available value is `session.agent.model` (the snapshot at creation). The scaffold's served-model assertion becomes "the session's echoed model and effort equal the requested ones". This gap is documented. |
| 8 | Sonnet 5.5 and Haiku 5.5 accepted as agent models at low and high | **Confirmed** | probe_results.md §1. (Haiku low-vs-high medians 1507 vs 1947, ranges overlap: suggestive, as the PoC doc says.) |
| 9 | Runner contract: `results.jsonl`, `traces/<id>_rep<k>.json`, `errors.jsonl`, `baseline/` + `vN/`, `_state.json` (`metrics`, `harness_paths`, `train_ids`) + integrity gate | **Confirmed**, with additions | Also: `test_ids`/`val_ids`; `harness_sha` written only by `--approve-harness` (that flag is yours to pass, never mine); `_state.json` is otherwise read-only to the runner; variant dirs must be exactly `baseline` or `v<N>`; case fixtures must live *outside* the flow dir. |

**Other places the brief is wrong or silent:**
1. **Only the lite report builder is installed** (`build-report-lite.mjs`; the full `build-report.mjs` isn't extracted). It shows the primary metric per variant, a test mean and trace links: **no cost column, no CIs, no transcripts**. Checkpoint 5's "report page shows accuracy vs cost" therefore needs its own deliverable. *Per the amendments, that's the path chart `evals/results/path.svg`/`.png` plus the table in COST_LEDGER.md.*
2. **The ladder doesn't fit `baseline`/`vN` naming.** Plan: two flow dirs. `evals/hillclimb/ladder/` has baseline = Opus 4.8 and v1…vN = each walk cell visited, in order. `evals/hillclimb/climb/` has baseline = the chosen target and v1…v4 = prompt rounds.
3. **`.claude/` is gitignored** in `ship-your-first-managed-agent/.gitignore:7`, so the skill's default `.claude/hillclimb/` would never be committed. Plan: `evals/hillclimb/`.
4. **Answer reachable through the internet.** The workshop environment is `networking: unrestricted` (so the web tools work), and `a3f9c21`/"N+1" are in the public README and `e2e.py`. Plan: an eval-only environment with `limited` networking and no `allowed_hosts`. That blocks web_search and web_fetch structurally (skill pitfall) while TOOLS stays identical to the shipped agent.
5. **The original log leaks the culprit.** `generate_log.py:143` logs `deploy_complete` only for `a3f9c21`. Generated cases log deploy_complete (and rollback) lines for **every** deploy. The verbatim regression case keeps the original as-is.
6. **Smaller logs vs the "regression fails here but passed in e2e → harness bug" rule.** That rule only means something if one case uses the **exact original fixtures** (70k log, the original data files, e2e's user prompt). Plan: `reg-verbatim` is that parity case. The other regression cases use the generated small-log reproduction.
7. **Hillclimbing `config.SYSTEM` would change the original lab mid-loop**, which breaks "don't break the original lab". Plan: the runner reads `evals/prompts/system.md`, initialized byte-identical to `config.SYSTEM` (a test asserts this at baseline). The hillclimb edits that file. Promoting the winner into `config.py` is a separate reviewed commit, and your call.
8. **Split deviates from the skill on purpose.** The guide says random stratified; the brief holds out whole families. That's deliberate, and recorded. Regression IDs go in `val_ids`, so the lite builder labels them and keeps them out of `test`. They're never handed to the analyzer as evidence.
9. **Noise.** Fixed by going to about 21 cases. Expected 95% half-width: test 8 × 2 reps ≈ ±25 points; full set 21 × 2 ≈ ±15 points.
10. **The brief's ladder isn't the skill's staircase walk** (`cost-hillclimb.md` Step 2), and it omits **Opus 5.5 at low**, the cell the skill says most often wins. *Resolved by Steffany's amendments (§C0):* the search is now the staircase walk, and Opus 5.5 is excluded deliberately, with the reason recorded.
11. **`budget_reached` and timeouts need pre-registered handling.** Both go to `errors.jsonl` (class `budget` / `timeout`), never scored. The budget is set at ≥3× the pilot's p95 so it fires only on runaway sessions.
12. **A per-case wall-clock check inside the stream loop only runs when an event arrives** (SSE heartbeats, per-chunk timeouts). Plan: a watchdog thread per case that sends `user.interrupt` and closes the stream at 600s.
13. **Pricing basis.** `list_cost` includes $0.08/hr session runtime, but `model × usage` doesn't. Both are recorded. **The headline cost is `list_cost`** (per the brief), and `cost_usd` (tokens only) is reported beside it.
14. **License.** The repo `LICENSE` and the SPDX headers say Apache-2.0, but the workshop `README.md` footer says "MIT". New READMEs credit Apache-2.0, and the discrepancy is noted (the original README isn't edited).
15. **Upload per session (brief) vs upload per case.** Each session gets a fresh container, and the mounted file is a read-only copy, so one upload per case's log (cached by sha) is equally isolated and cheaper. The plan does that.

---

## C. Implementation plan

Paths are relative to `ship-your-first-managed-agent/`. Every acceptance check is a command plus its expected output.

### C0. Amendments (Steffany, Oct 13; these override the brief where they differ)

1. **Cost search = the staircase walk** (`cost-hillclimb.md` Step 2), replacing the brief's Tier 1/Tier 2 grid.
2. **Exclusion: Opus 5.5 is not in the grid.** Reason: cost, and to keep the lab's story Opus 4.8 → Sonnet → Haiku. This is a recorded, deliberate exclusion. It is not an oversight.
3. **Pre-registered floor**, fixed now, before any ladder result exists. A cell passes only if all three hold:
   - `root_cause` on train+test is within **10 points** of the Opus 4.8 baseline
   - **every** `reg-verbatim` run passes
   - `format` ≥ **95%**
4. **Walk cells:**
   - **Baseline:** Opus 4.8 at default effort, 2 reps. *Measured 2026-10-14: on Managed Agents that default echoes as `xhigh`, not `high`; every cell's effective effort is read from the session echo and written into its `change.md`.*
   - **Round-0 diagnostic:** Opus 4.8 at low, 1 rep, all cases. Off the path, drawn grey on the chart.
   - **Entry:** Sonnet 5.5 at low, 2 reps.
   - **On a pass:** step down to Haiku 5.5 at low, only if it's projected under the incumbent's cost (projected from pilot texture at matched effort).
   - **On a fail:** step right, at most two notches (Sonnet 5.5 medium, then high).
   - **Prune** by incumbent cost.
   - Cost-hillclimb rules 2 and 3 apply: a pass or fail within noise of the floor gets one more run before the walk moves.
5. **Flow dirs:** every visited cell becomes `vN` in `evals/hillclimb/ladder/`, numbered in visit order. Its `change.md` records the model, the effort, and why the walk went there.
6. **Regression rule:**
   - `reg-verbatim` must pass on Opus 4.8 (harness parity).
   - During the climb, the val (regression-family) score must not drop below the climb baseline's val score. 100% is **not** required.
7. **Spend cap, $50 for the whole project.**
   - `evals/spend.py` sums `list_cost_usd` over every `results.jsonl` and `errors.jsonl` under `evals/hillclimb/` and `evals/pilot/`, plus the Phase 1 smoke-test cost recorded in `evals/pilot/manual.jsonl`.
   - `run.py` prints the cumulative spend and the projected cost of the run (cases × reps × the matching pilot p95) at every gate.
   - It refuses to start any run whose projection would push the cumulative total past $50.
8. **The path chart replaces `ladder.html`, and it's a core deliverable that is never cut.**
   - `evals/plot_path.py` (run with `uv run`, matplotlib added to the dependencies) writes `evals/results/path.svg` and `path.png`, modeled on Fig. 8 of the claude.dev hillclimbing post.
   - **x axis:** mean list cost per incident, log scale.
   - **y axis:** `root_cause` accuracy on train+test, with 95% CI error bars.
   - **Adopted path:** baseline → each walk cell kept → each kept hillclimb round, drawn as numbered points connected by dashed arrows, with a dashed "starting accuracy" line.
   - **Unadopted cells,** including the round-0 diagnostic, are grey and unconnected.
   - **Labels** look like "Sonnet 5.5, low effort — 88.9% at 1.0¢".
   - Every number is read from `results.jsonl`, plus `_state.json`/`change.md` for adoption, with nothing typed in by hand.
   - `COST_LEDGER.md` also carries a Markdown accuracy × $/incident table generated by `ledger.py`.
9. **Tonight's target:** through Phase 5 (pilot), then launch the ladder baseline and Sonnet 5.5 low in the background.

### Phase 0: files from this plan (no API spend)
- Write `docs/plan.md` (§A–C) at the repo root and `evals/SOURCES.md` (§D).
- Confirm `.env` is ignored: `git check-ignore -v ship-your-first-managed-agent/.env` → `.gitignore:5:.env`. (Already true at the root, and in the workshop's `.gitignore:1`.)
- **Accept:** both files exist; `git status` shows only them.

### Phase 1: Change 1, one config (the only edit to existing files)
- **New `config.py`** (no streamlit import):
  - `MODEL = "claude-opus-4-8"`
  - `EFFORT = None`. None means the model is sent as a bare string, so the create request is byte-identical to today's.
  - `SYSTEM` and `TOOLS`, moved verbatim from `provided.py`
  - `RUNBOOK_DIR`
  - `model_param()`, which returns the bare string or `{"id", "effort"}`
- **`provided.py`:** replace the SYSTEM and TOOLS literals with `from config import SYSTEM, TOOLS`. The rest is unchanged.
- **`agent_complete.py`:** `model=model_param()`.
- **`e2e.py`:**
  - import SYSTEM, TOOLS and `model_param` from `config`, and delete its local copies
  - keep `handle()`, the user prompt and the verdict logic exactly as they are (checkpoint 2 needs the old flawed check)
- **`agent.py`:** untouched. The learner writes `model=` themselves.
- **Accept:**
  - `uv run --no-project python -c "import config, provided; assert provided.SYSTEM is config.SYSTEM"` (the workshop has no `pyproject.toml`; `--no-project` runs in its uv-created `.venv`, which `uv pip install -r requirements.txt --dry-run` confirms matches `requirements.txt`)
  - `git diff --stat` touches only `provided.py`, `agent_complete.py`, `e2e.py`, plus the new `config.py`
  - `streamlit run app.py` loads, and all 4 pages render offline
  - **gated, ≈$0.22:** `uv run --no-project python e2e.py` → `verdict: PASS` with the canonical prompt (record cost and wall time)

### Phase 2: parameterized generator, case set, isolation (no API spend)
- **`evals/pyproject.toml`:**
  - dependencies: `anthropic==1.13.0`, `python-dotenv`; dev dependency: `pytest`
  - `[tool.pytest.ini_options] pythonpath = [".", ".."]`
  - `uv lock` → `evals/uv.lock`
- **`evals/scenario.py`:** a `Scenario` dataclass with these fields:
  - `id`, `family`, `prompt`
  - `affected_service`, `window`, `seed`
  - `deploys[]` (sha, service, ts, status ∈ success/rolled_back, summary, author, diff_kind ∈ n_plus_one/harmless_*)
  - `culprit_sha | None`
  - `component | None` (`db-primary` / `stripe-api`)
  - `red_herrings[]` (auth idp blip, …)
  - `target_lines` (≈6–8k)
- **`evals/generate.py`:** one pass per spec writes `evals/cases/<id>/fixtures/{app.log, metrics.json, deploys.json, diffs/<sha>.txt}` and `evals/cases/<id>/answer.json`. Details:
  - Metrics are aggregated per minute from the same simulated requests: p99 and error_rate for every service, `db_pool_utilization` for every service (the runbook step 5 needs it; today only checkout has it).
  - Every deploy and rollback is logged.
  - Harmless diff templates are used for the non-culprit deploys.
  - Logic is reused from `data/generate_log.py` by copying, since that file stays untouched.
- **`evals/specs.py`:** the case list (about 21):

| Family (`tags[0]`) | n | Split | Design |
|---|---|---|---|
| regression | 4 | val | `reg-verbatim` (original `data/` files + 70k log + e2e prompt) plus 3 rephrased pages on the generated reproduction ("checkout is throwing 500s", "what happened around 14:40?", "is auth the problem?") |
| shifted | 3 | train | Culprit deploy at different times; window adjusted |
| rolled_back | 3 | train | A same-service deploy before the spike, marked `rolled_back` before onset; the real culprit is later |
| innocent_message | 3 | train | Culprit message harmless, plus an innocent deploy whose message *sounds* guilty ("perf: rework query layer") |
| decoy | 4 | **test** | Another service deploys 1–2 min before/after the culprit; in 2 of the 4 the affected service is cart rather than checkout |
| no_culprit | 4 | **test** | No deploy lines up; pool exhaustion from `db-primary` (2) or a slow upstream `stripe-api` (2); auth red herring kept |

- **`evals/tools.py`:** `CaseTools(case_dir)` with the same three tools and the same miss strings as `agent_complete.handle_tool`. It reads only `fixtures/`. `get_diff` does an exact match of the 7-char prefix against the shas in `deploys.json`.
- **Tests** (`evals/tests/test_generator.py`, `test_isolation.py`):
  - generating the same spec twice gives a byte-identical tree
  - the regression spec gives culprit `a3f9c21` on checkout at 14:31:18Z, pool exhaustion around 14:40, and auth idp errors around 14:15 that recover
  - metrics agree with the log: p99 per minute recomputes from the log within tolerance
  - every path `CaseTools` can return, and every uploaded path, is under `fixtures/`
  - no fixture contains `answer`, `culprit`, `root_cause` or the component key
  - `prompts/system.md == config.SYSTEM`
- **Accept:** `cd evals && uv run python generate.py` → about 21 case dirs; `uv run pytest -q tests/test_generator.py tests/test_isolation.py` → all pass, no network.

### Phase 3: two code graders (no API spend)
- **`evals/graders.py`**, pure functions:
  - `find_root_cause_line(text)`: the last line containing `**Root cause:**`, after stripping leading `>`, whitespace and list markers.
  - `grade_format(text)`: the line exists, and its body after the label is one sentence. "One sentence" means: split on `[.!?]` followed by whitespace and then an uppercase letter or a backtick; that yields exactly 1 non-empty segment. Dots inside tokens (`handlers.py`, hashes) don't split.
  - `grade_root_cause(text, answer)`:
    - the first token after the label, with `` ` ``, `*` and quotes stripped
    - a 7–40-character hex token gives `sha[:7] == answer.culprit_sha[:7]`
    - on no-culprit cases, a hex token fails, and otherwise the normalized component must be in `answer.components`
  - `grade_legacy_e2e(text)`: the old check, for checkpoint 2.
- **Fixtures** (`evals/tests/test_graders.py`, pre-registered before any run):
  1. the real Opus 4.8 line `` > **Root cause:** `a3f9c21` — … `` (blockquote, backticks, em dash) → pass/pass
  2. 40-char hash with bold → pass
  3. a recap of all deploys plus "could be an N+1", concluding `9f1e2d4`: legacy **pass**, new **fail**
  4. correct answer saying "per-row query": legacy **fail**, new **pass**
  5. no-culprit with a hash → fail
  6. no-culprit `db-primary` → pass
  7. missing line → format 0, root_cause 0
  8. two-sentence line → format 0, root_cause still graded
- **Accept:** `uv run pytest -q tests/test_graders.py` → all pass; grading the same input twice gives identical results.

### Phase 4: runner, registry, eval environment (no paid runs yet)
- **`evals/run.py`:** a Python port of the `runner-scaffold.mjs` properties.
  - Flags: `--flow`, `--variant`, `--model`, `--effort`, `--reps`, `--cases`, `--concurrency 4`, `--timeout-s 600`, `--budget-cents 100`, `--spend-cap-usd 50`, `--dry-run`, `--approve-harness`.
  - **Setup (cached in `evals/.registry.json`, gitignored):**
    - one runbook skill, uploaded once with a unique `display_name`, `version` pinned if accepted (else `latest`, with the runbook sha in the key)
    - one eval environment, `networking: limited`
    - agents keyed by sha256(model, effort, system, tools json, skill id/version), created only on a key miss
    - file ids per case log sha
  - **Per (case, rep):**
    1. `sessions.create(agent={"type":"agent", id, version}, environment_id, resources=[file → "app.log"], budget, metadata={case, rep, variant})`
    2. open the stream, then send the user message (stream-first)
    3. serve `agent.custom_tool_use` from `CaseTools`
    4. stop on `session.status_idle` with `end_turn`; record `budget_reached` / `requires_action` / timeout as error classes
    5. watchdog → `user.interrupt`
    6. `sessions.retrieve()` → `usage.list_cost`, `active_seconds`, echoed `agent.model`
    7. assert the echoed model and effort match the request, else an error row
    8. archive the session
  - **Row** (`results.jsonl`, appended per case; resume key (case, rep)):
    - `prompt_id`, `rep`, `prompt`, `tags=[family, …]`
    - `grade={root_cause, format}`
    - `model`, `usage` (summed from `span.model_request_end`)
    - `latency_s`, `tool_calls`, `stop_reason`, `status`, `list_cost_usd`
    - `meta` = {session_id, console_url, agent_id/version, effort, active_seconds, deploys_before_first_sandbox_call, sandbox_calls, custom_calls, retries, session_usage_event_seen}
  - Plus `traces/<id>_rep<k>.json` (system / user / tool_call / tool_result / assistant turns), `errors.jsonl` (class, retries, usage if any), and a summary line with the mean and Wald CI.
  - Writes and resumes are idempotent.
  - Creates use jittered backoff with counted retries (SDK `max_retries=0` on wrapped calls).
  - **Harness gate:** sha over `run.py`, `uv.lock` and `_state.json.harness_paths` (graders.py, tools.py, generate.py, specs.py, scenario.py, config.py). Exit 2 on mismatch.
- **`evals/hillclimb/ladder/_state.json`:**
  - `metrics=[root_cause binary "Root cause", format binary "Format"]`
  - `perf_fields` = list cost, latency, tool calls, out tokens
  - `train_ids`, `test_ids`, `val_ids`, `harness_paths`, `reps: 2`
  - `goal = {target: "list_cost_usd", direction: "lower", hold: ["root_cause"]}`
- **Eval audit (`eval-audit.md` §2/§4), offline:**
  - `run.py --oracle`: a fake agent emits the answer-key line → 100%
  - `--null`: empty text / constant `a3f9c21` → about 0% (except regression)
  - an injected API error lands in `errors.jsonl`, not as a 0
- **Accept:**
  - `uv run pytest -q` passes, all offline
  - `uv run python run.py --dry-run --flow hillclimb/ladder --variant baseline --model claude-opus-4-8` prints "21 cases × 2 reps × claude-opus-4-8 (default effort), budget $1.00/session"
  - oracle and null runs give 100% and about 0%
  - the first real run exits 2 until **you** run `--approve-harness`

### Phase 5: Gate 0 pilot (paid; needs your OK)
- Run `reg-verbatim` once on Opus 4.8 (the parity check against e2e) and one generated regression case once each on Opus 4.8 and Haiku 5.5.
- Read the rows by hand: every field is non-zero and plausible.
- Confirm whether `session.usage` arrived on `end_turn`.
- **Pilot cells:** also run one generated case on Sonnet 5.5 low, so the walk's entry and its Haiku step-down both have measured texture.
- **Stop rule:** if `reg-verbatim` fails on Opus 4.8, it's a harness bug. Stop and report.
- **Accept:**
  - the pilot prints $/session (list_cost), tokens and wall time per model, plus the cumulative spend against the $50 cap
  - it prints the projected costs of the baseline (21 × 2), the round-0 diagnostic (21 × 1) and Sonnet low (21 × 2)
  - budgets get reset to ≥3× the pilot p95
- **Tonight's end state:** after your OK on the printed projection, launch `ladder/baseline` (Opus 4.8 default, 2 reps) and `ladder/v1` (Sonnet 5.5 low, 2 reps) in the background, then stop.

### Phase 6: staircase walk (paid; every cell gated on its printed projection, the cumulative spend, and your OK)
- **Cells in visit order:**
  - `baseline` = Opus 4.8 default (2 reps)
  - `v1` = Sonnet 5.5 low (entry, 2 reps)
  - `v2` = Opus 4.8 low (round-0 diagnostic, 1 rep, off path)
  - then the walk per C0.4: Haiku 5.5 low on a pass if projected under c\*; on a fail, Sonnet 5.5 medium → high (at most 2 notches)
- Opus 5.5 is excluded (C0.2).
- Each `vN/change.md`: the first line is "model=…, effort=…", followed by why the walk went there (pass, fail or prune, and the projection versus c\*).
- `_state.json` records `walk: [{variant, model, effort, verdict, adopted}]` and the floor from C0.3.
- Runs go in the background (`run_in_background`, `timeout` ≤ 7,200,000 ms).
- On 429s, propose a lower `--concurrency`, not a tight retry loop.
- **Sanity check:**
  - the round-0 diagnostic shows whether the effort dial is alive on Opus 4.8
  - if every cell is below 50%, look for a grader or harness bug
  - if Haiku low clears the floor at about 100%, skip the hillclimb
- **Accept:**
  - each cell has cases × reps rows, and its `errors.jsonl` has been reviewed
  - `node <skill>/build-report-lite.mjs hillclimb/ladder/` exits 0
  - `uv run python plot_path.py` writes `results/path.svg` and `results/path.png`

### Phase 7: build-eval review and target choice
- Steps 1 and 2 sign-offs:
  - an inputs page (`evals/cases/INPUTS.md`, generated)
  - grading spot-check on the pilot, with you deciding
- Noise floor and headroom per eval-hillclimb Step 0.5.
- **Target:** the walk's incumbent, meaning the cheapest cell that clears the floor pre-registered in C0.3.
- **`evals/ledger.py` → `COST_LEDGER.md`:**
  - spend per cell, model and round, from `list_cost`, plus billed error rows
  - the accuracy × $/incident Markdown table
  - the cumulative total against the $50 cap
- **Accept:**
  - `report.html` builds, and `path.svg`/`path.png` are regenerated
  - the ledger total matches `spend.py` and the sum of `list_cost_usd` over every `results.jsonl` and `errors.jsonl`

### Phase 8: hillclimb (paid; 2–4 rounds, plan approved via `/claude-api hillclimb`)
- `hillclimb/climb/`: the baseline is the target cell. Copy its rows if the harness sha is unchanged, otherwise re-run.
- **Scope:** `evals/prompts/system.md` only.
- **Off limits:** runbook, tools, graders, generator, runner.
- **Analyzer:** a fresh subagent per round, given only train traces (shifted, rolled_back, innocent_message).
- **Revert rule:** patches naming shas, "checkout" or specific times are reverted.
- `vN/change.md`, `change.patch`, and a `system.md` snapshot per round.
- **Regression rule (C0.6):** a round's val score must not drop below the climb baseline's val score.
- Every round is gated on the $50 cap.
- **Accept:**
  - `narrative.md` has a test delta with a CI, or says "within noise, not merged"
  - kept rounds are added to the adopted path in `path.svg`

### Phase 9: teaching layer (no new spend)
- `evals/lab/` (stubs: `grade_root_cause`, `session_cost`, plus a one-line config swap) and `evals/lab_complete/`.
- `evals/results/`: a snapshot of the ladder and climb, without bulk traces unless you want them.
- `evals/README.md`: story, five checkpoints with expected-output blocks, a one-command demo that runs on recorded results with no key, and credit to Gagan Bhat's original (Apache-2.0).
- `FACILITATOR_GUIDE.md`, the final `SOURCES.md`, and a session log appended to `docs/plan.md`.
- D6 and D8 each include a **"What I found in the original lab"** section covering every item in **Findings to carry into the write-ups** (below).
- **Accept:** every Findings item, and the shortcut-agent lesson with both numbers (17/21 → 11/21), appears in both D6 and D8; on a fresh clone with no API key, `uv run pytest` passes; every checkpoint's expected output reproduces from `results/`; the original lab smoke test passes.

**Cut order if behind:**
1. walk cells beyond entry plus one step
2. reps beyond 2
3. hillclimb
4. Spanish segment

Never cut: the regression check, the tests, the ledger, **the path chart**, the reference solution, the rehearsal.

---

## Findings to carry into the write-ups (D6 facilitator guide, D8 one-pager)

Both D6 and D8 get a section titled **"What I found in the original lab."** Every item below goes in both, with the evidence named. Add to this list as findings come up. Phase 9 isn't done until every item appears in both documents.

1. **The log gives away the culprit's deploy.** `data/generate_log.py:143` writes `deploy_complete` only for `a3f9c21`, so one grep for deploy events finds the culprit without reading anything else. Fix in the eval: every deploy and rollback in the window is logged (`evals/generate.py`, `background()`).
2. **The log gives away the query change.** In the original log, the per-row `SELECT … WHERE order_id = ?` lines are the first database lines of any kind. The culprit stands out without reasoning about query shape (the Phase 1 smoke run's agent said it directly: "first-ever `SELECT * FROM order_items …` query appears"). It's the same kind of leak as item 1. Fix in the eval: healthy requests log a batched `IN (?)` query, so the agent has to notice batched turning into per-row (`evals/generate.py`, `request()`).
3. **The e2e grader is both too lenient and too strict.** It passes when "n+1" and `a3f9c21` appear anywhere in the agent's text, even in a recap of deploys, and it fails a correct "per-row query" answer (`e2e.py:104-105`). This is the lab's grader-validation moment (checkpoint 2, video segment 1).
4. **`get_diff` matches by substring.** `args["commit"][:7] in diff` returns the diff for any 7-character fragment of it, for example `order_i` (`agent_complete.py`, `e2e.py`). Fix in the eval: an exact sha match against the deploy list (`evals/tools.py`).
5. **e2e tested a different prompt from the one learners ship.** `e2e.py` kept its own shorter SYSTEM and TOOLS, so the Oct 13 smoke test didn't exercise the dashboard prompt. Fixed by Change 1 (`config.py`).
6. **The default effort isn't what the docs table says.** On Managed Agents, Opus 4.8 with no effort set reports `effort: xhigh`, not the skill table's `high` (sesn_01Vy3PfLW7MwY35zqBcV6Reg).
7. **Setup drift.** The SDK rename (`display_title` → `display_name`) broke the lab on 1.13.0. The README's license line says MIT, while the repo is Apache-2.0. Streamlit's `use_container_width`, used in `provided.py` and `pages/1_Metrics.py`, was scheduled for removal after 2025-12-31.

**Lesson from building the eval. This goes in both D6 and D8 with both numbers (17/21 → 11/21), framed as the eval-audit habit from the blog post: "I ran a shortcut agent against my own eval, it scored 17/21, so I hardened the cases until it dropped to 11/21." Cite `tests/test_shortcuts.py` as the evidence; it pins the shortcut scores, so the numbers can't drift from what is written:**
- **The first case set could be solved without reading anything.** A shortcut ("name the latest deploy to the paged service before the page") scored 17/21 on the first version: every deploy family was solvable from timestamps, and the commit-message and rolled-back traps never came into play. Fix: a same-minute guilty-sounding twin deploy for innocent_message, and a slow-burn culprit with a later rolled-back deploy for rolled_back. The shortcut now scores 11/21, and `tests/test_shortcuts.py` pins the per-family scores of four shortcut policies. The held-out decoy family is still solvable by timing plus service matching (4/4); only no_culprit defeats every shortcut, which is worth saying when reading test-split results.

---

## Session log

- 2026-10-13: plan approved with amendments; Phase 0 written (`docs/plan.md`, `ship-your-first-managed-agent/evals/SOURCES.md`). No code, no API spend.
- 2026-10-14: Phase 1 (Change 1) applied. New `config.py` (MODEL, EFFORT=None, `model_param()`, SYSTEM, TOOLS, RUNBOOK_DIR; no Streamlit); `provided.py` re-exports SYSTEM/TOOLS from it; `agent_complete.py` and `e2e.py` use `model_param()`; `e2e.py` now runs the canonical dashboard prompt and tools (its old shorter copies removed). Offline checks passed: SYSTEM/TOOLS byte-identical to HEAD `provided.py`; `model_param()` returns the bare string `claude-opus-4-8`; all 4 dashboard pages render via Streamlit AppTest with the agent offline; mocked `agent_complete.setup_agent` sends the same `agents.create` arguments as before. Noted, not fixed (original lab untouched): Streamlit warns that `use_container_width`, used in `provided.py` and `pages/1_Metrics.py`, was scheduled for removal after 2025-12-31; it still works on the installed version. Pending: gated e2e re-smoke (≈$0.22). Correction: the first run of these checks called `.venv/bin/python` directly, against the uv ground rule; they were rerun with `uv run --no-project` (same results), and the Phase 1 commands above now use it.
- 2026-10-14: Phase 1 e2e re-smoke (`uv run --no-project python e2e.py`, canonical dashboard prompt): **PASS**, 47 s wall, 40.9 s active, **$0.20 list cost** (7 model requests, 4 sandbox + 4 custom tool calls; tokens in 14 / out 2,741 / cache read 67,674 / cache write 15,288; matches $0.1989 from list prices). Recorded in `evals/pilot/manual.jsonl`; cumulative project spend $0.20 of $50. Findings: (1) Opus 4.8 with no effort set echoes `effort: xhigh` on Managed Agents, not the skill table's `high`; (2) `session.usage` events arrive during normal runs (5 here), resolving §B item 7; (3) the agent followed the runbook order and ended with a blockquoted root-cause line, as in the Oct 13 run. Side effect: e2e.py creates a new skill, agent and environment every run (as shipped).
- 2026-10-14: Phase 2 done (no API spend). New in `evals/`: `pyproject.toml` + `uv.lock` (anthropic==1.13.0, python-dotenv; pytest dev), `scenario.py`, `diffs.py`, `generate.py`, `specs.py`, `tools.py`, `cases.py`, `prompts/system.md` (byte-identical to `config.SYSTEM`), `tests/`. `uv run python generate.py` writes 21 cases (4 val / 9 train / 8 test); `cases/` is gitignored and regenerated deterministically. Generated logs are 4.7k–10.2k lines (`reg-verbatim` keeps the original 69,740). `uv run pytest -q`: 151 passed offline in about 5 s; negative checks confirmed the tests catch a leaking tool and metrics/log drift. Design choices made while building: (1) the page time comes from metrics (the last run of p99 > 500 ms that is still going at the end of the window, stamped at its second minute), which reproduces the original "~14:32" and keeps a recovered blip, such as `rb-early-n1`'s rolled-back deploy, from paging; (2) healthy DB requests log a batched `IN (?)` query, so the switch to per-row queries is a contrast rather than the first-ever query line; (3) traps: `nc-db-1` reuses the original culprit's commit message on a harmless deploy an hour before onset; `im-docs` has an innocent "fix: remove N+1" deploy; in `dc-after` the decoy is a real but minor inventory regression (`cache_removed`), not a harmless diff; (4) `get_diff` matches a sha exactly (7-char prefix) against the case's deploy list, so the old substring quirk (`order_i` returning the diff) is gone.
- 2026-10-14: `dc-after` fairness confirmed and pinned (`test_decoy_cannot_explain_the_page`, all 4 decoys): the decoy deploys after the paged service is already above 500 ms, its own service never reaches 500 ms, and the paged service's log never mentions it. Negative checks: a decoy moved inside the onset minute, and a decoy on the paged service, both fail the test. The "What I found in the original lab" findings list added above for D6 and D8.
- 2026-10-14: Phase 3 done (no API spend). `evals/graders.py`: `find_root_cause_line`, `grade_format` (one sentence = no `[.!?]` followed by whitespace and a capital, backtick or quote), `grade_root_cause` (the identifier before the mechanism; hex 7–40 matched on its 7-char prefix; on component cases any hex fails and the identifier must equal or start with an accepted component), `grade`, `grade_legacy_e2e`. 34 grader fixtures, including the verbatim Opus 4.8 line from the Phase 1 smoke run. Whole-set checks: the oracle scores 21/21, an empty answer 0/21, a constant `a3f9c21` 4/21. The shortcut audit found the first case set solvable by timing alone (17/21); the train families were hardened as above (new `Deploy.degrade_at` for slow burns; answers gain `degraded_at`). Shortcuts now: 7/21, 11/21, 14/21 (when the shortcut also reads deploy status) and 4/21, pinned. `uv run pytest -q`: 195 passed offline.
