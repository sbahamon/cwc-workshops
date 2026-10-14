model=claude-sonnet-5-5, effort=low (walk entry cell)

Why the walk went here: cost-hillclimb.md Step 2 enters at the highest cost-plausible
tier at low effort. With Opus 5.5 excluded from the grid (docs/plan.md C0.2), that tier is
Sonnet 5.5. Canary: pilot/sonnet-5-5-low (reg-500s, root_cause 1, format 1, $0.06 list).
Verdict against the C0.3 floor: written after the run, below.

Verdict (walk.py + shadow_regrade.py, 2026-10-14): **FAIL**, official and shadow grades agree.
- root_cause (train+test): official 97.1% ± 5.7%; shadow 100.0%. Floor needs >= 90.0% (baseline 100.0%): pass.
- reg-verbatim: official [1, 0], shadow [1, 1]. The official 0 is a grader bug (the sha followed by a
  period, "`a3f9c21`. The ...", reads as "a3f9c21."); the fix is proposed, not applied.
- format: 61.9% ± 14.7% vs >= 95%: fail, and clearly outside noise. Sonnet low names the culprit but
  keeps adding a second sentence ("Reverting it should ...").
- Cost: $0.0374 list / $0.0375 rate card per incident (baseline $0.2407 / $0.2402): 6.4x cheaper.
Walk: fail -> step right to claude-sonnet-5-5 at medium (canary first), after the round-0 diagnostic.

Regrade (2026-10-14 morning, after the grader trailing-punctuation fix; docs/plan.md, Post-results
changes): dc-after rep 1 and reg-verbatim rep 1 root_cause 0 -> 1. Now root_cause (train+test)
100.0%, reg-verbatim [1, 1], format 61.9% unchanged. Verdict unchanged: **FAIL**, on format alone.
