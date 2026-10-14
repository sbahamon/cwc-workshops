model=claude-sonnet-5-5, effort=high (walk: second and last notch right of v1)

Why the walk went here: v1 (low) and v3 (medium) both failed the floor on format only.
cost-hillclimb.md caps the rightward walk at two notches; this is the second. Projected
under the incumbent's cost (canary $0.06/session vs baseline $0.2407/incident).
Canary: pilot/sonnet-5-5-high (reg-500s, root_cause 1, format 1, $0.06 list, effort echoed high).

Verdict (2026-10-14): **FAIL**, official and shadow grades agree. root_cause (train+test) 100.0%,
reg-verbatim [1, 1], format 52.4% ± 15.1% vs >= 95%. $0.0655 list / $0.0652 rate card per incident.
More effort made format worse, not better (low 61.9%, medium 69.0%, high 52.4%; output tokens
1,244 -> 1,403 -> 2,356); every miss is a second sentence on the root-cause line.
Walk: the Sonnet row is exhausted (two notches right). **The walk stops**: no cell cleared the floor,
the incumbent stays the baseline, and the $20 overnight stop is also reached ($19.96).
