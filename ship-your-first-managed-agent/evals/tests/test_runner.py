# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0
"""Runner wiring, offline (eval-audit §2): oracle ~100%, null ~0%, failures land in
errors.jsonl and never as a 0, resume is idempotent, and the gates hold.

Every test drives run.main() with --fake, which replays a scripted session
through the same drive() loop and record() path the live backend uses."""
import json
from pathlib import Path

import pytest

import run
from generate import write
from specs import SPECS, split_of

FEW = ["reg-500s", "shift-early", "nc-db-1", "dc-cart"]


@pytest.fixture(scope="module")
def cases_dir(tmp_path_factory):
    root = tmp_path_factory.mktemp("cases")
    for sc in SPECS:
        if sc.id in FEW:
            write(sc, split_of(sc), root=root)
    return root


def go(flow: Path, cases_dir: Path, *extra: str, variant="baseline", reps="2"):
    return run.main(["--flow", str(flow), "--variant", variant, "--model", "claude-opus-4-8",
                     "--reps", reps, "--cases-dir", str(cases_dir), "--concurrency", "2", *extra])


def rows(path: Path):
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()] if path.exists() else []


def test_oracle_scores_everything(tmp_path, cases_dir):
    assert go(tmp_path / "flow", cases_dir, "--fake", "oracle") == 0
    rs = rows(tmp_path / "flow/baseline/results.jsonl")
    assert len(rs) == len(FEW) * 2
    assert all(r["grade"] == {"root_cause": 1, "format": 1} for r in rs)
    # Every field the report and the ledger need is present and non-trivial.
    for r in rs:
        assert r["model"] == "claude-opus-4-8" and r["usage"]["output_tokens"] > 0
        assert r["latency_s"] > 0 and r["tool_calls"] == 2 and r["status"] == "ok"
        assert r["rate_card_usd"] > 0 and r["list_cost_usd"] is not None  # both costs, side by side
        assert "pricing.py" in r["meta"]["rate_card_basis"]
        assert r["tags"][0] in {"regression", "shifted", "no_culprit", "decoy"}
        assert r["meta"]["deploys_before_first_log_access"] is True and r["meta"]["fake"] is True
    trace = json.loads((tmp_path / f"flow/baseline/traces/{FEW[0]}_rep0.json").read_text())
    assert [t["role"] for t in trace] == ["system", "user", "tool_call", "tool_result", "tool_call",
                                          "tool_result", "assistant"]
    assert trace[3]["name"] == "get_recent_deploys" and trace[3]["content"].lstrip().startswith("[")


def test_null_and_constant_score_as_expected(tmp_path, cases_dir):
    go(tmp_path / "n", cases_dir, "--fake", "null")
    assert all(r["grade"] == {"root_cause": 0, "format": 0} for r in rows(tmp_path / "n/baseline/results.jsonl"))
    go(tmp_path / "c", cases_dir, "--fake", "const")
    got = {r["prompt_id"]: r["grade"]["root_cause"] for r in rows(tmp_path / "c/baseline/results.jsonl")}
    assert got == {"reg-500s": 1, "shift-early": 0, "nc-db-1": 0, "dc-cart": 0}


@pytest.mark.parametrize("mode,cls", [("api_error", "serving_error"), ("budget", "budget"), ("timeout", "timeout")])
def test_failures_go_to_errors_never_to_results(tmp_path, cases_dir, mode, cls):
    go(tmp_path / "f", cases_dir, "--fake", mode, "--timeout-s", "0.2", reps="1")
    assert rows(tmp_path / "f/baseline/results.jsonl") == []
    errs = rows(tmp_path / "f/baseline/errors.jsonl")
    assert len(errs) == len(FEW) and {e["class"] for e in errs} == {cls}


def test_resume_is_idempotent_and_reruns_failures(tmp_path, cases_dir):
    flow = tmp_path / "r"
    go(flow, cases_dir, "--fake", "api_error", reps="1")
    assert len(rows(flow / "baseline/errors.jsonl")) == len(FEW)
    go(flow, cases_dir, "--fake", "oracle", reps="1")       # errored keys get re-run
    go(flow, cases_dir, "--fake", "oracle", reps="1")       # nothing left to do
    rs = rows(flow / "baseline/results.jsonl")
    assert sorted((r["prompt_id"], r["rep"]) for r in rs) == sorted((c, 0) for c in FEW)


def test_harness_gate_blocks_until_approved(tmp_path, cases_dir):
    flow = tmp_path / "g"
    flow.mkdir()
    (flow / "_state.json").write_text(json.dumps({"reps": 1, "harness_paths": ["graders.py"]}))
    assert go(flow, cases_dir, "--fake", "oracle", reps="1") == 2
    assert not (flow / "baseline/results.jsonl").exists()
    assert go(flow, cases_dir, "--fake", "oracle", "--approve-harness", reps="1") == 0
    assert json.loads((flow / "_state.json").read_text())["harness_sha"]
    assert go(flow, cases_dir, "--fake", "oracle", reps="1") == 0  # approved sha still matches


def test_fake_refuses_the_real_flow_dirs(cases_dir):
    assert go(run.EVALS / "hillclimb/ladder", cases_dir, "--fake", "oracle") == 2


def test_spend_cap_refuses_before_any_session(tmp_path, cases_dir, monkeypatch):
    monkeypatch.setattr(run, "check_harness", lambda *a: True)  # approved; the cap is what's under test
    monkeypatch.setattr(run, "total_spend", lambda: 49.50)
    monkeypatch.setattr(run, "LiveBackend", lambda *_: pytest.fail("no backend may be built past the cap"))
    # 4 cases x 2 reps at the $1.00 worst-case budget = $8 projected; 49.50 + 8 > 50.
    assert go(tmp_path / "s", cases_dir) == 3


def test_dry_run_sends_nothing(tmp_path, cases_dir, monkeypatch, capsys):
    monkeypatch.setattr(run, "LiveBackend", lambda *_: pytest.fail("dry run built a backend"))
    assert go(tmp_path / "d", cases_dir, "--dry-run") == 0
    out = capsys.readouterr().out
    assert "4 cases × 2 reps × claude-opus-4-8 (default effort)" in out and "budget $1.00/session" in out


def test_served_model_mismatch_is_an_error(tmp_path, cases_dir, monkeypatch):
    orig = run.FakeBackend.run

    def swapped(self, *a, **k):
        att = orig(self, *a, **k)
        att.model = "claude-haiku-5-5"
        return att
    monkeypatch.setattr(run.FakeBackend, "run", swapped)
    go(tmp_path / "m", cases_dir, "--fake", "oracle", reps="1")
    assert rows(tmp_path / "m/baseline/results.jsonl") == []
    assert {e["class"] for e in rows(tmp_path / "m/baseline/errors.jsonl")} == {"served_model_mismatch"}


def test_messages_are_joined_on_new_lines(cases_dir):
    """A message arriving after the root-cause line must not be glued onto it."""
    from types import SimpleNamespace as ns
    import threading
    from tools import CaseTools
    from graders import grade_format
    msg = lambda t: ns(type="agent.message", content=[ns(type="text", text=t)])
    evs = [msg("> **Root cause:** `a3f9c21` — per-row query loop."), msg("Want me to open a revert PR?"),
           ns(type="session.status_idle", stop_reason=ns(type="end_turn"))]
    att = run.Attempt()
    run.drive(iter(evs), lambda e: None, CaseTools(cases_dir / "reg-500s"), att, threading.Event())
    assert grade_format(att.final_text) == 1
    assert att.turns[-1]["content"].splitlines()[-1] == "Want me to open a revert PR?"


def test_flows_without_state_use_the_ladder_gate(tmp_path, cases_dir, monkeypatch):
    ladder = tmp_path / "ladder_state.json"
    ladder.write_text(json.dumps({"harness_paths": []}))
    monkeypatch.setattr(run, "LADDER_STATE", ladder)
    monkeypatch.setattr(run, "LiveBackend", lambda *_: pytest.fail("ran past an unapproved gate"))
    assert go(tmp_path / "pilot", cases_dir, reps="1") == 2          # a live pilot is gated
    assert go(tmp_path / "pilot2", cases_dir, "--fake", "oracle", reps="1") == 0  # offline fakes are not


def test_ceiling_survives_a_read_that_close_cannot_unblock():
    """The live failure from the 2026-10-14 pilot: a reader stuck in a socket read that
    another thread can't interrupt. The ceiling must still return, as a timeout."""
    import threading, time
    stuck = threading.Event()  # never set: stands in for ssl.read() that close() can't wake
    t0 = time.monotonic()
    fired = []
    finished = run.run_with_ceiling(lambda: stuck.wait(), timeout_s=0.2, on_timeout=lambda: fired.append(1), grace_s=0.2)
    assert finished is False and fired == [1] and time.monotonic() - t0 < 2


def test_ceiling_lets_the_interrupt_finish_the_turn():
    """The normal timeout path: on_timeout sends user.interrupt, the server goes idle, the
    reader sees it and exits by itself within the grace period."""
    import threading
    idle = threading.Event()
    finished = run.run_with_ceiling(lambda: idle.wait(), timeout_s=0.1, on_timeout=idle.set, grace_s=2)
    assert finished is True


def test_ceiling_is_silent_when_the_turn_finishes_in_time():
    fired = []
    assert run.run_with_ceiling(lambda: None, timeout_s=5, on_timeout=lambda: fired.append(1)) is True
    assert fired == []


def _seq(cases_dir, *calls):
    """Drive a scripted list of ('sandbox'|'custom', name, input) calls; return the Attempt."""
    from types import SimpleNamespace as ns
    import threading
    from tools import CaseTools
    evs = []
    for i, (kind, name, inp) in enumerate(calls):
        evs.append(ns(type="agent.tool_use" if kind == "sandbox" else "agent.custom_tool_use",
                      id=f"t{i}", name=name, input=inp))
    evs.append(ns(type="session.status_idle", stop_reason=ns(type="end_turn")))
    att = run.Attempt()
    run.drive(iter(evs), lambda e: None, CaseTools(cases_dir / "reg-500s"), att, threading.Event())
    return att


def test_reading_the_runbook_is_not_opening_the_log(cases_dir):
    # What every pilot agent did: read SKILL.md, then pull deploys, then grep the log.
    att = _seq(cases_dir, ("sandbox", "read", {"file_path": "/workspace/skills/incident-triage-runbook/SKILL.md"}),
               ("custom", "get_recent_deploys", {}),
               ("sandbox", "bash", {"command": "grep -c deploy_complete /mnt/session/uploads/app.log"}))
    assert att.deploys_before_first_log_access is True


def test_log_first_is_flagged(cases_dir):
    att = _seq(cases_dir, ("sandbox", "bash", {"command": "head /mnt/session/uploads/app.log"}),
               ("custom", "get_recent_deploys", {}))
    assert att.deploys_before_first_log_access is False


def test_never_touching_the_log_counts_as_deploys_first_only_if_deploys_were_pulled(cases_dir):
    assert _seq(cases_dir, ("custom", "get_recent_deploys", {})).deploys_before_first_log_access is True
    assert _seq(cases_dir, ("custom", "get_metrics", {"service": "checkout", "metric": "p99_latency_ms"})
                ).deploys_before_first_log_access is False
