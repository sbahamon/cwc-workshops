# Effort probe results

Run at 2026-10-13 18:03:31 EDT (tag `a492b6`, 3 reps per arm)

## 1. Were the models accepted on Managed Agents?

| Model | Agent create (effort low/high) |
|---|---|
| `claude-sonnet-5-5` | accepted |
| `claude-haiku-5-5` | accepted |

## 2. Does effort in a per-session override get applied?

| Model | agent_low | agent_high | override_low | override_high | Verdict |
|---|---|---|---|---|---|
| `claude-sonnet-5-5` | 727 | 1106 | 852 | 1151 | APPLIED: per-session override effort works (skill docs correct); overrides are fine for sweeps |
| `claude-haiku-5-5` | 1507 | 1947 | 1619 | 2038 | INCONCLUSIVE: agent-level low vs high barely differ on this prompt; rerun with a harder prompt or PROBE_REPS=5 |

Cells are median output tokens per session (thinking counts as output).

## Raw runs

| Model | Arm | Output tokens | Model calls | Stop | Effort echoed by session |
|---|---|---|---|---|---|
| `claude-sonnet-5-5` | agent_low | 808 | 1 | end_turn | BetaManagedAgentsEffortLow(type='low') |
| `claude-sonnet-5-5` | agent_low | 716 | 1 | end_turn | BetaManagedAgentsEffortLow(type='low') |
| `claude-sonnet-5-5` | agent_low | 727 | 1 | end_turn | BetaManagedAgentsEffortLow(type='low') |
| `claude-sonnet-5-5` | agent_high | 1222 | 1 | end_turn | BetaManagedAgentsEffortHigh(type='high') |
| `claude-sonnet-5-5` | agent_high | 1077 | 1 | end_turn | BetaManagedAgentsEffortHigh(type='high') |
| `claude-sonnet-5-5` | agent_high | 1106 | 1 | end_turn | BetaManagedAgentsEffortHigh(type='high') |
| `claude-sonnet-5-5` | override_low | 921 | 1 | end_turn | BetaManagedAgentsEffortLow(type='low') |
| `claude-sonnet-5-5` | override_low | 600 | 1 | end_turn | BetaManagedAgentsEffortLow(type='low') |
| `claude-sonnet-5-5` | override_low | 852 | 1 | end_turn | BetaManagedAgentsEffortLow(type='low') |
| `claude-sonnet-5-5` | override_high | 1225 | 1 | end_turn | BetaManagedAgentsEffortHigh(type='high') |
| `claude-sonnet-5-5` | override_high | 1072 | 1 | end_turn | BetaManagedAgentsEffortHigh(type='high') |
| `claude-sonnet-5-5` | override_high | 1151 | 1 | end_turn | BetaManagedAgentsEffortHigh(type='high') |
| `claude-haiku-5-5` | agent_low | 1894 | 1 | end_turn | BetaManagedAgentsEffortLow(type='low') |
| `claude-haiku-5-5` | agent_low | 1374 | 1 | end_turn | BetaManagedAgentsEffortLow(type='low') |
| `claude-haiku-5-5` | agent_low | 1507 | 1 | end_turn | BetaManagedAgentsEffortLow(type='low') |
| `claude-haiku-5-5` | agent_high | 1947 | 1 | end_turn | BetaManagedAgentsEffortHigh(type='high') |
| `claude-haiku-5-5` | agent_high | 1789 | 1 | end_turn | BetaManagedAgentsEffortHigh(type='high') |
| `claude-haiku-5-5` | agent_high | 1986 | 1 | end_turn | BetaManagedAgentsEffortHigh(type='high') |
| `claude-haiku-5-5` | override_low | 1471 | 1 | end_turn | BetaManagedAgentsEffortLow(type='low') |
| `claude-haiku-5-5` | override_low | 1619 | 1 | end_turn | BetaManagedAgentsEffortLow(type='low') |
| `claude-haiku-5-5` | override_low | 1778 | 1 | end_turn | BetaManagedAgentsEffortLow(type='low') |
| `claude-haiku-5-5` | override_high | 2038 | 1 | end_turn | BetaManagedAgentsEffortHigh(type='high') |
| `claude-haiku-5-5` | override_high | 1788 | 1 | end_turn | BetaManagedAgentsEffortHigh(type='high') |
| `claude-haiku-5-5` | override_high | 2110 | 1 | end_turn | BetaManagedAgentsEffortHigh(type='high') |
