model=claude-opus-4-8, effort=low (round-0 diagnostic, 1 rep, off the walk path)

Why: cost-hillclimb.md Step 2's round-0 diagnostic. One cheap cell on the old model at a
different effort measures whether effort moves cost and quality on this workload. It's
not a candidate: it informs where repeats get spent, never where the walk goes, and it's
drawn grey on the path chart. Canary: pilot/opus-4-8-low (reg-500s, 1/1, $0.15 list).

Result: root_cause (train+test) 100.0%, format 100.0%, reg-verbatim [1]; $0.1371 list / $0.1365 rate card
per incident (baseline $0.2407). The effort dial is alive on Opus 4.8: mean output tokens 4,371 -> 1,735
per session, tool calls 9.2 -> 7.8, latency 68 s -> 32 s. Off the path as pre-registered: not a candidate.
Official and shadow grades agree.
