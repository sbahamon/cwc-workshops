# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0
"""
Headless eval runner for the SRE agent on Claude Managed Agents.

    uv run python run.py --flow hillclimb/ladder --variant baseline --model claude-opus-4-8 --dry-run
    uv run python run.py --flow hillclimb/ladder --variant v1 --model claude-sonnet-5-5 --effort low

Per (case, rep): a fresh session pinned to an agent version, with that case's
log mounted and a hard budget; the three custom tools are answered locally from
the case's fixtures; the final reply is graded by graders.py. Output follows the
claude-api skill's eval contract (shared/evals/build-eval.md Step 3):

    <flow>/<variant>/results.jsonl         one row per (case, rep), appended as each finishes
    <flow>/<variant>/errors.jsonl          failed attempts (never scored), append-only
    <flow>/<variant>/traces/<id>_rep<k>.json   the conversation, as {role, content} turns
    <flow>/<variant>/raw/<id>_rep<k>.jsonl     every event, for re-grading without a re-run
    <flow>/<variant>/summary.json

Guards: a harness-integrity gate (exit 2 until a human runs --approve-harness),
the project spend cap (refuses runs whose projection would cross it), a per-case
wall-clock ceiling, jittered backoff with counted retries, an echoed-model check,
and idempotent resume at (case, rep).

Agents, the environment, the runbook skill and uploaded logs are created once and
cached in .registry.json (workspace-specific; gitignored).
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import json
import math
import os
import random
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

EVALS = Path(__file__).resolve().parent
WORKSHOP = EVALS.parent
sys.path.insert(0, str(WORKSHOP))

import config  # noqa: E402  (the workshop's single source for SYSTEM / TOOLS)
from cases import Case, load_answer, load_cases  # noqa: E402
from graders import grade  # noqa: E402
from spend import CAP_USD, total_spend  # noqa: E402
from tools import CaseTools  # noqa: E402

REGISTRY = EVALS / ".registry.json"
LADDER_STATE = EVALS / "hillclimb" / "ladder" / "_state.json"
DEFAULT_SYSTEM_FILE = EVALS / "prompts" / "system.md"
RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504, 529}


# ── small utilities ─────────────────────────────────────────────────────
def sha256(data: bytes | str) -> str:
    return hashlib.sha256(data.encode() if isinstance(data, str) else data).hexdigest()


def text_of(content) -> str:
    return "".join(getattr(b, "text", "") or "" for b in (content or []) if getattr(b, "type", None) == "text")


def rel(p: Path) -> str:
    try:
        return p.relative_to(EVALS).as_posix()
    except ValueError:
        return str(p)


def wald(p: float, n: int) -> float:
    return 1.96 * math.sqrt(p * (1 - p) / n) if n else float("nan")


class Writer:
    """Thread-safe append-only JSONL plus per-attempt files."""

    def __init__(self, vdir: Path):
        self.vdir = vdir
        self.lock = threading.Lock()
        (vdir / "traces").mkdir(parents=True, exist_ok=True)
        (vdir / "raw").mkdir(parents=True, exist_ok=True)

    def append(self, name: str, row: dict) -> None:
        with self.lock, open(self.vdir / name, "a") as f:
            f.write(json.dumps(row, separators=(",", ":"), default=str) + "\n")

    def put(self, rel: str, text: str) -> None:
        p = self.vdir / rel
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(text)
        tmp.replace(p)


def done_keys(vdir: Path) -> set[tuple[str, int]]:
    p = vdir / "results.jsonl"
    if not p.exists():
        return set()
    return {(r["prompt_id"], r["rep"]) for r in map(json.loads, filter(str.strip, p.read_text().splitlines()))}


# ── harness-integrity gate ──────────────────────────────────────────────
def harness_sha(state: dict) -> tuple[str, list[str]]:
    paths = ["run.py", "uv.lock", *state.get("harness_paths", [])]
    h = hashlib.sha256()
    for rel in paths:
        p = (EVALS / rel).resolve()
        h.update(rel.encode() + b"\0" + (p.read_bytes() if p.exists() else b"<missing>") + b"\0")
    return h.hexdigest(), paths


def check_harness(state_path: Path, state: dict, approve: bool) -> bool:
    sha, paths = harness_sha(state)
    if state.get("harness_sha") == sha:
        return True
    if approve:
        state["harness_sha"] = sha
        state_path.write_text(json.dumps(state, indent=2) + "\n")
        print(f"harness approved: sha {sha[:12]} over {len(paths)} files ({', '.join(paths)})")
        return True
    was = state.get("harness_sha")
    print(f"harness changed since last approval ({(was or 'never approved')[:12]} -> {sha[:12]}).\n"
          f"Review the diff of: {', '.join(paths)}\nthen a human runs the same command with --approve-harness.",
          file=sys.stderr)
    return False


# ── run configuration ───────────────────────────────────────────────────
@dataclass(frozen=True)
class AgentCfg:
    model: str
    effort: str | None
    system: str
    tools_json: str = field(default_factory=lambda: json.dumps(config.TOOLS, sort_keys=True))

    @property
    def model_param(self):
        return config.model_param(self.model, self.effort)

    def key(self, skill_id: str, skill_version: str) -> str:
        return sha256(json.dumps([self.model, self.effort, self.system, self.tools_json, skill_id, skill_version]))


@dataclass
class Attempt:
    """What one session produced. Either `final_text` (scorable) or `error_class`."""
    session_id: str | None = None
    events: list = field(default_factory=list)
    turns: list = field(default_factory=list)
    final_text: str = ""
    stop_reason: str | None = None
    usage: dict = field(default_factory=lambda: dict(input_tokens=0, output_tokens=0,
                                                     cache_read_input_tokens=0, cache_creation_input_tokens=0))
    model: str | None = None
    effort_echoed: str | None = None
    list_cost_usd: float | None = None
    active_seconds: float | None = None
    latency_s: float | None = None
    sandbox_calls: int = 0
    custom_calls: int = 0
    deploys_before_first_sandbox_call: bool | None = None
    session_usage_events: int = 0
    retries: int = 0
    error_class: str | None = None
    error: str | None = None


def drive(events, send, tools: CaseTools, att: Attempt, cancelled: threading.Event) -> None:
    """Consume a session's event stream until the turn ends. Shared by live and fake backends.

    `send(events)` posts events back to the session (custom tool results)."""
    for ev in events:
        if cancelled.is_set():
            break
        att.events.append(ev)
        t = ev.type
        if t == "agent.message":
            txt = text_of(ev.content)
            # Separate messages with a newline so a later one can't land on the root-cause line.
            sep = "\n" if att.final_text and not att.final_text.endswith("\n") else ""
            att.final_text += sep + txt
            if att.turns and att.turns[-1]["role"] == "assistant":
                prev = att.turns[-1]["content"]
                att.turns[-1]["content"] += ("\n" if prev and not prev.endswith("\n") else "") + txt
            else:
                att.turns.append({"role": "assistant", "content": txt})
        elif t == "agent.tool_use":
            att.sandbox_calls += 1
            if att.deploys_before_first_sandbox_call is None:
                att.deploys_before_first_sandbox_call = False
            att.turns.append({"role": "tool_call", "name": ev.name, "content": json.dumps(ev.input, indent=2)})
        elif t == "agent.tool_result":
            att.turns.append({"role": "tool_result", "name": "sandbox", "content": text_of(ev.content)})
        elif t == "agent.custom_tool_use":
            att.custom_calls += 1
            if ev.name == "get_recent_deploys" and att.deploys_before_first_sandbox_call is None:
                att.deploys_before_first_sandbox_call = True
            result = tools.handle(ev.name, dict(ev.input or {}))
            att.turns.append({"role": "tool_call", "name": ev.name, "content": json.dumps(ev.input, indent=2)})
            att.turns.append({"role": "tool_result", "name": ev.name, "content": result})
            send([{"type": "user.custom_tool_result", "custom_tool_use_id": ev.id,
                   "content": [{"type": "text", "text": result}]}])
        elif t == "span.model_request_end":
            u = ev.model_usage
            for k in att.usage:
                att.usage[k] += int(getattr(u, k, 0) or 0)
        elif t == "session.usage":
            att.session_usage_events += 1
        elif t == "session.error":
            att.error = str(getattr(ev, "error", ev))[:500]
        elif t == "session.status_idle":
            reason = ev.stop_reason.type
            if reason == "requires_action":
                continue  # waiting on a tool result we have sent or are sending
            att.stop_reason = reason
            if reason == "budget_reached":
                att.error_class = "budget"
            elif reason != "end_turn":
                att.error_class = "serving_error"
            return
        elif t == "session.status_terminated":
            att.stop_reason = "terminated"
            att.error_class = att.error_class or "serving_error"
            return
    if not cancelled.is_set() and att.stop_reason is None:
        att.error_class, att.error = "harness_error", "event stream ended before the turn did"


# ── backends ────────────────────────────────────────────────────────────
def with_retries(fn, att: Attempt, attempts: int = 5):
    import anthropic
    for i in range(attempts):
        try:
            return fn()
        except (anthropic.APIConnectionError, anthropic.APIStatusError) as e:
            status = getattr(e, "status_code", None)
            if isinstance(e, anthropic.APIStatusError) and status not in RETRYABLE_STATUS:
                raise
            if i == attempts - 1:
                raise
            att.retries += 1
            time.sleep(min(30.0, 2 ** i) * random.uniform(0.5, 1.0))


class LiveBackend:
    def __init__(self, budget_cents: int):
        import anthropic
        from dotenv import load_dotenv
        load_dotenv(WORKSHOP / ".env")
        ws = os.environ.get("ANTHROPIC_WORKSPACE_ID")
        self.workspace = ws or "default"
        self.client = anthropic.Anthropic(max_retries=0,
                                          default_headers={"anthropic-workspace-id": ws} if ws else None)
        self.budget_cents = budget_cents
        self.lock = threading.Lock()
        self.reg = json.loads(REGISTRY.read_text()) if REGISTRY.exists() else {}

    def _save(self) -> None:
        tmp = REGISTRY.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.reg, indent=2) + "\n")
        tmp.replace(REGISTRY)

    # Control-plane resources: created once, reused by every session.
    def environment(self) -> str:
        cfg = {"type": "cloud", "networking": {"type": "limited"}}  # no allowed_hosts: no egress, no web tools
        key = sha256(json.dumps(cfg, sort_keys=True))
        with self.lock:
            env = self.reg.get("environment")
            if env and env["config_sha"] == key:
                return env["id"]
            e = self.client.beta.environments.create(name=f"sre-eval-{key[:6]}-{uuid.uuid4().hex[:4]}", config=cfg)
            self.reg["environment"] = {"id": e.id, "config_sha": key, "config": cfg}
            self._save()
            return e.id

    def skill(self) -> tuple[str, str]:
        from anthropic.lib import files_from_dir
        runbook = config.RUNBOOK_DIR
        key = sha256(b"".join(p.read_bytes() for p in sorted(runbook.rglob("*")) if p.is_file()))
        with self.lock:
            sk = self.reg.get("skill")
            if sk and sk["runbook_sha"] == key:
                return sk["id"], sk["version"]
            s = self.client.beta.skills.create(
                display_name=f"Incident Triage Runbook eval {key[:6]}-{uuid.uuid4().hex[:4]}",
                files=files_from_dir(runbook))
            self.reg["skill"] = {"id": s.id, "version": s.latest_version_id, "runbook_sha": key}
            self._save()
            return s.id, s.latest_version_id

    def agent(self, cfg: AgentCfg) -> dict:
        skill_id, skill_version = self.skill()
        key = cfg.key(skill_id, skill_version)
        with self.lock:
            a = self.reg.setdefault("agents", {}).get(key)
            if a:
                return {"type": "agent", "id": a["id"], "version": a["version"]}
            ag = self.client.beta.agents.create(
                name=f"SRE Agent eval {cfg.model} {cfg.effort or 'default'} {key[:6]}",
                model=cfg.model_param, system=cfg.system, tools=config.TOOLS,
                skills=[{"type": "custom", "skill_id": skill_id, "version": skill_version}],
                metadata={"lab": "make-it-cheap", "system_sha": sha256(cfg.system)[:16]})
            self.reg["agents"][key] = {"id": ag.id, "version": ag.version, "model": cfg.model,
                                       "effort": cfg.effort, "system_sha": sha256(cfg.system)[:16]}
            self._save()
            return {"type": "agent", "id": ag.id, "version": ag.version}

    def log_file(self, case: Case) -> str:
        with self.lock:
            fid = self.reg.setdefault("files", {}).get(case.log_sha256)
            if fid:
                return fid
        with open(case.dir / "fixtures" / "app.log", "rb") as f:
            fid = self.client.beta.files.upload(file=f).id  # same call as agent_complete.upload_log
        with self.lock:
            self.reg["files"][case.log_sha256] = fid
            self._save()
        return fid

    def setup(self, cfg: AgentCfg, cases: list[Case]) -> None:
        self.environment()
        self.agent(cfg)
        for c in cases:
            self.log_file(c)

    def run(self, case: Case, rep: int, cfg: AgentCfg, meta: dict, timeout_s: float) -> Attempt:
        import anthropic
        att = Attempt()
        tools = CaseTools(case.dir)
        cancelled = threading.Event()
        c = self.client
        try:
            agent_ref = self.agent(cfg)
            session = with_retries(lambda: c.beta.sessions.create(
                agent=agent_ref, environment_id=self.environment(),
                resources=[{"type": "file", "file_id": self.log_file(case), "mount_path": "app.log"}],
                budget={"type": "limit", "max_list_cost": {"amount": str(self.budget_cents), "currency": "USD"}},
                title=f"eval {meta['variant']} {case.id} rep{rep}",
                metadata={"case": case.id, "rep": str(rep), "variant": meta["variant"], "flow": meta["flow"]}), att)
            att.session_id = session.id
            t0 = time.monotonic()
            with c.beta.sessions.events.stream(session.id) as stream:
                def on_timeout():
                    cancelled.set()
                    att.error_class, att.error = "timeout", f"wall-clock ceiling {timeout_s:.0f}s"
                    try:
                        c.beta.sessions.events.send(session.id, events=[{"type": "user.interrupt"}])
                    finally:
                        stream.close()
                watchdog = threading.Timer(timeout_s, on_timeout)
                watchdog.daemon = True
                watchdog.start()
                try:
                    with_retries(lambda: c.beta.sessions.events.send(session.id, events=[
                        {"type": "user.message", "content": [{"type": "text", "text": case.prompt}]}]), att)
                    drive(stream, lambda evs: with_retries(lambda: c.beta.sessions.events.send(session.id, events=evs), att),
                          tools, att, cancelled)
                except Exception as e:  # stream closed by the watchdog, or a transport failure
                    if not cancelled.is_set():
                        att.error_class, att.error = "harness_error", f"{type(e).__name__}: {e}"[:500]
                finally:
                    watchdog.cancel()
            att.latency_s = round(time.monotonic() - t0, 2)
        except anthropic.APIStatusError as e:
            att.error_class, att.error = "serving_error", f"{e.status_code}: {e.message}"[:500]
        except Exception as e:
            att.error_class, att.error = "harness_error", f"{type(e).__name__}: {e}"[:500]
        if att.session_id:
            self._finish(att)
        return att

    def _finish(self, att: Attempt) -> None:
        """Authoritative usage, cost and echoed model from the session object; then archive."""
        try:
            s = self.client.beta.sessions.retrieve(att.session_id)
            if s.usage and s.usage.list_cost is not None:
                att.list_cost_usd = int(s.usage.list_cost.amount) / 100
            att.active_seconds = getattr(s.usage, "active_seconds", None)
            m = s.agent.model
            att.model = getattr(m, "id", m)
            eff = getattr(m, "effort", None)
            att.effort_echoed = getattr(eff, "type", eff)
            if s.status in ("running", "rescheduling"):
                self.client.beta.sessions.events.send(att.session_id, events=[{"type": "user.interrupt"}])
            self.client.beta.sessions.archive(att.session_id)
        except Exception as e:  # never lose the attempt over bookkeeping
            att.error = (att.error or "") + f" | finish: {type(e).__name__}: {e}"[:300]


class FakeBackend:
    """Offline stand-in that replays a scripted session through the same drive() loop.

    modes: oracle (answers from the key), null (empty reply), const (always a3f9c21),
           api_error (session create fails), timeout (stream stalls), budget (pauses at cap)."""

    def __init__(self, mode: str):
        self.mode = mode

    def setup(self, cfg, cases):
        pass

    def run(self, case: Case, rep: int, cfg: AgentCfg, meta: dict, timeout_s: float) -> Attempt:
        att = Attempt(session_id=f"fake_{case.id}_{rep}")
        if self.mode == "api_error":
            att.session_id, att.error_class, att.error = None, "serving_error", "529: overloaded (fake)"
            return att
        ns = SimpleNamespace
        text = {"oracle": None, "null": "", "const": "**Root cause:** `a3f9c21` — N+1 query."}.get(self.mode)
        if text is None:
            a = load_answer(case)
            text = f"Evidence above.\n\n> **Root cause:** `{a['culprit_short'] or a['components'][0]}` — mechanism."
        script = [
            ns(type="session.status_running"),
            ns(type="span.model_request_start"),
            ns(type="agent.custom_tool_use", id="cu1", name="get_recent_deploys", input={}),
            ns(type="session.status_idle", stop_reason=ns(type="requires_action")),
            ns(type="agent.tool_use", id="tu1", name="bash", input={"command": "grep -c . /mnt/session/uploads/app.log"}),
            ns(type="agent.tool_result", tool_use_id="tu1", content=[ns(type="text", text="8000")]),
            ns(type="agent.message", content=[ns(type="text", text=text)]),
            ns(type="span.model_request_end", model_usage=ns(input_tokens=12, output_tokens=345,
                                                             cache_read_input_tokens=6000, cache_creation_input_tokens=1500)),
            ns(type="session.usage"),
            ns(type="session.status_idle", stop_reason=ns(type="budget_reached" if self.mode == "budget" else "end_turn")),
        ]
        cancelled = threading.Event()

        def events():
            for ev in script:
                if self.mode == "timeout" and ev.type == "agent.message":
                    cancelled.wait(timeout_s)
                    att.error_class, att.error = "timeout", f"wall-clock ceiling {timeout_s:.0f}s"
                    cancelled.set()
                    return
                yield ev

        t0 = time.monotonic()
        drive(events(), lambda evs: None, CaseTools(case.dir), att, cancelled)
        att.latency_s = max(0.001, round(time.monotonic() - t0, 3))
        att.model, att.effort_echoed = cfg.model, cfg.effort or "default"
        att.list_cost_usd, att.active_seconds = 0.0, att.latency_s
        return att


# ── one attempt -> row or error ─────────────────────────────────────────
def record(w: Writer, case: Case, rep: int, cfg: AgentCfg, att: Attempt, meta: dict, console: str | None) -> dict:
    base_meta = {**meta, "session_id": att.session_id, "effort_requested": cfg.effort,
                 "effort_echoed": att.effort_echoed, "retries": att.retries,
                 "active_seconds": att.active_seconds, "console_url": console}
    # Served-model check: the session's echoed model (and effort, when we set one) must match.
    if att.error_class is None and att.model is not None:
        if att.model != cfg.model or (cfg.effort is not None and att.effort_echoed != cfg.effort):
            att.error_class = "served_model_mismatch"
            att.error = f"requested {cfg.model}/{cfg.effort}, session echoed {att.model}/{att.effort_echoed}"
    if att.error_class is None and att.model is None:
        att.error_class, att.error = "harness_error", "no echoed model (session not retrieved)"
    w.put(f"raw/{case.id}_rep{rep}.jsonl",
          "".join(json.dumps(e.model_dump(mode="json") if hasattr(e, "model_dump") else _plain(e), default=str) + "\n"
                  for e in att.events))
    trace = [{"role": "system", "content": cfg.system}, {"role": "user", "content": case.prompt}, *att.turns]
    w.put(f"traces/{case.id}_rep{rep}.json", json.dumps(trace, indent=2))
    common = {"prompt_id": case.id, "rep": rep, "model": att.model, "usage": att.usage,
              "list_cost_usd": att.list_cost_usd}
    if att.error_class:
        row = {**common, "class": att.error_class, "error": att.error, "retries": att.retries,
               "stop_reason": att.stop_reason, "meta": base_meta}
        w.append("errors.jsonl", row)
        return row
    row = {**common, "prompt": case.prompt, "tags": list(case.tags), "grade": grade(att.final_text, load_answer(case)),
           "status": "ok", "stop_reason": att.stop_reason, "latency_s": att.latency_s,
           "tool_calls": att.sandbox_calls + att.custom_calls,
           "out_tokens": att.usage["output_tokens"],
           "meta": {**base_meta, "sandbox_calls": att.sandbox_calls, "custom_calls": att.custom_calls,
                    "deploys_before_first_sandbox_call": att.deploys_before_first_sandbox_call,
                    "session_usage_events": att.session_usage_events}}
    if not (att.usage["output_tokens"] > 0 and row["latency_s"] and att.list_cost_usd is not None):
        raise RuntimeError(f"{case.id} rep{rep}: scorable row is missing usage, latency or cost: {common}")
    w.append("results.jsonl", row)
    return row


def _plain(e):
    if isinstance(e, SimpleNamespace):
        return {k: _plain(v) for k, v in vars(e).items()}
    if isinstance(e, list):
        return [_plain(x) for x in e]
    return e


# ── spend projection ────────────────────────────────────────────────────
def per_session_estimate(model: str, effort: str | None, budget_cents: int) -> tuple[float, str]:
    """p95 list cost of earlier real sessions with the same model and effort; else the budget."""
    from spend import counted, ledger_files
    costs = []
    for p in ledger_files():
        for r in map(json.loads, filter(str.strip, p.read_text().splitlines())):
            m = r.get("meta") or {}
            if counted(r) and r.get("model") == model and m.get("effort_requested") == effort \
                    and r.get("list_cost_usd") is not None:
                costs.append(float(r["list_cost_usd"]))
    if len(costs) >= 1:
        costs.sort()
        basis = (f"p95 of {len(costs)} earlier sessions" if len(costs) > 1
                 else "1 earlier session: a single canary, not a spread")
        return costs[min(len(costs) - 1, math.ceil(0.95 * len(costs)) - 1)], basis
    return budget_cents / 100, "no earlier sessions: worst case = the session budget"


# ── main ────────────────────────────────────────────────────────────────
def parse(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--flow", required=True, help="flow dir, relative to evals/ (e.g. hillclimb/ladder)")
    ap.add_argument("--variant", required=True, help="baseline or v<N>")
    ap.add_argument("--model", required=True)
    ap.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"], default=None,
                    help="omit for the model's default effort")
    ap.add_argument("--reps", type=int, default=None, help="default: _state.json reps, else 1")
    ap.add_argument("--cases", nargs="*", default=None, help="case ids (default: all)")
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--timeout-s", type=float, default=600)
    ap.add_argument("--budget-cents", type=int, default=100, help="per-session hard cap, integer cents")
    ap.add_argument("--spend-cap-usd", type=float, default=CAP_USD)
    ap.add_argument("--system-file", default=str(DEFAULT_SYSTEM_FILE))
    ap.add_argument("--cases-dir", default=None, help=argparse.SUPPRESS)  # tests point this at a temp dir
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--setup-only", action="store_true", help="create/reuse env, skill, agent and uploads; no sessions")
    ap.add_argument("--approve-harness", action="store_true", help="humans only: record the current harness sha")
    ap.add_argument("--fake", choices=["oracle", "null", "const", "api_error", "timeout", "budget"], default=None,
                    help="offline wiring check; refuses flows under hillclimb/")
    a = ap.parse_args(argv)
    if a.variant != "baseline" and not (a.variant.startswith("v") and a.variant[1:].isdigit()):
        ap.error("--variant must be 'baseline' or v<N> (the report builder ignores anything else)")
    if not a.budget_cents > 0:
        ap.error("--budget-cents must be a positive integer")
    return a


def main(argv=None) -> int:
    a = parse(argv)
    flow = (EVALS / a.flow).resolve()
    if a.fake and EVALS / "hillclimb" in [flow, *flow.parents]:
        print("--fake writes zero-cost rows; refusing to write them under hillclimb/", file=sys.stderr)
        return 2
    state_path = flow / "_state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    reps = a.reps or state.get("reps", 1)
    cases = load_cases(a.cases, **({"root": Path(a.cases_dir)} if a.cases_dir else {}))
    system = Path(a.system_file).read_text()
    cfg = AgentCfg(a.model, a.effort, system)
    vdir = flow / a.variant
    todo = [(c, r) for c in cases for r in range(reps) if (c.id, r) not in done_keys(vdir)]

    est, basis = per_session_estimate(a.model, a.effort, a.budget_cents)
    spent = 0.0 if a.fake else total_spend()
    projected = 0.0 if a.fake else round(len(todo) * est, 2)
    print(f"scope: {len(cases)} cases × {reps} reps × {a.model} ({a.effort or 'default effort'}) "
          f"-> {len(todo)} sessions to run ({len(cases) * reps - len(todo)} already done), "
          f"budget ${a.budget_cents / 100:.2f}/session, timeout {a.timeout_s:.0f}s, concurrency {a.concurrency}")
    print(f"spend: ${spent:.2f} so far of ${a.spend_cap_usd:.2f} cap; this run projects ${projected:.2f} "
          f"(${est:.2f}/session, {basis}); after: ${spent + projected:.2f}")
    print(f"prompt: {Path(a.system_file).name} sha {sha256(system)[:12]}; output: {rel(vdir)}/")

    # Flows without their own _state.json (pilots, probes) are gated by the ladder's approval.
    gate_path = state_path if state_path.exists() else LADDER_STATE
    gate_state = state if state_path.exists() else (json.loads(gate_path.read_text()) if gate_path.exists() else {})
    gate_ok = True if (a.fake and not state_path.exists()) else check_harness(gate_path, gate_state, a.approve_harness)
    if a.dry_run:
        print("dry run: nothing sent." + ("" if gate_ok else " (the harness gate would stop a real run)"))
        return 0
    if not gate_ok:
        return 2
    if spent + projected > a.spend_cap_usd:
        print(f"refusing: projected total ${spent + projected:.2f} exceeds the ${a.spend_cap_usd:.2f} cap",
              file=sys.stderr)
        return 3

    backend = FakeBackend(a.fake) if a.fake else LiveBackend(a.budget_cents)
    backend.setup(cfg, cases)
    if a.setup_only:
        print(f"setup done; registry at {REGISTRY.name}")
        return 0
    if not todo:
        print("nothing to do: every (case, rep) already has a row")
        return 0

    w = Writer(vdir)
    meta = {"flow": a.flow, "variant": a.variant, "fake": bool(a.fake) or None,
            "system_sha": sha256(system)[:16], "budget_cents": a.budget_cents}
    console = (lambda sid: f"https://platform.claude.com/workspaces/{backend.workspace}/sessions/{sid}") \
        if hasattr(backend, "workspace") else (lambda sid: None)
    t0, done, run_cost = time.monotonic(), 0, 0.0
    lock = threading.Lock()

    def one(c: Case, r: int):
        nonlocal done, run_cost
        att = backend.run(c, r, cfg, meta, a.timeout_s)
        row = record(w, c, r, cfg, att, meta, console(att.session_id) if att.session_id else None)
        with lock:
            done += 1
            run_cost += row.get("list_cost_usd") or 0.0
            g = row.get("grade")
            status = f"root_cause={g['root_cause']} format={g['format']}" if g else f"ERROR {row['class']}: {row['error']}"
            print(f"[{done}/{len(todo)}] {c.id} rep{r}: {status}  ${row.get('list_cost_usd') or 0:.2f}  "
                  f"{time.monotonic() - t0:.0f}s elapsed", flush=True)

    with cf.ThreadPoolExecutor(max_workers=a.concurrency) as ex:
        for f in [ex.submit(one, c, r) for c, r in todo]:
            f.result()

    summarize(vdir, cfg, run_cost)
    return 0


def summarize(vdir: Path, cfg: AgentCfg, run_cost: float) -> None:
    rows = [json.loads(l) for l in (vdir / "results.jsonl").read_text().splitlines() if l.strip()] \
        if (vdir / "results.jsonl").exists() else []
    errs = [json.loads(l) for l in (vdir / "errors.jsonl").read_text().splitlines() if l.strip()] \
        if (vdir / "errors.jsonl").exists() else []
    ok_keys = {(r["prompt_id"], r["rep"]) for r in rows}
    open_errs = [e for e in errs if (e["prompt_id"], e["rep"]) not in ok_keys]
    print(f"\n{rel(vdir)}: {len(rows)} scored rows, {len(open_errs)} unresolved errors, "
          f"this run ${run_cost:.2f}")
    for split in ("train", "test", "val", None):
        sub = [r for r in rows if split is None or split in r["tags"]]
        if not sub:
            continue
        for metric in ("root_cause", "format"):
            p = sum(r["grade"][metric] for r in sub) / len(sub)
            print(f"  {split or 'all':5s} {metric:10s} {p:6.1%} ± {wald(p, len(sub)):.1%}  (n={len(sub)})")
    summary = vdir / "summary.json"
    if not summary.exists():
        summary.write_text(json.dumps({"label": f"{cfg.model} {cfg.effort or 'default'}",
                                       "description": f"model={cfg.model}, effort={cfg.effort or 'default'}"},
                                      indent=2) + "\n")


if __name__ == "__main__":
    sys.exit(main())
