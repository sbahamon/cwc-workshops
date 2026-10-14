# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0
"""The generator is deterministic, reproduces the original story, and its metrics agree with its log."""
import json
import math
import re
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from generate import alert_minute, build, write
from specs import SPECS, SPLITS, split_of

WORKSHOP = Path(__file__).resolve().parents[2]
GENERATED = [sc for sc in SPECS if not sc.verbatim]
BY_ID = {sc.id: sc for sc in SPECS}


@pytest.fixture(scope="module")
def built():
    return {sc.id: build(sc, split_of(sc)) for sc in SPECS}


def j(files, rel):
    return json.loads(files[rel])


def log_records(files):
    return [json.loads(line) for line in files["fixtures/app.log"].decode().splitlines()]


def ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


# ── determinism ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("sc", GENERATED, ids=lambda s: s.id)
def test_same_spec_same_bytes(sc, built):
    assert build(sc, split_of(sc)) == built[sc.id]


def test_write_matches_build(tmp_path, built):
    sc = BY_ID["reg-500s"]
    d = write(sc, split_of(sc), root=tmp_path)
    on_disk = {str(p.relative_to(d)): p.read_bytes() for p in d.rglob("*") if p.is_file()}
    assert on_disk == built[sc.id]


# ── case set shape ──────────────────────────────────────────────────────
def test_case_set_shape():
    ids = [sc.id for sc in SPECS]
    assert len(ids) == len(set(ids)) == 21
    counts = defaultdict(int)
    for sc in SPECS:
        counts[split_of(sc)] += 1
    assert dict(counts) == {"val": 4, "train": 9, "test": 8}
    assert set(SPLITS.values()) == {"val", "train", "test"}


@pytest.mark.parametrize("sc", GENERATED, ids=lambda s: s.id)
def test_log_size_in_budget(sc, built):
    assert 4_000 <= built[sc.id]["fixtures/app.log"].count(b"\n") <= 11_000


# ── the original story ──────────────────────────────────────────────────
def test_regression_reproduces_original_story(built):
    f = built["reg-500s"]
    ans = j(f, "answer.json")
    assert ans["culprit_short"] == "a3f9c21" and ans["culprit_service"] == "checkout"
    dep = {d["commit"]: d for d in j(f, "fixtures/deploys.json")}
    assert dep["a3f9c21"]["ts"] == "2026-04-22T14:31:18Z" and dep["a3f9c21"]["service"] == "checkout"
    assert set(dep) == {"e21b6c9", "9f1e2d4", "a3f9c21", "7b3e8f0"}

    recs = log_records(f)
    per_row = [r["ts"] for r in recs if "WHERE order_id = ?" in r["msg"]]
    assert per_row and min(per_row) >= "2026-04-22T14:31:18"
    pool = [r["ts"] for r in recs if "pool exhausted" in r["msg"]]
    assert pool and min(pool).startswith("2026-04-22T14:40")
    idp = [r for r in recs if r["service"] == "auth" and "identity-provider timeout" in r["msg"]]
    assert idp and all(r["ts"].startswith("2026-04-22T14:15") for r in idp)
    assert any("CLOSED for idp.internal" in r["msg"] and "recovered" in r["msg"] for r in recs)
    auth_p99 = [p["value"] for p in j(f, "fixtures/metrics.json")["auth"]["p99_latency_ms"]]
    assert max(v for v in auth_p99 if v is not None) < 500  # the red herring never pages

    # The page fires at ~14:32, like the original prompt.
    assert alert_minute(BY_ID["reg-500s"], j(f, "fixtures/metrics.json")) == "14:32"


def test_rephrased_regressions_share_one_log(built):
    logs = {built[i]["fixtures/app.log"] for i in ("reg-500s", "reg-1440", "reg-auth")}
    assert len(logs) == 1


def test_verbatim_case_is_the_original_fixtures(built):
    f = built["reg-verbatim"]
    data = WORKSHOP / "data"
    assert f["fixtures/app.log"] == (data / "app.log").read_bytes()
    assert f["fixtures/metrics.json"] == (data / "metrics.json").read_bytes()
    assert f["fixtures/deploys.json"] == (data / "deploys.json").read_bytes()
    assert f["fixtures/diffs/a3f9c21.txt"] == (data / "diff.txt").read_bytes()
    assert j(f, "case.json")["prompt"] == "checkout p99 spiked ~14:32 UTC. Find the root cause."  # e2e.py's prompt


# ── metrics agree with the log ──────────────────────────────────────────
@pytest.mark.parametrize("sc", GENERATED, ids=lambda s: s.id)
def test_metrics_recompute_from_log(sc, built):
    f = built[sc.id]
    starts, ends = {}, {}
    for r in log_records(f):
        if r["msg"].startswith("request_start"):
            starts[r["request_id"]] = (r["service"], ts(r["ts"]))
        elif r["msg"].startswith("request_end"):
            ends[r["request_id"]] = (r["latency_ms"], r["status"])
    assert starts.keys() == ends.keys()
    buckets = defaultdict(list)
    for rid, (svc, t) in starts.items():
        buckets[(svc, int((t - sc.start).total_seconds() // 60))].append(ends[rid])
    metrics = j(f, "fixtures/metrics.json")
    for svc, series in metrics.items():
        for k, (p, e) in enumerate(zip(series["p99_latency_ms"], series["error_rate"])):
            rows = buckets.get((svc, k), [])
            lats = sorted(lat for lat, _ in rows)
            want_p99 = float(lats[max(0, math.ceil(0.99 * len(lats)) - 1)]) if lats else None
            want_err = round(sum(s >= 500 for _, s in rows) / len(rows), 4) if rows else None
            assert (p["value"], e["value"]) == (want_p99, want_err), (svc, p["ts"])


@pytest.mark.parametrize("sc", GENERATED, ids=lambda s: s.id)
def test_pool_exhaustion_lines_fall_in_full_pool_minutes(sc, built):
    f = built[sc.id]
    util = {(svc, p["ts"][:16]): p["value"]
            for svc, s in j(f, "fixtures/metrics.json").items() for p in s["db_pool_utilization"]}
    for r in log_records(f):
        if "pool exhausted" in r["msg"]:
            assert util[(r["service"], r["ts"][:16])] == 1.0, (r["service"], r["ts"])


@pytest.mark.parametrize("sc", GENERATED, ids=lambda s: s.id)
def test_every_deploy_has_a_diff_and_a_log_line(sc, built):
    f = built[sc.id]
    deploys = j(f, "fixtures/deploys.json")
    msgs = [r["msg"] for r in log_records(f)]
    for d in deploys:
        assert f"fixtures/diffs/{d['commit']}.txt" in f
        if sc.start <= ts(d["ts"]) < sc.end:
            assert f"deploy_complete version={d['commit']} strategy=rolling" in msgs
        if "rolled_back_at" in d and sc.start <= ts(d["rolled_back_at"]) < sc.end:
            assert f"deploy_rollback version={d['commit']} reason=manual" in msgs


# ── each family tests what it says it tests ─────────────────────────────
@pytest.mark.parametrize("sc", GENERATED, ids=lambda s: s.id)
def test_page_fires_just_after_onset(sc, built):
    if sc.prompt is not None:
        return
    f = built[sc.id]
    onset = ts(j(f, "answer.json")["degraded_at"])  # = deploy time, unless a slow burn
    hhmm = re.search(r"~(\d\d:\d\d) UTC", j(f, "case.json")["prompt"]).group(1)
    page = onset.replace(hour=int(hhmm[:2]), minute=int(hhmm[3:]), second=0)
    assert timedelta(0) <= page - onset.replace(second=0) <= timedelta(minutes=2)


@pytest.mark.parametrize("sc", SPECS, ids=lambda s: s.id)
def test_family_invariants(sc, built):
    f = built[sc.id]
    ans, deploys = j(f, "answer.json"), j(f, "fixtures/deploys.json")
    by_sha = {d["commit"]: d for d in deploys}
    if sc.family == "no_culprit":
        assert ans["kind"] == "component" and ans["culprit_sha"] is None and ans["components"]
        onset = ts(ans["onset"])
        assert not [d for d in deploys if onset - timedelta(minutes=30) <= ts(d["ts"]) <= onset + timedelta(minutes=2)]
        return
    culprit = by_sha[ans["culprit_short"]]
    assert ans["kind"] == "deploy" and culprit["status"] == "success"
    assert culprit["service"] == sc.affected_service
    others = [d for d in deploys if d is not culprit]
    if sc.family == "shifted":
        assert culprit["ts"] != "2026-04-22T14:31:18Z"
    risky = re.compile(r"perf|n\+1|query|slow|batch|cache", re.I)
    if sc.family == "rolled_back":
        # A same-service deploy after the culprit, rolled back before full degradation:
        # it's the latest deploy before the page, so timing alone points at it.
        later_rb = [d for d in others if d["status"] == "rolled_back" and d["service"] == sc.affected_service
                    and ts(d["ts"]) > ts(culprit["ts"]) and ts(d["rolled_back_at"]) < ts(ans["degraded_at"])]
        assert later_rb
        # Slow burn: the culprit's per-row queries are already in the log before the
        # rolled-back deploy goes out (rb-early-n1 also has an earlier, rolled-back N+1).
        per_row = [r["ts"] for r in log_records(f) if r["msg"].startswith("db_query") and "= ?" in r["msg"]
                   and culprit["ts"][:19] <= r["ts"] < later_rb[0]["ts"]]
        assert len(per_row) >= 20
    if sc.family == "innocent_message":
        assert not risky.search(culprit["summary"])
        # A guilty-sounding harmless deploy to the same service, same minute, after the culprit.
        twin = [d for d in others if d["service"] == sc.affected_service and risky.search(d["summary"])
                and d["ts"][:16] == culprit["ts"][:16] and d["ts"] > culprit["ts"]]
        assert twin
    if sc.family == "decoy":
        near = [d for d in others if d["service"] != culprit["service"]
                and abs((ts(d["ts"]) - ts(culprit["ts"])).total_seconds()) <= 120]
        assert near


@pytest.mark.parametrize("sc", [s for s in SPECS if s.family == "decoy"], ids=lambda s: s.id)
def test_decoy_cannot_explain_the_page(sc, built):
    """A careful agent must not be able to defend blaming the decoy; if it could, the
    grader would mark a reasonable answer wrong and the case would add noise."""
    f = built[sc.id]
    ans, deploys = j(f, "answer.json"), j(f, "fixtures/deploys.json")
    culprit = next(d for d in deploys if d["commit"] == ans["culprit_short"])
    p99 = {svc: [(ts(p["ts"]), p["value"]) for p in s["p99_latency_ms"]]
           for svc, s in j(f, "fixtures/metrics.json").items()}
    decoys = [d for d in deploys if d is not culprit
              and abs((ts(d["ts"]) - ts(culprit["ts"])).total_seconds()) <= 120]
    assert decoys
    affected_logs = [r["msg"] for r in log_records(f) if r["service"] == sc.affected_service]
    for d in decoys:
        assert d["service"] != sc.affected_service
        # The decoy's own service never reaches the page threshold.
        assert max(v for _, v in p99[d["service"]] if v is not None) < 500, d["commit"]
        # Nothing in the paged service's log points at the decoy's service.
        assert not [m for m in affected_logs if d["service"] in m]
        if ts(d["ts"]) > ts(culprit["ts"]):
            # A later decoy deploys after the paged service is already degraded.
            first_high = next(t for t, v in p99[sc.affected_service] if v is not None and v > 500)
            assert first_high + timedelta(minutes=1) <= ts(d["ts"]), d["commit"]
        else:
            # An earlier decoy leaves the paged service healthy until the culprit lands.
            assert all(v is None or v <= 500 for t, v in p99[sc.affected_service]
                       if t + timedelta(minutes=1) <= ts(culprit["ts"]))
