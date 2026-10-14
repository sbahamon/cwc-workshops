# Facilitator notes (working draft)

Running notes for the facilitator guide (D6). Folded into [`FACILITATOR_GUIDE.md`](FACILITATOR_GUIDE.md) in Phase 9; the guide is the version to teach from.
Built on Gagan Bhat's original workshop, *Ship your first managed agent* (Apache-2.0).

## Running the eval

- **Run one `run.py` process at a time.** Run cells one after another, never two `run.py`
  commands in parallel. Two processes race on the shared registry temp file
  (`.registry.tmp` → `.registry.json`) and the second one crashes in setup. This happened once,
  with no sessions started and nothing billed. Within one cell, `--concurrency N` is safe:
  those are threads in one process, and the in-process lock covers them. The race is known and
  deliberately left unfixed (docs/plan.md, Post-results changes).
- **Probe each error path live once before a grid.** The watchdog's first live timeout hung.
  The offline fake couldn't show that; a 1¢ live probe did.
- **Audit the grader before trusting a failure.** Read only the grader's input on the failing
  rows. That's how the trailing-punctuation bug (`a3f9c21`. The…) was found.

## Terminology: two meanings of "harness"

Goes near the top of `evals/README.md` (docs/plan.md, Phase 9):

> **Two meanings of "harness."** The *agent harness* is the loop around the model
> (prompting, tool calls, feeding results back). On Managed Agents, Anthropic runs it, and
> you only configure the agent. The *eval harness* is the measuring setup: cases, tools,
> graders, runner and cost calculation. This lab fingerprints the eval harness and requires
> a human approval whenever it changes, so every result is measured with the same ruler and
> a hillclimb can't raise its score by editing the grader. That's a method from the
> claude-api skill's hillclimb process, not something the API requires.

**Talk-track.** Name the two meanings as soon as learners first see `--approve-harness`.
Then use `docs/plan.md` → "Post-results changes" as the worked example:
- The eval harness was approved at three fingerprints:
  - `9f02ee7a8a03` before the pilot
  - `64ecf9d86b32` after the watchdog fix and `pricing.py`
  - `c808e86bdb6d` after the grader fix
- Only the last change came after results existed.
- That grader fix was safe, because grades are recomputed from saved transcripts: the agent
  saw exactly the same thing, and only the ruler's reading changed (two rows, no verdict).
- The case hardening we declined (the diffs-only shortcut finding) would not have been safe,
  because it changes what the agent sees. Every existing result would have measured a
  different test, so the ladder would have to be re-run.
