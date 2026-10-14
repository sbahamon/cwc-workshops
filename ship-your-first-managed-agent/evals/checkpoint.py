# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0
"""
The lab's five checkpoints. Each one runs your code (lab/) against fixtures or the
recorded runs in results/, so none of them needs an API key.

    uv run python checkpoint.py 1                 # check your lab/grading.py
    uv run python checkpoint.py 3 --solution      # run the reference in lab_complete/ instead
    uv run python checkpoint.py all --solution    # the whole lab on recorded results, about 5 s
    uv run python checkpoint.py 4 --live          # one real session on your lab/cell.py (needs a key)

  1  grade_root_cause      lab/grading.py   fixtures from the grader-validation step
  2  the e2e.py grader     (uses 1)         the old check next to yours, on recorded replies, then fixtures
  3  session_cost          lab/cost.py      price recorded sessions from their tokens
  4  the model swap        lab/cell.py      the recorded run of your cell; --live runs it (about 2¢)
  5  the path              (uses 1, 3)      every ladder cell and climb round, graded and priced by your code

The expected output of each checkpoint is in README.md; tests/test_lab.py checks that
the reference solution prints exactly that.
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

EVALS = Path(__file__).resolve().parent
RESULTS = EVALS / "results"
sys.path.insert(0, str(EVALS.parent))  # the workshop's config.py

import config  # noqa: E402
from cases import CASES_DIR, load_answer, load_cases  # noqa: E402
from graders import find_root_cause_line, grade_format, grade_legacy_e2e  # noqa: E402

NAMES = {"claude-opus-4-8": "Opus 4.8", "claude-sonnet-5-5": "Sonnet 5.5", "claude-haiku-5-5": "Haiku 5.5"}
SHIPPED_SHA = __import__("hashlib").sha256(config.SYSTEM.encode()).hexdigest()[:16]

DEPLOY = {"kind": "deploy", "culprit_short": "a3f9c21", "components": []}
DB = {"kind": "component", "culprit_short": None,
      "components": ["db-primary", "db primary", "primary db", "primary database"]}
STRIPE = {"kind": "component", "culprit_short": None, "components": ["stripe-api", "stripe api", "stripe"]}
FULL_SHA = "a3f9c21e8b4d2f1a9c0e7d3b5f8a2c4e6d9b1f0a"

# The real Opus 4.8 line from the Phase 1 smoke run (pilot/phase1-e2e-smoke.log).
REAL_OPUS = ("> **Root cause:** `a3f9c21` — refactor swapped a single batched `order_id__in` query "
             "for a per-order query inside a loop (N+1), multiplying DB round-trips per checkout "
             "request and driving p99 from ~60 ms to multiple seconds.")
# Names N+1 and the right sha, but concludes a different commit.
RECAP_WRONG = ("Recent deploys: e21b6c9 (cart), 9f1e2d4 (auth), a3f9c21 (checkout), 7b3e8f0 (inventory).\n"
               "The a3f9c21 diff could be an N+1, but the timing fits auth's rate limiter better.\n\n"
               "**Root cause:** `9f1e2d4` — the new /refresh rate limiter throttles checkout's token refresh.")
# Right, but never says "N+1".
PER_ROW_RIGHT = ("Deploy a3f9c21 lines up with the p99 jump; the diff swaps a batched lookup for a loop.\n\n"
                 "**Root cause:** `a3f9c21` — the summary builder now issues a per-row query for every open order.")

FIXTURES = [  # (what it checks, reply, answer key, expected grade)
    ("the real Opus 4.8 line: blockquote, backticks, em dash", REAL_OPUS, DEPLOY, 1),
    ("a full 40-character sha in bold", f"**Root cause:** **{FULL_SHA}** — per-row query loop.", DEPLOY, 1),
    ("a sha followed by a period", "**Root cause:** `a3f9c21`. Per-row queries replaced the batch.", DEPLOY, 1),
    ("'commit' before the sha", "**Root cause:** commit `a3f9c21` — N+1 query.", DEPLOY, 1),
    ("says 'per-row query', never 'N+1'", PER_ROW_RIGHT, DEPLOY, 1),
    ("two sentences: format fails, root cause still counts",
     "**Root cause:** `a3f9c21` — per-row queries replaced a batch. Revert it.", DEPLOY, 1),
    ("mentions the right sha, concludes another", RECAP_WRONG, DEPLOY, 0),
    ("a sha one character off", "**Root cause:** `a3f9c22` — N+1 query.", DEPLOY, 0),
    ("no root-cause line at all", "Probably a3f9c21, the N+1 in checkout. Revert it.", DEPLOY, 0),
    ("two root-cause lines: the last one counts",
     "**Root cause:** `9f1e2d4` — first guess.\n\n**Root cause:** `a3f9c21` — per-row query loop.", DEPLOY, 1),
    ("no culprit: names the component", "**Root cause:** `db-primary` — lock waits exhausted every pool.", DB, 1),
    ("no culprit: component in plain words", "**Root cause:** primary DB lock contention — not a deploy.", DB, 1),
    ("no culprit: blames a deploy", "**Root cause:** `a3f9c21` — db-primary lock waits began after it.", DB, 0),
    ("no culprit: names the symptom, not the cause", "**Root cause:** checkout — the service is slow.", STRIPE, 0),
    ("no culprit: the wrong component", "**Root cause:** `stripe-api` — upstream timeouts.", DB, 0),
    ("no culprit: upstream named casually", "**Root cause:** Stripe — the payments upstream is timing out.", STRIPE, 1),
]


class NotDone(Exception):
    pass


def lab(module: str, solution: bool):
    pkg = "lab_complete" if solution else "lab"
    return importlib.import_module(f"{pkg}.{module}"), f"{pkg}/{module}.py"


def call(fn, *args):
    try:
        return fn(*args)
    except NotImplementedError as e:
        raise NotDone(str(e) or fn.__name__) from None


# ── recorded data ───────────────────────────────────────────────────────
def answers() -> dict[str, dict]:
    """Answer keys, from the generated cases (generated once if missing; deterministic)."""
    if not CASES_DIR.exists():
        from generate import write
        from specs import SPECS, split_of
        print("(generating cases/ once, a few seconds)", file=sys.stderr)
        for sc in SPECS:
            write(sc, split_of(sc))
    return {c.id: load_answer(c) for c in load_cases()}


def recorded(cell: str) -> list[tuple[dict, dict]]:
    """[(row, session)] for results/<cell>/: the recorded row and its reply and per-request usage."""
    d = RESULTS / cell
    rows = [json.loads(l) for l in (d / "rows.jsonl").read_text().splitlines() if l.strip()]
    sessions = [json.loads(l) for l in (d / "sessions.jsonl").read_text().splitlines() if l.strip()]
    assert [(r["prompt_id"], r["rep"]) for r in rows] == [(s["prompt_id"], s["rep"]) for s in sessions], cell
    return list(zip(rows, sessions))


def state(flow: str) -> dict:
    return json.loads((RESULTS / flow / "state.json").read_text())


def path_cells() -> list[dict]:
    """Every ladder cell and climb round, in the order the walk and the climb visited them."""
    walk, climb = state("ladder")["walk"], state("climb")
    plain = [dict(e, cell=f"ladder/{e['variant']}") for e in walk if not e.get("prompt")]
    rounds = [{"cell": f"climb/{r['variant']}", "model": climb["target"]["model"], "effort": climb["target"]["effort"],
               "role": "climb", "adopted": str(r.get("kept", "")).startswith("kept")} for r in climb["rounds"]]
    later = [dict(e, cell=f"ladder/{e['variant']}") for e in walk if e.get("prompt")]
    return plain + rounds + later


# ── checkpoint 1 ────────────────────────────────────────────────────────
def checkpoint_1(solution: bool) -> int:
    grading, where = lab("grading", solution)
    print(f"Checkpoint 1: grade_root_cause ({where})")
    failed = 0
    for what, text, answer, want in FIXTURES:
        got = call(grading.grade_root_cause, text, answer)
        ok = got == want
        failed += not ok
        print(f"  {'ok  ' if ok else 'FAIL'}  {what}" + ("" if ok else f": expected {want}, got {got}"))
    print(f"{len(FIXTURES) - failed}/{len(FIXTURES)} fixtures pass." + (" Next: checkpoint 2." if not failed else ""))
    return int(bool(failed))


# ── checkpoint 2 ────────────────────────────────────────────────────────
def checkpoint_2(solution: bool) -> int:
    grading, where = lab("grading", solution)
    print("Checkpoint 2: the e2e.py grader, next to yours")
    print('e2e.py passes a reply when "n+1" and the sha appear anywhere in it (e2e.py:104-105).')
    keys = answers()
    counts = {(1, 1): 0, (0, 1): 0, (1, 0): 0, (0, 0): 0}
    example = None
    cells = [c["cell"] for c in path_cells()]
    for cell in cells:
        for row, s in recorded(cell):
            a = keys[row["prompt_id"]]
            if a["kind"] != "deploy":
                continue
            old = grade_legacy_e2e(s["reply"], a["culprit_short"])
            new = call(grading.grade_root_cause, s["reply"], a)
            counts[(old, new)] += 1
            if (old, new) == (0, 1) and example is None:
                example = (cell, row, find_root_cause_line(s["reply"]))
    n = sum(counts.values())
    print()
    print(f"Both checks on all {n} recorded replies to deploy cases ({len(cells)} cells in results/;")
    print("e2e.py's check is applied with each case's own sha):")
    print(f"  e2e.py fails a correct answer   {counts[(0, 1)]:4d}")
    print(f"  e2e.py passes a wrong answer    {counts[(1, 0)]:4d}")
    print(f"  both pass                       {counts[(1, 1)]:4d}")
    print(f"  both fail                       {counts[(0, 0)]:4d}")
    if example:
        cell, row, line = example
        print(f"For example {cell}, {row['prompt_id']} rep {row['rep']}, right but no \"N+1\":")
        print(f"  **Root cause:** {line}")
    print()
    print("In theory it can also pass a wrong answer. No recorded agent did; these are written fixtures:")
    print(f"  {'reply':44s} {'e2e.py':7s} {'yours':6s} right?")
    for what, text, right in (('correct, says "per-row query", not "N+1"', PER_ROW_RIGHT, "yes"),
                              ("recaps every deploy, concludes 9f1e2d4", RECAP_WRONG, "no")):
        old, new = grade_legacy_e2e(text), call(grading.grade_root_cause, text, DEPLOY)
        print(f"  {what:44s} {'PASS' if old else 'fail':7s} {'PASS' if new else 'fail':6s} {right}")
    return 0


# ── checkpoint 3 ────────────────────────────────────────────────────────
def checkpoint_3(solution: bool) -> int:
    from pricing import session_usd
    cost, where = lab("cost", solution)
    print(f"Checkpoint 3: session_cost ({where})")
    print("Two recorded canary sessions on case reg-500s (results/pilot/):")
    print()
    print(f"  {'session':18s} {'requests':>8s} {'input':>6s} {'output':>7s} {'cache read':>11s} {'cache write':>12s}"
          f" {'your cost':>10s} {'list_cost':>10s}")
    shown = {}
    for cell in ("pilot/opus-4-8-default", "pilot/haiku-5-5-low"):
        row, s = next((r, s) for r, s in recorded(cell) if r["prompt_id"] == "reg-500s")
        usd = call(cost.session_cost, row["model"], s["requests"], row["meta"]["active_seconds"])
        tot = lambda k: sum(u[k] for u in s["requests"])
        name = f"{NAMES[row['model']]}, {row['meta']['effort_echoed']}"
        print(f"  {name:18s} {len(s['requests']):8d} {tot('input_tokens'):6,d} {tot('output_tokens'):7,d}"
              f" {tot('cache_read_input_tokens'):11,d} {tot('cache_creation_input_tokens'):12,d}"
              f" {'$%.4f' % usd:>10s} {'$%.2f' % row['list_cost_usd']:>10s}")
        shown[row["model"]] = (usd, row["list_cost_usd"])
    total = agree = 0
    for d in sorted(RESULTS.rglob("sessions.jsonl")):
        for row, s in recorded(d.parent.relative_to(RESULTS).as_posix()):
            want = session_usd(row["model"], s["requests"], row["meta"]["active_seconds"])
            got = call(cost.session_cost, row["model"], s["requests"], row["meta"]["active_seconds"])
            total += 1
            agree += abs(got - want) < 5e-6
    usd, lst = shown["claude-haiku-5-5"]
    print()
    print(f"Your session_cost matches pricing.py on {agree}/{total} recorded sessions.")
    print(f"Haiku's list_cost reads {lst / usd:.1f}× its rate card. The Console bill followed the rate card")
    print("(SOURCES.md, Haiku 5.5 billing check), so the path chart's x axis is the rate card.")
    return int(agree != total)


# ── checkpoint 4 ────────────────────────────────────────────────────────
def cell_tag(model: str, effort: str | None) -> str:
    return f"{model.removeprefix('claude-')}-{effort or 'default'}"


def checkpoint_4(solution: bool, live: bool = False, dry_run: bool = False) -> int:
    cell, where = lab("cell", solution)
    grading, _ = lab("grading", solution)
    cost, _ = lab("cost", solution)
    model, effort = cell.MODEL, cell.EFFORT
    print(f"Checkpoint 4: the model swap ({where})")
    print(f"  cell: {model}, effort {effort or 'default'}")
    if (model, effort) == ("claude-opus-4-8", None):
        print("  That's still the workshop's Opus 4.8 at default effort. Swap the line to Haiku 5.5 at low effort.")
        return 1
    if live or dry_run:
        return run_live(model, effort, grading, cost, dry_run)
    pilot = RESULTS / "pilot" / cell_tag(model, effort)
    if not (pilot / "rows.jsonl").exists():
        print(f"  No recorded run for this cell in results/pilot/. Run one: uv run python checkpoint.py 4 --live")
        return 1
    row, s = recorded(f"pilot/{pilot.name}")[0]
    report_session(row, s, grading, cost, f"results/pilot/{pilot.name}/")
    print("Run it yourself (one session, about 2¢; needs ANTHROPIC_API_KEY in ../.env):")
    print("  uv run python checkpoint.py 4 --live")
    return 0


def report_session(row: dict, s: dict, grading, cost, where: str) -> None:
    rc = call(grading.grade_root_cause, s["reply"], answers()[row["prompt_id"]])
    usd = call(cost.session_cost, row["model"], s["requests"], row["meta"]["active_seconds"])
    print(f"  recorded run: {where} (case {row['prompt_id']}, one session)")
    print(f"    the session echoed: model {row['model']}, effort {row['meta']['effort_echoed']}")
    print(f"    root cause {rc} (your grader), format {grade_format(s['reply'])}")
    print(f"    ${usd:.4f} at the rate card (your session_cost), ${row['list_cost_usd']:.2f} list_cost,"
          f" {row['latency_s']:.0f} s, {row['tool_calls']} tool calls, {row['out_tokens']:,d} output tokens")
    print(f"    root-cause line: **Root cause:** {find_root_cause_line(s['reply'])}")


def run_live(model: str, effort: str | None, grading, cost, dry_run: bool) -> int:
    """One real session of the configured cell on reg-500s, through the eval runner, on the
    workshop's shipped system prompt. Lands in lab_runs/ (gitignored); spend.py counts it."""
    import run
    from snapshot import session
    flow = Path("lab_runs") / cell_tag(model, effort)
    system = EVALS / "lab_runs" / "system_shipped.md"
    system.parent.mkdir(exist_ok=True)
    system.write_text(config.SYSTEM)
    argv = ["--flow", flow.as_posix(), "--variant", "baseline", "--model", model, "--cases", "reg-500s",
            "--reps", "1", "--system-file", str(system), "--concurrency", "1"]
    argv += ["--effort", effort] if effort else []
    argv += ["--dry-run"] if dry_run else []
    print("  uv run python run.py " + " ".join(argv).replace(str(EVALS) + "/", ""))
    rc = run.main(argv)
    vdir = EVALS / flow / "baseline"
    if rc or dry_run or not (vdir / "results.jsonl").exists():
        return rc
    row = json.loads((vdir / "results.jsonl").read_text().splitlines()[0])
    report_session(row, session(vdir, row), grading, cost, f"{flow.as_posix()}/baseline/")
    return 0


# ── checkpoint 5 ────────────────────────────────────────────────────────
def checkpoint_5(solution: bool) -> int:
    grading, _ = lab("grading", solution)
    cost, _ = lab("cost", solution)
    keys = answers()
    floor = state("ladder")["floor"]
    print("Checkpoint 5: the cost-reduction path (results/, graded and priced by your code)")
    stats, rows_n, rc_same, usd_same = [], 0, 0, 0
    for c in path_cells():
        rc, fmt, verb, usd = [], [], [], []
        for row, s in recorded(c["cell"]):
            g = call(grading.grade_root_cause, s["reply"], keys[row["prompt_id"]])
            f = grade_format(s["reply"])
            u = call(cost.session_cost, row["model"], s["requests"], row["meta"]["active_seconds"])
            if {"train", "test"} & set(row["tags"]):
                rc.append(g)
            if row["prompt_id"] == "reg-verbatim":
                verb.append(g)
            fmt.append(f)
            usd.append(u)
            rows_n += 1
            rc_same += (g, f) == (row["grade"]["root_cause"], row["grade"]["format"])
            usd_same += abs(u - row["rate_card_usd"]) < 5e-6
        prompt = "shipped" if row["meta"]["system_sha"] == SHIPPED_SHA else "climbed"
        stats.append(dict(c, rows=len(fmt), rc=sum(rc) / len(rc), fmt=sum(fmt) / len(fmt), verb=verb,
                          cents=100 * sum(usd) / len(usd), prompt=prompt, effort_echoed=row["meta"]["effort_echoed"]))
    base = stats[0]
    need = base["rc"] - floor["root_cause_train_test_within_points_of_baseline"] / 100
    print(f"Floor, pre-registered: root cause on train+test ≥ {need:.1%} (baseline − 10 points), "
          f"reg-verbatim right on every rep, format ≥ {floor['format_min']:.0%}.")
    print()
    print(f"  {'#':1s}  {'cell':15s} {'model, effort, prompt':28s} {'rows':>4s} {'root cause':>10s} {'format':>7s}"
          f" {'verbatim':>8s} {'¢/incident':>10s}  floor")
    step = 0
    for c in stats:
        fails = [name for name, bad in (("root cause", c["rc"] < need - 1e-9),
                                         ("reg-verbatim", not all(c["verb"])),
                                         ("format", c["fmt"] < floor["format_min"] - 1e-9)) if bad]
        verdict = ("reference" if c is base else
                   ("pass" if not fails else "fail: " + ", ".join(fails)) + (" (off path)" if c.get("role") == "diagnostic" else ""))
        step += bool(c.get("adopted"))
        num = str(step) if c.get("adopted") else " "
        name = f"{NAMES[c['model']]}, {c['effort'] or c['effort_echoed']}, {c['prompt']}"
        verb = f"{sum(c['verb'])}/{len(c['verb'])}"
        print(f"  {num}  {c['cell']:15s} {name:28s} {c['rows']:4d} {c['rc']:10.1%} {c['fmt']:7.1%}"
              f" {verb:>8s} {c['cents']:10.2f}  {verdict}")
    path = [c for c in stats if c.get("adopted")]
    print()
    print(f"Your grades match the recorded ones on {rc_same}/{rows_n} rows; "
          f"your costs match the recorded rate card on {usd_same}/{rows_n}.")
    print("Adopted path (#): " + " → ".join(f"{c['cents']:.2f}¢" for c in path) + " per incident at the rate card ("
          + " and ".join(f"{base['cents'] / c['cents']:.1f}×" for c in path[1:]) + " cheaper than Opus 4.8).")
    print("Chart: results/path.png. The walk ends at Haiku 5.5 low, a narrow pass; climbed Sonnet 5.5 low")
    print("passes with margin and is the deployment recommendation (COST_LEDGER.md).")
    return int(rc_same != rows_n or usd_same != rows_n)


CHECKPOINTS = {"1": checkpoint_1, "2": checkpoint_2, "3": checkpoint_3, "4": checkpoint_4, "5": checkpoint_5}


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    which = [a for a in argv if not a.startswith("--")]
    solution, live, dry = "--solution" in argv, "--live" in argv, "--dry-run" in argv
    if len(which) != 1 or which[0] not in [*CHECKPOINTS, "all"]:
        print(__doc__.strip())
        return 2
    todo = list(CHECKPOINTS) if which[0] == "all" else which
    for i, n in enumerate(todo):
        if i:
            print()
        try:
            rc = checkpoint_4(solution, live, dry) if n == "4" else CHECKPOINTS[n](solution)
        except NotDone as e:
            print(f"  not done yet: {e}")
            print(f"  (or run the reference: uv run python checkpoint.py {n} --solution)")
            rc = 1
        if rc:
            return rc
    return 0


if __name__ == "__main__":
    sys.exit(main())
