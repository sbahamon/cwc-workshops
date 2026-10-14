model=claude-sonnet-5-5, effort=medium (walk: one notch right of v1)

Why the walk went here: v1 (Sonnet 5.5 low) failed the floor on format only (61.9% < 95%),
outside noise. cost-hillclimb.md Step 2: on a fail, step right (at most two notches). Its
projected cost ($0.04/session canary) is far under the incumbent's (baseline $0.2407/incident).
Canary: pilot/sonnet-5-5-medium (reg-500s, root_cause 1, format 1, $0.04 list).

Verdict (2026-10-14): **FAIL**, official and shadow grades agree. root_cause (train+test) 100.0%,
reg-verbatim [1, 1], format 69.0% ± 14.0% vs >= 95% (outside noise). $0.0381 list / $0.0389 rate card per
incident. Effort dial low -> medium: output tokens +13% (1,244 -> 1,403 mean), format +7 points (within noise).
Walk: fail -> second and last notch right, claude-sonnet-5-5 at high (canary first).
