# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0
"""
The eval case set: Level 0/1 variants of the original Incident-2277 story.

Each family tests one reasoning step from the team's runbook, so a failure
points at a cause. Split is by whole family (docs/plan.md §B item 8): train
families are the only ones whose transcripts a hillclimb analyzer may read; test
families are held out; the regression family is a val slice that guards
against breaking the original story but isn't scored as generalization.
"""
from __future__ import annotations

import hashlib

from scenario import Deploy, Incident, Scenario, at

SPLITS = {
    "regression": "val",
    "shifted": "train",
    "rolled_back": "train",
    "innocent_message": "train",
    "decoy": "test",
    "no_culprit": "test",
}

D = "2026-04-22"
D2 = "2026-04-23"
A, B, C, DV, E, F, G = (f"{n}@shop.io" for n in ("alice", "bob", "carol", "dave", "erin", "frank", "grace"))


def split_of(sc: Scenario) -> str:
    return SPLITS[sc.family]


def _full(short: str) -> str:
    """Extend a known 7-char sha to 40 hex chars, deterministically."""
    return short + hashlib.sha1(short.encode()).hexdigest()[:33]


# The original four deploys, same shas, times and messages as data/deploys.json.
ORIGINAL_DEPLOYS = (
    Deploy("cart", at(D, "09:14:05"), "bump lodash to 4.17.22", DV, "harmless:dep_bump", sha=_full("e21b6c9")),
    Deploy("auth", at(D, "11:02:33"), "add rate limiting to /refresh", B, "harmless:rate_limit", sha=_full("9f1e2d4")),
    Deploy("checkout", at(D, "14:31:18"), "refactor order summary builder for readability", A, "n_plus_one",
           sha="a3f9c21e8b4d2f1a9c0e7d3b5f8a2c4e6d9b1f0a"),
    Deploy("inventory", at(D, "14:55:40"), "add SKU validation on reserve endpoint", C, "harmless:validation",
           sha=_full("7b3e8f0")),
)


def _repro(id: str, prompt: str) -> Scenario:
    """Generated reproduction of the original story (small log). Same seed -> identical fixtures."""
    return Scenario(id, "regression", seed=2277, start=at(D, "14:00:00"), deploys=ORIGINAL_DEPLOYS,
                    prompt=prompt, auth_red_herring_at=at(D, "14:15:00"))


SPECS: list[Scenario] = [
    # ── regression (val) ───────────────────────────────────────────────
    Scenario("reg-verbatim", "regression", seed=42, start=at(D, "14:00:00"), deploys=ORIGINAL_DEPLOYS,
             prompt="checkout p99 spiked ~14:32 UTC. Find the root cause.", verbatim=True,
             extra_tags=("verbatim",)),
    _repro("reg-500s", "Checkout is throwing 500s. Find the root cause."),
    _repro("reg-1440", "What happened around 14:40 UTC? Find the root cause."),
    _repro("reg-auth", "Is auth the problem? Checkout latency has been bad since ~14:32 UTC. Find the root cause."),

    # ── shifted: the culprit lands at a different time (train) ──────────
    Scenario("shift-early", "shifted", seed=101, start=at(D, "14:00:00"), auth_red_herring_at=at(D, "14:41:00"),
             deploys=(
                 Deploy("auth", at(D, "10:47:12"), "add rate limiting to /refresh", B, "harmless:rate_limit"),
                 Deploy("checkout", at(D, "14:09:42"), "refactor order summary builder for readability", A, "n_plus_one"),
                 Deploy("cart", at(D, "14:33:05"), "bump lodash to 4.17.22", DV, "harmless:dep_bump"),
             )),
    Scenario("shift-late", "shifted", seed=102, start=at(D, "14:00:00"), auth_red_herring_at=at(D, "14:15:00"),
             deploys=(
                 Deploy("inventory", at(D, "12:20:51"), "add SKU validation on reserve endpoint", C, "harmless:validation"),
                 Deploy("cart", at(D, "14:18:37"), "structured request logging", E, "harmless:log_tweak"),
                 Deploy("checkout", at(D, "14:46:05"), "refactor order summary builder for readability", F, "n_plus_one"),
             )),
    Scenario("shift-morning", "shifted", seed=103, start=at(D2, "09:00:00"), auth_red_herring_at=at(D2, "09:12:00"),
             deploys=(
                 Deploy("cart", at(D2, "05:41:19"), "bump lodash to 4.17.22", DV, "harmless:dep_bump"),
                 Deploy("auth", at(D2, "08:52:44"), "promo banner flag (off)", G, "harmless:feature_flag"),
                 Deploy("checkout", at(D2, "09:27:31"), "simplify order summary assembly", A, "n_plus_one"),
             )),

    # ── rolled_back: a deploy's status matters (train) ──────────────────
    # The culprit is a slow burn: it ships early and latency creeps up under the page
    # line, then degrades fully. Meanwhile a later deploy to the same service goes out
    # and is rolled back before the page. "Latest deploy to the paged service before the
    # page" names the rolled-back one; reading deploy status and the log does not.
    Scenario("rb-cache", "rolled_back", seed=201, start=at(D, "14:00:00"), auth_red_herring_at=at(D, "14:15:00"),
             deploys=(
                 Deploy("checkout", at(D, "14:06:20"), "refactor order summary builder for readability", A, "n_plus_one",
                        degrade_at=at(D, "14:29:30")),
                 Deploy("checkout", at(D, "14:18:10"), "temporarily disable catalog cache", C, "cache_removed",
                        status="rolled_back", rolled_back_at=at(D, "14:23:40")),
                 Deploy("inventory", at(D, "13:02:08"), "add SKU validation on reserve endpoint", E, "harmless:validation"),
             )),
    Scenario("rb-early-n1", "rolled_back", seed=202, start=at(D, "14:00:00"), auth_red_herring_at=at(D, "14:44:00"),
             deploys=(
                 Deploy("checkout", at(D, "14:03:30"), "inline order item fetch", F, "n_plus_one",
                        status="rolled_back", rolled_back_at=at(D, "14:07:00")),
                 Deploy("cart", at(D, "13:21:16"), "bump lodash to 4.17.22", DV, "harmless:dep_bump"),
                 Deploy("checkout", at(D, "14:15:40"), "tidy order summary helpers", A, "n_plus_one",
                        degrade_at=at(D, "14:38:00")),
                 Deploy("checkout", at(D, "14:33:10"), "structured request logging", E, "harmless:log_tweak",
                        status="rolled_back", rolled_back_at=at(D, "14:35:30")),
             )),
    Scenario("rb-wrong-rollback", "rolled_back", seed=203, start=at(D, "14:00:00"), auth_red_herring_at=at(D, "14:15:00"),
             deploys=(
                 Deploy("auth", at(D, "11:30:02"), "add rate limiting to /refresh", B, "harmless:rate_limit"),
                 Deploy("checkout", at(D, "14:08:45"), "refactor order summary builder for readability", A, "n_plus_one",
                        degrade_at=at(D, "14:30:20")),
                 Deploy("checkout", at(D, "14:26:00"), "rewrite order summary query path", G, "harmless:log_tweak",
                        status="rolled_back", rolled_back_at=at(D, "14:29:10")),
             )),

    # ── innocent_message: the culprit's message sounds harmless (train) ─
    # A harmless deploy to the same service, with a message that sounds guilty, lands in
    # the same minute right after the culprit. Per-minute metrics can't separate them, so
    # the agent has to read the diffs (or the log to the second).
    Scenario("im-naming", "innocent_message", seed=301, start=at(D, "14:00:00"), auth_red_herring_at=at(D, "14:15:00"),
             deploys=(
                 Deploy("cart", at(D, "13:10:44"), "perf: rework query layer for cart lookups", E, "harmless:add_index"),
                 Deploy("checkout", at(D, "14:28:05"), "tidy up summary builder naming", A, "n_plus_one"),
                 Deploy("checkout", at(D, "14:28:50"), "perf: rework query layer for order lookups", G, "harmless:add_index"),
                 Deploy("inventory", at(D, "14:51:09"), "add SKU validation on reserve endpoint", C, "harmless:validation"),
             )),
    Scenario("im-docs", "innocent_message", seed=302, start=at(D, "14:00:00"), auth_red_herring_at=at(D, "14:37:00"),
             deploys=(
                 Deploy("inventory", at(D, "14:02:26"), "fix: remove N+1 in stock check", F, "harmless:add_index"),
                 Deploy("checkout", at(D, "14:13:10"), "docs: clarify order summary comments", G, "n_plus_one"),
                 Deploy("checkout", at(D, "14:13:48"), "fix: batch order item lookups", E, "harmless:add_index"),
                 Deploy("auth", at(D, "12:44:31"), "add rate limiting to /refresh", B, "harmless:rate_limit"),
             )),
    Scenario("im-chore", "innocent_message", seed=303, start=at(D, "14:00:00"), auth_red_herring_at=at(D, "14:15:00"),
             deploys=(
                 Deploy("auth", at(D, "12:00:17"), "perf: batch token refresh queries", B, "harmless:retry_jitter"),
                 Deploy("checkout", at(D, "14:35:05"), "chore: small cleanup", DV, "n_plus_one"),
                 Deploy("checkout", at(D, "14:35:41"), "perf: add backoff to order query retries", F, "harmless:retry_jitter"),
                 Deploy("cart", at(D, "14:21:48"), "bump lodash to 4.17.22", DV, "harmless:dep_bump"),
             )),

    # ── decoy: another service deploys within ~2 min of the culprit (test) ─
    Scenario("dc-before", "decoy", seed=401, start=at(D, "14:00:00"), auth_red_herring_at=at(D, "14:15:00"),
             deploys=(
                 Deploy("cart", at(D, "14:21:05"), "add exponential backoff to pricing client", E, "harmless:retry_jitter"),
                 Deploy("checkout", at(D, "14:22:30"), "refactor order summary builder for readability", A, "n_plus_one"),
                 Deploy("auth", at(D, "11:58:40"), "add rate limiting to /refresh", B, "harmless:rate_limit"),
             )),
    # dc-after's decoy is a real (minor) regression, so it must not be a defensible answer:
    # it deploys at 14:39:40, after checkout p99 is already > 500 ms in the 14:38 minute;
    # inventory's own p99 stays under the 500 ms page line; and checkout's log never
    # mentions inventory. Pinned by tests/test_generator.py::test_decoy_cannot_explain_the_page.
    Scenario("dc-after", "decoy", seed=402, start=at(D, "14:00:00"), auth_red_herring_at=at(D, "14:15:00"),
             deploys=(
                 Deploy("checkout", at(D, "14:38:10"), "refactor order summary builder for readability", A, "n_plus_one"),
                 Deploy("inventory", at(D, "14:39:40"), "temporarily disable catalog cache", C, "cache_removed"),
                 Deploy("cart", at(D, "10:05:12"), "bump lodash to 4.17.22", DV, "harmless:dep_bump"),
             )),
    Scenario("dc-cart", "decoy", seed=403, start=at(D, "14:00:00"), affected_service="cart",
             auth_red_herring_at=at(D, "14:33:00"),
             deploys=(
                 Deploy("checkout", at(D, "14:15:30"), "rewrite order summary query path", G, "harmless:add_index"),
                 Deploy("cart", at(D, "14:16:45"), "split price lookup into a loop for clarity", F, "n_plus_one"),
                 Deploy("inventory", at(D, "12:31:58"), "add SKU validation on reserve endpoint", C, "harmless:validation"),
             )),
    Scenario("dc-cart-late", "decoy", seed=404, start=at(D, "14:00:00"), affected_service="cart",
             auth_red_herring_at=at(D, "14:15:00"),
             deploys=(
                 Deploy("checkout", at(D, "14:41:00"), "structured request logging", E, "harmless:log_tweak"),
                 Deploy("cart", at(D, "14:43:20"), "price cart lines individually", A, "n_plus_one"),
                 Deploy("auth", at(D, "14:44:50"), "add rate limiting to /refresh", B, "harmless:rate_limit"),
             )),

    # ── no_culprit: nothing deployed lines up (test) ────────────────────
    Scenario("nc-db-1", "no_culprit", seed=501, start=at(D, "14:00:00"), auth_red_herring_at=at(D, "14:15:00"),
             incident=Incident("db_primary", at(D, "14:23:00")),
             deploys=(
                 Deploy("cart", at(D, "09:14:05"), "bump lodash to 4.17.22", DV, "harmless:dep_bump"),
                 Deploy("auth", at(D, "11:02:33"), "add rate limiting to /refresh", B, "harmless:rate_limit"),
                 Deploy("checkout", at(D, "13:20:47"), "refactor order summary builder for readability", A, "harmless:log_tweak"),
                 Deploy("inventory", at(D, "14:52:13"), "add SKU validation on reserve endpoint", C, "harmless:validation"),
             )),
    Scenario("nc-db-2", "no_culprit", seed=502, start=at(D, "14:00:00"), auth_red_herring_at=at(D, "14:09:00"),
             incident=Incident("db_primary", at(D, "14:36:00")),
             deploys=(
                 Deploy("checkout", at(D, "13:48:22"), "perf: rework query layer for order lookups", G, "harmless:add_index"),
                 Deploy("cart", at(D, "12:05:09"), "promo banner flag (off)", E, "harmless:feature_flag"),
             )),
    Scenario("nc-stripe-1", "no_culprit", seed=503, start=at(D, "14:00:00"), auth_red_herring_at=at(D, "14:15:00"),
             incident=Incident("stripe_api", at(D, "14:19:30")),
             deploys=(
                 Deploy("checkout", at(D, "12:40:31"), "add exponential backoff to payment client", F, "harmless:retry_jitter"),
                 Deploy("inventory", at(D, "13:33:57"), "add SKU validation on reserve endpoint", C, "harmless:validation"),
                 Deploy("cart", at(D, "14:47:02"), "bump lodash to 4.17.22", DV, "harmless:dep_bump"),
             )),
    Scenario("nc-stripe-2", "no_culprit", seed=504, start=at(D, "14:00:00"), auth_red_herring_at=at(D, "14:30:00"),
             incident=Incident("stripe_api", at(D, "14:41:10")),
             deploys=(
                 Deploy("auth", at(D, "10:12:40"), "add rate limiting to /refresh", B, "harmless:rate_limit"),
                 Deploy("checkout", at(D, "13:05:18"), "structured request logging", A, "harmless:log_tweak"),
             )),
]
