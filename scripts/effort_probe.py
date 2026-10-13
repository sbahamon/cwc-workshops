# /// script
# requires-python = ">=3.10"
# dependencies = ["anthropic", "python-dotenv"]
# ///
"""
Effort probe for Claude Managed Agents.

Question 1: does `effort` set on the AGENT change behavior? (Both sources say yes.)
Question 2: does `effort` set inside a PER-SESSION model override get applied?
            (Public docs say no; the claude-api skill says yes.)

Method: same reasoning prompt, measure output tokens (thinking counts as output),
across four arms per model:

  agent_low      agent created with effort=low                      -> known low
  agent_high     agent created with effort=high                     -> known high
  override_low   agent_high + session override {id, effort: low}    -> ? 
  override_high  agent_low  + session override {id, effort: high}   -> ?

If override_low looks like agent_low and override_high looks like agent_high,
overrides apply effort. If both override arms look like the model's DEFAULT
effort instead, they don't (per the public docs).

Run:   uv run effort_probe.py   (needs PROBE_ANTHROPIC_API_KEY or ANTHROPIC_API_KEY, env or .env)
Output: probe_results.md (readable) and probe_results.json (raw), written even if a run fails.
Cost:  tiny. No tools, no files, short prompt; every session has a hard budget.
"""
import json
import os
import statistics
import sys
import time
import uuid

import anthropic
from dotenv import load_dotenv

load_dotenv()
# PROBE_ANTHROPIC_API_KEY lets you run this in a Claude Code cloud session without
# setting ANTHROPIC_API_KEY, which Claude Code itself might pick up.
# Keys not scoped to a workspace need the anthropic-workspace-id header for Managed Agents.
_ws = os.environ.get("ANTHROPIC_WORKSPACE_ID")
client = anthropic.Anthropic(
    api_key=os.environ.get("PROBE_ANTHROPIC_API_KEY") or None,
    default_headers={"anthropic-workspace-id": _ws} if _ws else None,
)

MODELS = ["claude-sonnet-5-5", "claude-haiku-5-5"]
REPS = int(os.environ.get("PROBE_REPS", "3"))
BUDGET_CENTS = "25"  # per session, hard cap: amount is an integer string in cents ("25" = $0.25)

PROMPT = (
    "A warehouse has three conveyor belts. Belt A moves 12 boxes/min, B moves 9, "
    "C moves 15. A runs 40 min, stops 10, runs 30. B runs continuously for 75 min "
    "but loses 1 box in every 18 it moves. C starts 20 min late and runs until all "
    "three belts together have moved exactly 2,000 boxes, if that ever happens within "
    "two hours. Does it? If so, at what minute (to one decimal)? Show brief working, "
    "then give the final answer on its own line."
)
SYSTEM = "You are a careful analyst. Be correct; keep the final answer short."
TAG = uuid.uuid4().hex[:6]


def model_obj(model_id: str, effort: str) -> dict:
    return {"id": model_id, "effort": {"type": effort}}


def make_agent(model_id: str, effort: str):
    return client.beta.agents.create(
        name=f"effort-probe-{model_id}-{effort}-{TAG}",
        model=model_obj(model_id, effort),
        system=SYSTEM,
        tools=[],
    )


def run_session(env_id: str, agent_ref) -> dict:
    session = client.beta.sessions.create(
        agent=agent_ref,
        environment_id=env_id,
        budget={"type": "limit", "max_list_cost": {"amount": BUDGET_CENTS, "currency": "USD"}},
        title=f"effort-probe-{TAG}",
    )
    out_tokens, calls, stop = 0, 0, None
    t0 = time.monotonic()
    with client.beta.sessions.events.stream(session.id) as stream:
        client.beta.sessions.events.send(
            session.id,
            events=[{"type": "user.message", "content": [{"type": "text", "text": PROMPT}]}],
        )
        for ev in stream:
            if ev.type == "span.model_request_end" and getattr(ev, "model_usage", None):
                out_tokens += ev.model_usage.output_tokens or 0
                calls += 1
            elif ev.type == "session.status_idle":
                stop = ev.stop_reason.type
                if stop != "requires_action":
                    break
            if time.monotonic() - t0 > 300:
                stop = "timeout"
                break
    # What does the server say this session is running with?
    echoed = None
    try:
        s = client.beta.sessions.retrieve(session.id)
        a = getattr(s, "agent", None)
        m = getattr(a, "model", None) if a is not None else None
        echoed = str(getattr(m, "effort", m)) if m is not None else None
    except Exception as e:  # informational only
        echoed = f"(retrieve failed: {e.__class__.__name__})"
    try:
        client.beta.sessions.delete(session.id)
    except Exception:
        pass
    return {"out": out_tokens, "calls": calls, "stop": stop, "echo": echoed}


ARMS = ["agent_low", "agent_high", "override_low", "override_high"]


def verdict_for(med: dict) -> str:
    lo, hi, olo, ohi = (med.get(k) for k in ARMS)
    if lo is None or hi is None:
        return "INCOMPLETE: agent-level arms failed (see errors)"
    if olo is None or ohi is None:
        return "OVERRIDE REJECTED: per-session effort overrides errored (see errors); use one agent version per effort"
    if hi < lo * 1.3:
        return "INCONCLUSIVE: agent-level low vs high barely differ on this prompt; rerun with a harder prompt or PROBE_REPS=5"
    near = lambda x: "low" if abs(x - lo) <= abs(x - hi) else "high"
    if near(olo) == "low" and near(ohi) == "high":
        return "APPLIED: per-session override effort works (skill docs correct); overrides are fine for sweeps"
    if near(olo) == near(ohi):
        return ("NOT APPLIED: both override arms behave alike (model default effort); public docs correct; "
                "use one agent version per effort")
    return "UNEXPECTED: override arms look reversed; rerun with PROBE_REPS=5"


def write_results(accepted: dict, results: dict, medians: dict, verdicts: dict) -> None:
    stamp = time.strftime("%Y-%m-%d %H:%M:%S %Z")
    data = {
        "run_at": stamp, "tag": TAG, "reps": REPS, "models": MODELS, "prompt": PROMPT,
        "models_accepted": accepted, "medians_output_tokens": medians, "verdicts": verdicts,
        "runs": [{"model": m, "arm": a, **r} for (m, a), rs in results.items() for r in rs],
    }
    with open("probe_results.json", "w") as f:
        json.dump(data, f, indent=2, default=str)

    lines = [f"# Effort probe results", "", f"Run at {stamp} (tag `{TAG}`, {REPS} reps per arm)", "",
             "## 1. Were the models accepted on Managed Agents?", "",
             "| Model | Agent create (effort low/high) |", "|---|---|"]
    for m in MODELS:
        lines.append(f"| `{m}` | {accepted.get(m, 'not attempted')} |")
    lines += ["", "## 2. Does effort in a per-session override get applied?", "",
              "| Model | agent_low | agent_high | override_low | override_high | Verdict |",
              "|---|---|---|---|---|---|"]
    for m in MODELS:
        med = medians.get(m, {})
        cells = " | ".join(str(med.get(a, "-")) for a in ARMS)
        lines.append(f"| `{m}` | {cells} | {verdicts.get(m, '-')} |")
    lines += ["", "Cells are median output tokens per session (thinking counts as output).", "",
              "## Raw runs", "", "| Model | Arm | Output tokens | Model calls | Stop | Effort echoed by session |",
              "|---|---|---|---|---|---|"]
    for (m, a), rs in results.items():
        for r in rs:
            stop = str(r["stop"]).replace("|", "/")[:120]
            lines.append(f"| `{m}` | {a} | {r['out']} | {r['calls']} | {stop} | {r['echo']} |")
    with open("probe_results.md", "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\nwrote probe_results.md and probe_results.json")


def main() -> int:
    env = client.beta.environments.create(
        name=f"effort-probe-{TAG}", config={"type": "cloud", "networking": {"type": "unrestricted"}}
    )
    agents = []
    accepted: dict[str, str] = {}
    results: dict[tuple[str, str], list[dict]] = {}
    try:
        for model_id in MODELS:
            try:
                a_low, a_high = make_agent(model_id, "low"), make_agent(model_id, "high")
                accepted[model_id] = "accepted"
            except anthropic.APIStatusError as e:
                accepted[model_id] = f"REJECTED ({e.status_code}): {str(e)[:200]}"
                print(f"!! {model_id}: agent create rejected -> {e}")
                continue
            agents += [a_low, a_high]
            arms = {
                "agent_low": a_low.id,
                "agent_high": a_high.id,
                "override_low": {"type": "agent_with_overrides", "id": a_high.id,
                                 "model": model_obj(model_id, "low")},
                "override_high": {"type": "agent_with_overrides", "id": a_low.id,
                                  "model": model_obj(model_id, "high")},
            }
            for arm, ref in arms.items():
                for r in range(REPS):
                    try:
                        res = run_session(env.id, ref)
                    except anthropic.APIStatusError as e:
                        res = {"out": None, "calls": 0, "stop": f"{e.status_code}: {str(e)[:200]}", "echo": None}
                    results.setdefault((model_id, arm), []).append(res)
                    print(f"{model_id:20} {arm:14} rep{r}  out_tokens={res['out']}  "
                          f"calls={res['calls']}  stop={res['stop']}  echo={res['echo']}")
    finally:
        for a in agents:
            try:
                client.beta.agents.archive(a.id)
            except Exception:
                pass
        try:
            client.beta.environments.delete(env.id)
        except Exception:
            pass

        medians, verdicts = {}, {}
        print("\n=== verdict (median output tokens) ===")
        for model_id in MODELS:
            if accepted.get(model_id) != "accepted":
                verdicts[model_id] = "model not accepted"
                continue
            med = {}
            for arm in ARMS:
                vals = [x["out"] for x in results.get((model_id, arm), []) if x["out"]]
                med[arm] = statistics.median(vals) if vals else None
            medians[model_id] = med
            verdicts[model_id] = verdict_for(med)
            print(model_id, med, "\n  ->", verdicts[model_id])
        write_results(accepted, results, medians, verdicts)
    return 0


if __name__ == "__main__":
    sys.exit(main())