# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0
"""
Write every eval case in specs.py to cases/<id>/.

    uv run python generate.py            # all cases
    uv run python generate.py reg-500s   # just one

Per case:
  cases/<id>/case.json            id, family, split, prompt, tags  (runner reads this)
  cases/<id>/answer.json          ground truth                     (grader reads this ONLY)
  cases/<id>/fixtures/app.log     uploaded to the agent's sandbox
  cases/<id>/fixtures/metrics.json, deploys.json, diffs/<sha7>.txt  served by tools.py

The log, metrics, deploys and diffs come from one simulation of the spec, so the
per-minute metrics are exactly what the log's requests imply. Deterministic for
a given spec: the same spec writes byte-identical files. Stdlib only, like the
workshop's data/generate_log.py (which this borrows from but does not modify).
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import shutil
import string
import sys
from datetime import datetime, timedelta
from pathlib import Path

from diffs import N1, batched_sql, per_row_sql, render
from scenario import (DB_PRIMARY_EXHAUST_S, DB_SERVICES, FAULT_KINDS, N_PLUS_ONE_EXHAUST_S,
                      SERVICES, Deploy, Scenario)

HERE = Path(__file__).parent
WORKSHOP = HERE.parent
CASES_DIR = HERE / "cases"

ENDPOINTS = {
    "checkout": ["/api/checkout/submit", "/api/checkout/summary", "/api/checkout/validate"],
    "cart": ["/api/cart", "/api/cart/add", "/api/cart/remove"],
    "auth": ["/api/auth/login", "/api/auth/refresh", "/api/auth/logout"],
    "inventory": ["/api/inventory/check", "/api/inventory/reserve"],
}
HOSTS = {svc: [f"{svc}-{i}" for i in range(1, 4)] for svc in SERVICES}
WEIGHTS = [3, 3, 2, 2]


def iso_ms(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ts.microsecond // 1000:03d}Z"


def iso_s(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def sha_for(sc: Scenario, i: int, d: Deploy) -> str:
    return d.sha or hashlib.sha1(f"{sc.id}:{i}".encode()).hexdigest()


def p99(values: list[int]) -> float | None:
    """Nearest-rank 99th percentile (what tests recompute from the log)."""
    if not values:
        return None
    s = sorted(values)
    return float(s[max(0, math.ceil(0.99 * len(s)) - 1)])


class Sim:
    def __init__(self, sc: Scenario):
        self.sc = sc
        self.rng = random.Random(sc.seed)
        self.buf: list[str] = []
        self.requests: list[tuple[str, datetime, int, int]] = []  # service, start, latency, status

    # ── causes ──────────────────────────────────────────────────────────
    def n1_live(self, svc: str, t: datetime) -> Deploy | None:
        for d in self.sc.deploys:
            if d.service == svc and d.diff_kind == "n_plus_one" and d.live_at(t):
                return d
        return None

    def cache_removed_live(self, svc: str, t: datetime) -> bool:
        return any(d.service == svc and d.diff_kind == "cache_removed" and d.live_at(t)
                   for d in self.sc.deploys)

    def incident(self, kind: str, svc: str, t: datetime) -> bool:
        inc = self.sc.incident
        if inc is None or inc.kind != kind or t < inc.start:
            return False
        return svc in DB_SERVICES if kind == "db_primary" else svc == self.sc.affected_service

    def exhaust_at(self, svc: str, t: datetime) -> datetime | None:
        """When svc's DB pool runs out under the cause live at t (None = never)."""
        d = self.n1_live(svc, t)
        if d is not None:
            ex = d.degraded_from + timedelta(seconds=N_PLUS_ONE_EXHAUST_S)
            return ex if d.rolled_back_at is None or ex < d.rolled_back_at else None
        if self.incident("db_primary", svc, t):
            return self.sc.incident.start + timedelta(seconds=DB_PRIMARY_EXHAUST_S)
        return None

    def pool_down(self, svc: str, t: datetime) -> bool:
        ex = self.exhaust_at(svc, t)
        return ex is not None and t >= ex

    # ── log lines ───────────────────────────────────────────────────────
    def emit(self, ts: datetime, **fields) -> None:
        rec = {"ts": iso_ms(ts)}
        rec.update(fields)
        self.buf.append(json.dumps(rec, separators=(",", ":")))

    def rid(self) -> str:
        return "req_" + "".join(self.rng.choices(string.hexdigits.lower(), k=12))

    def request(self, svc: str, ts: datetime) -> None:
        r = self.rng
        req, user = self.rid(), f"u_{r.randint(10000, 99999)}"
        host, ep = r.choice(HOSTS[svc]), r.choice(ENDPOINTS[svc])
        common = dict(service=svc, host=host)
        self.emit(ts, level="INFO", **common, msg=f"request_start method=POST path={ep}",
                  request_id=req, user_id=user)
        status, cursor = 200, ts
        n1 = self.n1_live(svc, ts)

        if n1 is not None and ts < n1.degraded_from:  # slow burn: loop shipped, still cheap
            frac = (ts - n1.ts) / (n1.degraded_from - n1.ts)
            for _ in range(r.randint(2, 5)):
                cursor += timedelta(milliseconds=r.randint(2, 12))
                self.emit(cursor, level="DEBUG", **common,
                          msg=f'db_query sql="{per_row_sql(svc)}" params=[{r.randint(1000, 9999)}]',
                          request_id=req, duration_ms=r.randint(2, 9))
            lat = r.randint(40, 110) + int(330 * frac)  # tops out under the 500 ms page line
        elif n1 is not None:  # per-row query loop (the original incident)
            mins = (ts - n1.degraded_from).total_seconds() / 60.0
            for _ in range(r.randint(8, 16)):
                cursor += timedelta(milliseconds=r.randint(2, 30))
                self.emit(cursor, level="DEBUG", **common,
                          msg=f'db_query sql="{per_row_sql(svc)}" params=[{r.randint(1000, 9999)}]',
                          request_id=req, duration_ms=r.randint(2, 25))
            lat = r.randint(800, 4000) + int(mins * 50)
            if self.pool_down(svc, ts) and r.random() < 0.35:
                status = 500
            elif self.pool_down(svc, ts) and r.random() < 0.5:
                self.emit(cursor, level="WARN", **common,
                          msg=f"db_pool high utilization active={r.randint(42, 50)}/50", request_id=req)
        elif self.incident("db_primary", svc, ts):  # shared DB degraded, no code change
            mins = (ts - self.sc.incident.start).total_seconds() / 60.0
            lat = r.randint(400, 2500) + int(mins * 40)
            if r.random() < 0.4:
                cursor += timedelta(milliseconds=r.randint(5, 40))
                self.emit(cursor, level="WARN", **common,
                          msg=f"slow query {r.randint(900, 4800)}ms on db-primary (lock wait)",
                          request_id=req, db="db-primary")
            if self.pool_down(svc, ts) and r.random() < 0.25:
                status = 500
        elif self.incident("stripe_api", svc, ts):  # slow upstream dependency
            upstream = r.randint(1500, 6000)
            cursor += timedelta(milliseconds=r.randint(3, 12))
            if upstream > 5000:
                self.emit(cursor, level="ERROR", **common, msg="upstream stripe-api timeout after 5000ms",
                          request_id=req, upstream="stripe-api")
                status, lat = 502, 5000 + r.randint(5, 40)
            else:
                self.emit(cursor, level="INFO", **common,
                          msg=f"upstream_call stripe-api latency_ms={upstream}", request_id=req,
                          upstream="stripe-api")
                lat = upstream + r.randint(20, 80)
        else:  # healthy
            lat = r.randint(20, 80)
            if self.cache_removed_live(svc, ts):
                lat += r.randint(150, 400)
                cursor += timedelta(milliseconds=r.randint(1, 5))
                self.emit(cursor, level="DEBUG", **common,
                          msg=f"cache_miss key=catalog:page:{r.randint(1, 40)}", request_id=req)
            if svc in DB_SERVICES and r.random() < 0.5:
                cursor += timedelta(milliseconds=r.randint(2, 15))
                self.emit(cursor, level="DEBUG", **common,
                          msg=f'db_query sql="{batched_sql(svc)}" rows={r.randint(2, 18)}',
                          request_id=req, duration_ms=r.randint(3, 20))

        if status == 500:
            self.emit(cursor + timedelta(milliseconds=5), level="ERROR", **common,
                      msg="DB connection pool exhausted (active=50/50, waiters=12)", request_id=req)
            self.emit(cursor + timedelta(milliseconds=8), level="ERROR", **common,
                      msg=f"request_end status=500 path={ep} error=PoolTimeout",
                      request_id=req, user_id=user, latency_ms=lat, status=500)
        elif status == 502:
            self.emit(cursor + timedelta(milliseconds=6), level="ERROR", **common,
                      msg=f"request_end status=502 path={ep} error=UpstreamTimeout",
                      request_id=req, user_id=user, latency_ms=lat, status=502)
        else:
            self.emit(ts + timedelta(milliseconds=lat), level="INFO", **common,
                      msg=f"request_end status=200 path={ep}", request_id=req, user_id=user,
                      latency_ms=lat, status=200)
        self.requests.append((svc, ts, lat, status))

    def auth_red_herring(self, base: datetime) -> None:
        """Unrelated idp timeouts that self-resolve (the original story's red herring)."""
        r = self.rng
        for i in range(6):
            self.emit(base + timedelta(seconds=i * 7 + r.randint(0, 3)), level="ERROR", service="auth",
                      host=r.choice(HOSTS["auth"]), msg="upstream identity-provider timeout after 5000ms",
                      request_id=self.rid(), upstream="idp.internal")
        self.emit(base + timedelta(seconds=55), level="WARN", service="auth", host="auth-1",
                  msg="circuit_breaker OPEN for idp.internal (will retry in 30s)")
        self.emit(base + timedelta(seconds=90), level="INFO", service="auth", host="auth-1",
                  msg="circuit_breaker CLOSED for idp.internal — recovered")

    def background(self, shas: list[str]) -> None:
        r, sc = self.rng, self.sc
        t = sc.start
        while t < sc.end:
            for svc in SERVICES:
                self.emit(t, level="DEBUG", service=svc, host=r.choice(HOSTS[svc]),
                          msg="healthcheck OK", uptime_s=r.randint(3600, 86400))
            t += timedelta(seconds=30)
        for _ in range(15):
            svc = r.choice(SERVICES)
            self.emit(sc.start + timedelta(seconds=r.randint(0, sc.minutes * 60 - 1)), level="WARN",
                      service=svc, host=r.choice(HOSTS[svc]),
                      msg=f"GC pause {r.randint(80, 350)}ms (G1 young gen)")
        for _ in range(40):
            self.emit(sc.start + timedelta(seconds=r.randint(0, sc.minutes * 60 - 1)), level="DEBUG",
                      service="inventory", host=r.choice(HOSTS["inventory"]),
                      msg=f"cache_miss key=sku:{r.randint(100000, 999999)}")
        # Every deploy and rollback inside the window is logged, not just the culprit's.
        for d, sha in zip(sc.deploys, shas):
            if sc.start <= d.ts < sc.end:
                self.emit(d.ts, level="INFO", service=d.service, host=f"{d.service}-1",
                          msg=f"deploy_complete version={sha[:7]} strategy=rolling", commit=sha[:7])
            if d.rolled_back_at is not None and sc.start <= d.rolled_back_at < sc.end:
                self.emit(d.rolled_back_at, level="WARN", service=d.service, host=f"{d.service}-1",
                          msg=f"deploy_rollback version={sha[:7]} reason=manual", commit=sha[:7])

    def run(self, shas: list[str]) -> None:
        sc, r = self.sc, self.rng
        t = sc.start
        whole, frac = int(sc.req_per_s), sc.req_per_s - int(sc.req_per_s)
        while t < sc.end:
            for _ in range(whole + (1 if r.random() < frac else 0)):
                ts = t + timedelta(milliseconds=r.randint(0, 999))
                self.request(r.choices(SERVICES, weights=WEIGHTS)[0], ts)
            t += timedelta(seconds=1)
        if sc.auth_red_herring_at is not None:
            self.auth_red_herring(sc.auth_red_herring_at)
        self.background(shas)
        self.buf.sort(key=lambda line: line[7:31])  # fixed-width ISO prefix; stable

    # ── metrics ─────────────────────────────────────────────────────────
    def pool_util(self, svc: str, m0: datetime, base: float) -> float:
        # 1.0 for any minute in which the pool is exhausted at some instant, so every
        # "pool exhausted" log line falls in a minute that reads 100%.
        m1 = m0 + timedelta(minutes=1)
        for probe in (m0, m1 - timedelta(milliseconds=1)):
            ex = self.exhaust_at(svc, probe)
            if ex is not None and ex < m1 and self.pool_down(svc, max(m0, ex)):
                return 1.0
        mid = m0 + timedelta(seconds=30)
        d = self.n1_live(svc, mid)
        if d is not None:
            exd = d.degraded_from + timedelta(seconds=N_PLUS_ONE_EXHAUST_S)
            return round(base + (0.97 - base) * min(1.0, (mid - d.ts) / (exd - d.ts)), 3)
        if self.incident("db_primary", svc, mid):
            inc = self.sc.incident.start
            return round(base + (0.97 - base) * min(1.0, (mid - inc).total_seconds() / DB_PRIMARY_EXHAUST_S), 3)
        if self.incident("stripe_api", svc, mid):
            inc = self.sc.incident.start
            return round(base + (0.72 - base) * min(1.0, (mid - inc).total_seconds() / 300), 3)
        if self.cache_removed_live(svc, mid):
            return round(base + 0.12, 3)
        return round(base, 3)

    def metrics(self) -> dict:
        sc = self.sc
        noise = random.Random(sc.seed + 1)  # separate stream: metrics noise never shifts the log
        out: dict = {svc: {"p99_latency_ms": [], "error_rate": [], "db_pool_utilization": []} for svc in SERVICES}
        by_bucket: dict[tuple[str, int], list[tuple[int, int]]] = {}
        for svc, ts, lat, status in self.requests:
            k = int((ts - sc.start).total_seconds() // 60)
            by_bucket.setdefault((svc, k), []).append((lat, status))
        for k in range(sc.minutes):
            m0 = sc.start + timedelta(minutes=k)
            for svc in SERVICES:
                rows = by_bucket.get((svc, k), [])
                lats = [lat for lat, _ in rows]
                err = round(sum(1 for _, s in rows if s >= 500) / len(rows), 4) if rows else None
                out[svc]["p99_latency_ms"].append({"ts": iso_s(m0), "value": p99(lats)})
                out[svc]["error_rate"].append({"ts": iso_s(m0), "value": err})
                out[svc]["db_pool_utilization"].append(
                    {"ts": iso_s(m0), "value": self.pool_util(svc, m0, noise.uniform(0.08, 0.2))})
        return out


def alert_minute(sc: Scenario, metrics: dict) -> str:
    """When the page for the *ongoing* incident fires: the last stretch of p99 > 500 ms that
    runs to the end of the window, stamped at its second minute. An earlier blip that
    recovered (e.g. a rolled-back deploy) doesn't page. Reproduces the original:
    deploy 14:31:18 -> page "~14:32"."""
    pts = metrics[sc.affected_service]["p99_latency_ms"]
    high = [p["value"] is not None and p["value"] > 500 for p in pts]
    if not high[-1]:
        raise ValueError(f"{sc.id}: {sc.affected_service} p99 isn't high at the end of the window")
    i = len(high) - 1
    while i > 0 and high[i - 1]:
        i -= 1
    if i + 1 >= len(pts):
        raise ValueError(f"{sc.id}: incident starts in the last minute")
    return pts[i + 1]["ts"][11:16]


def derived_prompt(sc: Scenario, metrics: dict) -> str:
    return f"{sc.affected_service} p99 spiked ~{alert_minute(sc, metrics)} UTC. Find the root cause."


def build(sc: Scenario, split: str) -> dict[str, bytes]:
    """Every file for one case, as {relative path: bytes}. Pure: no disk writes."""
    files: dict[str, bytes] = {}
    if sc.verbatim:
        return build_verbatim(sc, split)
    for d in sc.deploys:
        if d.diff_kind == "n_plus_one":
            assert d.service in N1, f"{sc.id}: no N+1 template for {d.service}"
        assert d.ts <= sc.end and d.ts >= sc.end - timedelta(hours=6), f"{sc.id}: deploy outside last 6h"
    shas = [sha_for(sc, i, d) for i, d in enumerate(sc.deploys)]
    sim = Sim(sc)
    sim.run(shas)
    metrics = sim.metrics()
    log = "\n".join(sim.buf) + "\n"

    deploys = []
    for d, sha in sorted(zip(sc.deploys, shas), key=lambda x: x[0].ts):
        rec = {"ts": iso_s(d.ts), "service": d.service, "commit": sha[:7], "author": d.author,
               "status": d.status, "summary": d.summary}
        if d.rolled_back_at is not None:
            rec["rolled_back_at"] = iso_s(d.rolled_back_at)
        deploys.append(rec)
        files[f"fixtures/diffs/{sha[:7]}.txt"] = render(
            d.diff_kind, d.service, sha, d.author, d.ts, d.summary).encode()
    files["fixtures/app.log"] = log.encode()
    files["fixtures/metrics.json"] = (json.dumps(metrics, indent=2) + "\n").encode()
    files["fixtures/deploys.json"] = (json.dumps(deploys, indent=2) + "\n").encode()

    culprit = sc.culprit()
    if culprit is not None:
        sha = shas[sc.deploys.index(culprit)]
        answer = {"kind": "deploy", "culprit_sha": sha, "culprit_short": sha[:7],
                  "culprit_service": culprit.service, "components": [],
                  "onset": iso_s(culprit.ts), "degraded_at": iso_s(culprit.degraded_from)}
    else:
        inc = sc.incident
        answer = {"kind": "component", "culprit_sha": None, "culprit_short": None,
                  "culprit_service": None,
                  "components": {"db_primary": ["db-primary", "db primary", "primary db", "primary database"],
                                 "stripe_api": ["stripe-api", "stripe api", "stripe"]}[inc.kind],
                  "onset": iso_s(inc.start), "degraded_at": iso_s(inc.start)}
    prompt = sc.prompt or derived_prompt(sc, metrics)
    return finish(sc, split, prompt, answer, files)


def build_verbatim(sc: Scenario, split: str) -> dict[str, bytes]:
    """The original workshop fixtures, unchanged: the harness-parity case."""
    data = WORKSHOP / "data"
    if not (data / "app.log").exists():  # same first-run path app.py uses
        sys.path.insert(0, str(WORKSHOP))
        from data.generate_log import main as generate_original_log
        generate_original_log()
    diff = (data / "diff.txt").read_text()
    sha = diff.split("\n", 1)[0].split()[1]
    files = {
        "fixtures/app.log": (data / "app.log").read_bytes(),
        "fixtures/metrics.json": (data / "metrics.json").read_bytes(),
        "fixtures/deploys.json": (data / "deploys.json").read_bytes(),
        f"fixtures/diffs/{sha[:7]}.txt": diff.encode(),
    }
    answer = {"kind": "deploy", "culprit_sha": sha, "culprit_short": sha[:7], "culprit_service": "checkout",
              "components": [], "onset": "2026-04-22T14:31:18Z", "degraded_at": "2026-04-22T14:31:18Z"}
    return finish(sc, split, sc.prompt, answer, files)


def finish(sc: Scenario, split: str, prompt: str, answer: dict, files: dict[str, bytes]) -> dict[str, bytes]:
    log = files["fixtures/app.log"]
    case = {"id": sc.id, "family": sc.family, "split": split, "prompt": prompt,
            "tags": [sc.family, split, *sc.extra_tags],
            "log_lines": log.count(b"\n"), "log_sha256": hashlib.sha256(log).hexdigest()}
    files["case.json"] = (json.dumps(case, indent=2) + "\n").encode()
    files["answer.json"] = (json.dumps({"case_id": sc.id, "family": sc.family, **answer}, indent=2) + "\n").encode()
    return files


def write(sc: Scenario, split: str, root: Path = CASES_DIR) -> Path:
    files = build(sc, split)
    case_dir = root / sc.id
    if case_dir.exists():
        shutil.rmtree(case_dir)
    for rel, data in sorted(files.items()):
        p = case_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    return case_dir


def main(argv: list[str]) -> None:
    from specs import SPECS, split_of
    chosen = [sc for sc in SPECS if not argv or sc.id in argv]
    if argv and len(chosen) != len(argv):
        raise SystemExit(f"unknown case id(s): {sorted(set(argv) - {sc.id for sc in chosen})}")
    print(f"{'case':18s} {'family':17s} {'split':6s} {'lines':>7s}  prompt")
    for sc in chosen:
        d = write(sc, split_of(sc))
        case = json.loads((d / "case.json").read_text())
        print(f"{sc.id:18s} {sc.family:17s} {case['split']:6s} {case['log_lines']:7,d}  {case['prompt']}")
    print(f"wrote {len(chosen)} case(s) to {CASES_DIR.relative_to(WORKSHOP)}/")


if __name__ == "__main__":
    main(sys.argv[1:])
