# Facilitator notes (working draft)

Running notes for the facilitator guide (D6). Phase 9 folds them into `FACILITATOR_GUIDE.md`.
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
