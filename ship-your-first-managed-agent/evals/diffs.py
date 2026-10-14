# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0
"""
Unified-diff templates for generated deploys.

`n_plus_one` is the original workshop diff (data/diff.txt), parameterized by
service. `cache_removed` is the runbook's second "burned us" pattern. The
`harmless:*` templates are plausible changes that don't degrade anything; some
deliberately *look* risky (a new index, a retry change) so the agent has to read
the diff rather than pattern-match the commit message.
"""
from __future__ import annotations

from datetime import datetime, timedelta

# Per-service code context for the N+1 template, and the SQL the generator logs.
N1 = {
    "checkout": dict(
        path="checkout/handlers.py", cls="CheckoutSummaryHandler", fn="build_summary",
        parent="Order", child="OrderItem", fk="order_id", table="order_items",
        filt='user_id=user_id, status="open"', loopvar="order", key="user_id",
    ),
    "cart": dict(
        path="cart/pricing.py", cls="CartPricingHandler", fn="price_cart",
        parent="CartLine", child="SkuPrice", fk="sku_id", table="sku_prices",
        filt="cart_id=cart_id", loopvar="line", key="cart_id",
    ),
    "inventory": dict(
        path="inventory/reserve.py", cls="ReserveHandler", fn="check_stock",
        parent="ReserveLine", child="StockLevel", fk="sku_id", table="stock_levels",
        filt="reservation_id=reservation_id", loopvar="line", key="reservation_id",
    ),
}


def per_row_sql(service: str) -> str:
    c = N1[service]
    return f'SELECT * FROM {c["table"]} WHERE {c["fk"]} = ?'


def batched_sql(service: str) -> str:
    c = N1[service]
    return f'SELECT * FROM {c["table"]} WHERE {c["fk"]} IN (?)'


def _header(sha: str, author: str, email: str, when: datetime, summary: str, body: str) -> str:
    date = f"{when:%a %b} {when.day} {when:%H:%M:%S %Y} +0000"  # git style: day not zero-padded
    body_txt = "".join(f"    {line}\n" if line else "\n" for line in body.split("\n"))
    return f"commit {sha}\nAuthor: {author} <{email}>\nDate:   {date}\n\n    {summary}\n\n{body_txt}\n"


def _n_plus_one(service: str) -> tuple[str, str]:
    c = N1[service]
    v = c["loopvar"]
    body = (
        "The old list comprehension was getting hard to follow. Split it into\n"
        "an explicit loop so the per-row enrichment logic is clearer."
    )
    diff = f'''diff --git a/{c["path"]} b/{c["path"]}
index 8f3a2b1..c4d9e7f 100644
--- a/{c["path"]}
+++ b/{c["path"]}
@@ -41,22 +41,24 @@ class {c["cls"]}(BaseHandler):
     def {c["fn"]}(self, {c["key"]}: str) -> dict:
         rows = {c["parent"]}.objects.filter({c["filt"]})
-        ids = [r.{c["fk"]} for r in rows]
-
-        # Single query, then group in memory
-        all_items = {c["child"]}.objects.filter({c["fk"]}__in=ids)
-        by_id = defaultdict(list)
-        for item in all_items:
-            by_id[item.{c["fk"]}].append(item)
-
-        summaries = [
-            self._summarize(r, by_id[r.{c["fk"]}])
-            for r in rows
-        ]
+
+        summaries = []
+        for {v} in rows:
+            # fetch the items for this row
+            items = {c["child"]}.objects.filter({c["fk"]}={v}.{c["fk"]})
+            log.debug(
+                'db_query sql="{per_row_sql(service)}" params=[%s]',
+                {v}.{c["fk"]},
+            )
+            summaries.append(self._summarize({v}, list(items)))
+
         return {{
             "{c["key"]}": {c["key"]},
             "rows": summaries,
             "total_cents": sum(s["subtotal_cents"] for s in summaries),
         }}
'''
    return body, diff


def _cache_removed(service: str) -> tuple[str, str]:
    path = f"{service}/catalog.py"
    body = "Disabling the cache while we chase a stale-price report. Will restore\nonce the TTL bug is understood."
    diff = f'''diff --git a/{path} b/{path}
index 1d2e3f4..5a6b7c8 100644
--- a/{path}
+++ b/{path}
@@ -18,7 +18,7 @@ from .cache import cached


-@cached(ttl=60)
+# @cached(ttl=60)  # temporarily disabled, see INC-2241
 def load_catalog_page(page: int) -> list[dict]:
     return [serialize(p) for p in Product.objects.page(page)]
'''
    return body, diff


def _dep_bump(service: str) -> tuple[str, str]:
    body = "Routine patch bump from the weekly dependency PR."
    diff = f'''diff --git a/{service}/package.json b/{service}/package.json
index 3c4d5e6..7f8a9b0 100644
--- a/{service}/package.json
+++ b/{service}/package.json
@@ -12,7 +12,7 @@
     "express": "4.19.2",
-    "lodash": "4.17.21",
+    "lodash": "4.17.22",
     "pino": "8.17.2",
'''
    return body, diff


def _rate_limit(service: str) -> tuple[str, str]:
    body = "Caps abusive refresh loops from misbehaving clients."
    diff = f'''diff --git a/{service}/routes.py b/{service}/routes.py
index 2b3c4d5..6e7f8a9 100644
--- a/{service}/routes.py
+++ b/{service}/routes.py
@@ -30,6 +30,7 @@ def register(app):
-    app.post("/refresh")(refresh_token)
+    app.post("/refresh")(rate_limited(per_minute=120)(refresh_token))
     app.post("/logout")(logout)
'''
    return body, diff


def _validation(service: str) -> tuple[str, str]:
    body = "Reject malformed SKUs at the edge instead of deep in the handler."
    diff = f'''diff --git a/{service}/validators.py b/{service}/validators.py
index 4a5b6c7..8d9e0f1 100644
--- a/{service}/validators.py
+++ b/{service}/validators.py
@@ -9,4 +9,8 @@ import re
 SKU_RE = re.compile(r"^[A-Z]{{3}}-[0-9]{{6}}$")
+
+
+def validate_sku(sku: str) -> None:
+    if not SKU_RE.match(sku):
+        raise ValidationError(f"bad sku: {{sku}}")
'''
    return body, diff


def _log_tweak(service: str) -> tuple[str, str]:
    body = "Structured field instead of string interpolation; easier to query."
    diff = f'''diff --git a/{service}/middleware.py b/{service}/middleware.py
index 5b6c7d8..9e0f1a2 100644
--- a/{service}/middleware.py
+++ b/{service}/middleware.py
@@ -22,5 +22,5 @@ class RequestLogMiddleware:
     def after(self, req, resp):
-        log.info(f"request_end status={{resp.status}} path={{req.path}}")
+        log.info("request_end", status=resp.status, path=req.path)
'''
    return body, diff


def _feature_flag(service: str) -> tuple[str, str]:
    body = "New banner behind a flag; default off until marketing signs off."
    diff = f'''diff --git a/{service}/flags.py b/{service}/flags.py
index 6c7d8e9..0f1a2b3 100644
--- a/{service}/flags.py
+++ b/{service}/flags.py
@@ -4,3 +4,4 @@ FLAGS = {{
     "new_checkout_copy": False,
+    "promo_banner_v2": False,
 }}
'''
    return body, diff


def _add_index(service: str) -> tuple[str, str]:
    table = N1.get(service, {}).get("table", f"{service}_events")
    body = "Adds a covering index for the lookup path. Built CONCURRENTLY, no lock."
    diff = f'''diff --git a/{service}/migrations/0042_lookup_index.py b/{service}/migrations/0042_lookup_index.py
new file mode 100644
index 0000000..1b2c3d4
--- /dev/null
+++ b/{service}/migrations/0042_lookup_index.py
@@ -0,0 +1,9 @@
+from django.contrib.postgres.operations import AddIndexConcurrently
+from django.db import migrations, models
+
+
+class Migration(migrations.Migration):
+    atomic = False
+    operations = [
+        AddIndexConcurrently("{table}", models.Index(fields=["created_at"], name="{table}_created_idx")),
+    ]
'''
    return body, diff


def _retry_jitter(service: str) -> tuple[str, str]:
    body = "Adds exponential backoff with jitter to the client retry loop."
    diff = f'''diff --git a/{service}/client.py b/{service}/client.py
index 7d8e9f0..1a2b3c4 100644
--- a/{service}/client.py
+++ b/{service}/client.py
@@ -15,6 +15,7 @@ def call_with_retry(fn, attempts=3):
     for i in range(attempts):
         try:
             return fn()
         except TransientError:
-            continue
+            time.sleep(min(2 ** i, 8) * random.uniform(0.5, 1.0))
+            continue
     raise RetriesExhausted()
'''
    return body, diff


TEMPLATES = {
    "n_plus_one": _n_plus_one,
    "cache_removed": _cache_removed,
    "harmless:dep_bump": _dep_bump,
    "harmless:rate_limit": _rate_limit,
    "harmless:validation": _validation,
    "harmless:log_tweak": _log_tweak,
    "harmless:feature_flag": _feature_flag,
    "harmless:add_index": _add_index,
    "harmless:retry_jitter": _retry_jitter,
}


def render(kind: str, service: str, sha: str, author_email: str, deployed_at: datetime, summary: str) -> str:
    """A full `git show`-style diff for one deploy. Authored ~2.5 min before it deployed."""
    body, diff = TEMPLATES[kind](service)
    name = author_email.split("@")[0].replace(".", " ").title()
    return _header(sha, name, author_email, deployed_at - timedelta(seconds=147), summary, body) + diff
