# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0
"""
A scenario spec: everything generate.py needs to write one eval case.

A case is a deploy history plus at most one active cause. The cause is either a
deploy whose diff degrades a service (the culprit) or a non-deploy incident on a
shared component (`db-primary`, `stripe-api`). The log, metrics, deploys and
diffs are all derived from the same spec in one pass, so they always agree.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

UTC = timezone.utc
SERVICES = ("checkout", "cart", "auth", "inventory")
DB_SERVICES = ("checkout", "cart", "inventory")  # services that talk to db-primary

# Diff kinds that degrade the service while the deploy is live. Everything else
# is "harmless:<template>" (see diffs.py).
FAULT_KINDS = ("n_plus_one", "cache_removed")

# Seconds from an N+1 deploy to DB pool exhaustion. 522 s reproduces the
# original story exactly: deploy 14:31:18, pool exhausted 14:40:00.
N_PLUS_ONE_EXHAUST_S = 522
DB_PRIMARY_EXHAUST_S = 360


def at(day: str, hms: str) -> datetime:
    """at("2026-04-22", "14:31:18") -> aware UTC datetime."""
    return datetime.fromisoformat(f"{day}T{hms}+00:00")


@dataclass(frozen=True)
class Deploy:
    service: str
    ts: datetime
    summary: str
    author: str
    diff_kind: str  # "n_plus_one" | "cache_removed" | "harmless:<template>"
    status: str = "success"  # "success" | "rolled_back"
    rolled_back_at: datetime | None = None
    sha: str | None = None  # full 40-hex; None -> derived from the case id
    # Slow burn (N+1 only): the per-row loop ships at `ts` but stays cheap while row counts
    # are small; latency creeps up (always under the 500 ms page line) until `degrade_at`,
    # then degrades fully. None = degrades at once, as in the original incident.
    degrade_at: datetime | None = None

    @property
    def degraded_from(self) -> datetime:
        return self.degrade_at or self.ts

    def live_at(self, t: datetime) -> bool:
        return t >= self.ts and (self.rolled_back_at is None or t < self.rolled_back_at)


@dataclass(frozen=True)
class Incident:
    """A non-deploy cause. kind: "db_primary" | "stripe_api"."""
    kind: str
    start: datetime


@dataclass(frozen=True)
class Scenario:
    id: str
    family: str
    seed: int
    start: datetime
    deploys: tuple[Deploy, ...]
    affected_service: str = "checkout"
    incident: Incident | None = None
    prompt: str | None = None  # None -> "<svc> p99 spiked ~HH:MM UTC. Find the root cause." (alert time)
    auth_red_herring_at: datetime | None = None
    minutes: int = 60
    req_per_s: float = 0.5  # sampled traffic; keeps logs ~5-11k lines
    verbatim: bool = False  # copy the original workshop fixtures instead of generating
    extra_tags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def end(self) -> datetime:
        return self.start + timedelta(minutes=self.minutes)

    def culprit(self) -> Deploy | None:
        """The fault deploy still live when the incident window ends, if any."""
        live = [d for d in self.deploys if d.diff_kind == "n_plus_one" and d.live_at(self.end)]
        if self.incident is not None:
            assert not live, f"{self.id}: both an incident and a live N+1 deploy"
            return None
        assert len(live) == 1, f"{self.id}: expected exactly one live N+1 deploy, got {len(live)}"
        return live[0]
