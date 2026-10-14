# SOURCES

Every API field, model ID, docs page and claim this lab relies on, with where it came from and how it was checked. When a model or beta field changes, this table is the update checklist.

Status key: **verified** = checked against the installed SDK (`anthropic==1.13.0`), a live run, or the claude-api skill docs (named in the Source column); **to confirm** = checked in a later phase (noted); **unverified** = carried from earlier notes and not re-checked; **decision** = a deliberate project choice.

Skill docs refer to the `claude-api` skill bundled with Claude Code 2.1.299 (`shared/…` paths; model table cached 2026-10-06).

| Item | Value used | Source | Status |
|---|---|---|---|
| SDK | `anthropic==1.13.0` | `requirements.txt`; installed `.venv` | verified |
| Skills create | `client.beta.skills.create(display_name=, files=files_from_dir())`; stable `client.skills.create` also exists | SDK `resources/beta/skills/skills.py:73`, `resources/skills/skills.py:72`; skill SKILL.md "API Drift" | verified |
| Files upload | `client.beta.files.upload(file=)` (stable `client.files` exists) | SDK `resources/beta/files.py:265` | verified |
| Agent create | `name, model, system, tools, skills=[{type:"custom", skill_id, version}]` | `managed-agents-core.md` §Agent configuration fields | verified (skill) |
| Agent model/effort | `model: "<id>"` or `{"id", "effort": low\|medium\|high\|xhigh\|max}` | core §Effort on the agent model; probe_results.md | verified (live probe) |
| Override effort | applied (skill + probe); "public docs say not applied" | core §Override; `scripts/probe_results.md` | public-docs line **unverified this session** |
| Agent versioning | update → new integer version; pin `{type:"agent", id, version}` | core §Versioning | verified (skill) |
| Environment | `environments.create(name, config={"type":"cloud","networking":{"type":"limited"}})`; limited without `allowed_hosts` blocks web tools | core; SKILL.md pitfalls (limited networking) | to confirm in Phase 4 |
| Session create | `agent, environment_id, resources=[{type:"file", file_id, mount_path:"app.log"}], budget, metadata, title` | SDK `sessions.create`; `agent_complete.py` | verified |
| Session budget | `{"type":"limit","max_list_cost":{"amount":"<int cents>","currency":"USD"}}`; pauses with `stop_reason: budget_reached` | core §Session budgets; live 400 on `"0.25"` (Oct 13) | verified |
| list_cost basis | list token prices + web search $10/1k + runtime $0.08/hr; rounded to the cent | core §Session budgets | verified (skill) |
| Session usage | `sessions.retrieve(id).usage.{list_cost, active_seconds, tokens}` | core §Session Object | verified (skill) |
| `session.usage` event | `BetaManagedAgentsSessionUsageEvent` ("periodic snapshot"); emitted during normal runs too (5 events in a 7-request `end_turn` session), not only before `budget_reached`. Runner still treats `sessions.retrieve().usage` as authoritative | events §Reaching a session budget; SDK type; live, sesn_01Vy3PfLW7MwY35zqBcV6Reg (2026-10-14) | verified (live) |
| `span.model_request_end` | `model_usage{input, output, cache_read, cache_creation tokens}`; no model id | events §Event payloads; SDK type | verified |
| Served model | none per event; `session.agent.model` snapshot only | SDK `BetaManagedAgentsSession.agent` | gap, documented |
| Stream / tools | open stream before send; `agent.custom_tool_use` → `user.custom_tool_result{custom_tool_use_id}`; `user.interrupt` | events §Stream-first ordering, §Interrupt; `agent_complete.py` | verified |
| Toolset | `agent_toolset_20260401` | `provided.py`; core | verified |
| Workspace-scoped key | unscoped key → 400 asking for `anthropic-workspace-id` | live (Oct 13) | verified |
| Models | `claude-opus-4-8` $5/$25 (skill table: default high; **on Managed Agents a bare model string echoes `effort: xhigh`**, see next row); `claude-opus-5-5` $4/$20 (default **medium**); `claude-sonnet-5-5` $2/$10 (default high); `claude-haiku-5-5` $0.10/$0.50 ≤100K-token prompts, $0.50/$2.50 beyond (default medium) | claude-api SKILL.md Current Models (cached 2026-10-06), Thinking & Effort table | verified (skill) |
| Managed Agents default effort, Opus 4.8 | agent created with `model="claude-opus-4-8"` (no effort) → `sessions.retrieve().agent.model` = `{id: claude-opus-4-8, effort: xhigh, speed: standard}`. Conflicts with the skill's "default high". The ladder baseline is therefore Opus 4.8 at **xhigh**; other models' defaults must be read from the echo, not assumed | live, sesn_01Vy3PfLW7MwY35zqBcV6Reg (2026-10-14) | verified (live) |
| list_cost cross-check | 20¢ reported = $0.1989 from tokens at list (in $5, out $25, cache read 0.1×, 5m write 1.25×) + 40.9 s × $0.08/h | live, same session | verified (live) |
| Eval contract | `results.jsonl` / `traces` / `errors.jsonl` / `_state.json` / `baseline` + `vN` / harness gate | `shared/evals/build-eval.md` Step 3; `eval-hillclimb.md` Step 3; `report/SCHEMA.md` | verified |
| Report builder | only `build-report-lite.mjs` installed (no cost, no CI) | skill dir listing | verified |
| Cost search order | caching → audit → model×effort staircase → prompt climb → down-left re-probe → joint confirm | `shared/evals/cost-hillclimb.md` | verified |
| Docs pages | platform.claude.com/docs/en/managed-agents/overview, …/quickstart | workshop README | links to re-check in Phase 9 |
| Opus 4.8 at `low` (round-0 diagnostic) | `{"id":"claude-opus-4-8","effort":"low"}` | SKILL.md effort table (Opus 4.8: low–max) | **to confirm in pilot** (agent create) |
| Grid exclusion | Opus 5.5 excluded from the walk (cost; Opus 4.8 → Sonnet → Haiku story) | Steffany, Oct 13 amendment | decision |
| Path chart style | Fig. 8, cost-reduction path | claude.dev blog, *Automating eval design and hillclimbing with Claude* (#hillclimbing-for-cost-reduction) | not fetched this session; layout per the amendment spec |
