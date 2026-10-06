"""`lampway-compute`: ONE provider-agnostic AXI CLI over the compute wrapper (the captain: "an agnostic aXi wrapper over the boat CLI and other cloud inference backend providers ... give people the
choice"). AXI principles (the shelf's tools/AXI.md): argparse, a live no-args view (content first), TOON summaries, explicit empties, a `help[]` of next steps after every output, structured errors and
exit codes (0 ok, 1 refused or failed, 2 usage), no interactive prompts, unknown flags fail loud. The user picks the provider: nothing is hard-wired. The same library serves the server."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from .. import egress as E
from .. import jobreceipts as JR
from ..ledger import Ledger
from . import prefs as PF
from . import recipes as RC
from . import runner as R
from . import toon_out as T

PROVIDERS = ("boat", "modal", "runpod", "fal")
ROUTE_OF = {"boat": "compute:boat", "modal": "compute:modal", "runpod": "compute:runpod", "fal": "fal"}


class UsageError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise UsageError(message)


@dataclass
class Context:
    root: Path
    state: Path
    backends_factory: Optional[Callable] = None
    clock: Callable = time.time
    sleep: Callable = time.sleep


def default_context() -> Context:
    root = Path(os.environ.get("LAMPWAY_PROJECT_ROOT") or Path.cwd())
    state = Path(os.environ.get("LAMPWAY_STATE_DIR") or Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "lampway")
    return Context(root, state)


def default_backends(prefs) -> dict:
    from . import boat as BT
    from . import endpoint as EP
    out, cfg = {}, prefs.data
    for name in cfg["backends"]:
        if name == "boat":
            out[name] = BT.BoatCliBackend()
        elif name in EP.SHAPES:
            out[name] = EP.EndpointBackend(name, (cfg.get("endpoints") or {}).get(name) or {})
    return out


def build(ctx: Context, own_egress: bool = True):
    E.install()
    if own_egress:
        E.set_active(E.Egress(ctx.state))                      # the CLI is its own Lampway process: every route is off until the user opts in (the same egress.json the server uses)
    prefs = PF.Prefs(ctx.state / "compute_prefs.json")
    ledger = Ledger(ctx.root / "ledger" / "runs.jsonl")
    receipts = JR.JobReceipts(ctx.root, ledger=ledger)
    backends = (ctx.backends_factory or default_backends)(prefs)
    return prefs, R.ComputeRunner(ctx.root, receipts, ledger, prefs, backends, clock=ctx.clock, sleep=ctx.sleep)


def _parser() -> _Parser:
    p = _Parser(prog="compute", description="Rent compute through any provider, with receipts, caps, a privacy gate and egress consent.", add_help=True)
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("backends", help="the providers, which are enabled, and their egress state")
    sub.add_parser("recipes", help="what can run on a box")
    sub.add_parser("list", help="compute jobs")
    sub.add_parser("reconcile", help="re-adopt, finish and tear down; report orphans and what still bills")
    for name in ("plan", "submit"):
        s = sub.add_parser(name, help=f"{name} a job (no spend until you submit and approve)")
        s.add_argument("recipe")
        s.add_argument("--backend")
        s.add_argument("--input", action="append", default=[], help="path[:public|synthetic|private]; no class means private")
        s.add_argument("--max-seconds", type=int, default=300)
        s.add_argument("--max-usd", type=float)
        s.add_argument("--type", help="machine type for Boat: small | default | large")
        s.add_argument("--param", action="append", default=[], metavar="KEY=VALUE", help="a recipe parameter, e.g. op=silhouette (repeatable; a value that parses as JSON is JSON)")
        s.add_argument("--key", help="idempotency key")
        s.add_argument("--origin", default="user", choices=["user", "agent", "swarm"])
        if name == "submit":
            s.add_argument("--yes-price", type=float, help="your approval of exactly this worst-case dollar amount")
    for name in ("status", "cancel"):
        sub.add_parser(name, help=f"{name} a job").add_argument("key")
    sub.add_parser("approve", help="approve a planned spend (your click)").add_argument("plan_id")
    pr = sub.add_parser("prefs", help="show or set caps, enabled backends, orphan action")
    pr.add_argument("--set", action="append", default=[], metavar="KEY=VALUE")
    eg = sub.add_parser("egress", help="show the routes, or switch one on or off (your choice: every route is off until you opt in)")
    eg.add_argument("route", nargs="?")
    eg.add_argument("state", nargs="?", choices=["on", "off"])
    return p


def _job(a) -> dict:
    ins = []
    for i in a.input:
        path, _, cls = i.partition(":")
        ins.append({"path": path, **({"content_class": cls} if cls else {})})
    params = {"type": a.type} if a.type else {}
    for kv in a.param:
        k, _, v = kv.partition("=")
        try:
            params[k] = json.loads(v)
        except ValueError:
            params[k] = v
    j = {"recipe": a.recipe, "inputs": ins, "backend": a.backend, "max_seconds": a.max_seconds, "origin": a.origin, "idempotency_key": a.key, "params": params}
    if a.max_usd is not None:
        j["max_usd"] = a.max_usd
    return j


def _state_view(prefs, runner, ctx) -> dict:
    d, eg = prefs.data, E.ACTIVE
    jobs = runner.list_jobs()
    bn = runner.billing_now()
    names = list(dict.fromkeys(list(PROVIDERS) + list(runner.backends)))
    return {"backends": [{"name": n, "enabled": n in d["backends"], "egress": ("on" if eg.enabled(ROUTE_OF.get(n, "")) else "off") if n in ROUTE_OF else "n/a"} for n in names],
            "job_cap_usd": float(d["spend"]["job_cap"]), "day_cap_usd": float(d["spend"]["day_cap"]), "click": f"{d['spend']['click']} {d['spend'].get('above', '')}".strip(), "spent_today_usd": runner._day_spent(),
            "jobs": [{"key": j["key"], "backend": j["backend"], "state": j["state"]} for j in jobs[-10:]], "jobs_total": len(jobs),
            "billing_now": bn if bn else "nothing"}


def main(argv=None, ctx: Optional[Context] = None, out=None, err=None) -> int:
    out, ctx = out or sys.stdout, ctx or default_context()

    def emit(obj, helps=(), rc=0):
        body = T.dumps(obj)
        if helps:
            body += ("\n" if body else "") + T.dumps({"help": list(helps)})
        print(body, file=out)
        return rc

    def fail(message, helps=(), rc=1):
        return emit({"error": message}, helps, rc)

    try:
        a = _parser().parse_args(list(argv if argv is not None else sys.argv[1:]))
    except UsageError as exc:
        return fail(str(exc), ["run `compute --help` for the commands", "run `compute` with no arguments for the live state"], 2)
    except SystemExit:
        return 0
    prefs, runner = build(ctx)
    try:
        if a.cmd is None:
            return emit(_state_view(prefs, runner, ctx), ["compute backends: pick a provider", "compute egress <route> on: let data leave through a route (off by default)", "compute plan <recipe> --backend <name> --input <path>: price a job"])
        if a.cmd == "backends":
            return emit({"backends": _state_view(prefs, runner, ctx)["backends"], "note": "there is no default provider: you choose one"}, ["compute prefs --set backends=boat", "compute egress compute:boat on"])
        if a.cmd == "recipes":
            return emit({"recipes": [{"id": r.id, "version": r.version, "gpu": r.hardware_gpu, "outputs": ",".join(r.outputs)} for r in RC.RECIPES.values()]}, ["compute plan <recipe> --backend <name> --input <path>"])
        if a.cmd == "list":
            jobs = [{k: j[k] for k in ("key", "backend", "recipe", "state")} for j in runner.list_jobs()]            # a minimal default schema: four fields
            return emit({"count": len(jobs), "jobs": jobs} if jobs else {"count": 0, "jobs": []}, ["compute status <key>"] if jobs else ["compute submit <recipe> --backend <name> --input <path>"])
        if a.cmd == "status":
            return emit(runner.status(a.key), ["compute list"])
        if a.cmd == "cancel":
            return emit(runner.cancel(a.key), ["compute reconcile"])
        if a.cmd == "approve":
            return emit(runner.approve(a.plan_id, "user"), ["compute submit ... --yes-price <upper_bound_usd>"])
        if a.cmd == "reconcile":
            rep = runner.reconcile()
            bn = rep.pop("billing_now")
            rep["billing_now"] = bn if bn else "nothing"
            return emit({k: v for k, v in rep.items()}, ["compute list", "compute prefs --set orphan_action=stop: stop (never delete) orphans on the next reconcile"])
        if a.cmd == "prefs":
            changes: dict = {}
            for kv in a.set:
                k, _, v = kv.partition("=")
                if k in ("backends", "private_backends"):
                    changes[k] = [x for x in v.split(",") if x]
                elif k in ("job_cap", "day_cap", "above"):
                    changes.setdefault("spend", dict(prefs.data["spend"]))[k] = float(v)
                elif k == "click":
                    changes.setdefault("spend", dict(prefs.data["spend"]))[k] = v
                elif k == "orphan_action":
                    changes[k] = v
                else:
                    raise UsageError(f"unknown pref {k!r}: backends, private_backends, job_cap, day_cap, click, above, orphan_action")
            d = prefs.update(changes) if changes else prefs.data
            return emit({"backends": d["backends"], "private_backends": d["private_backends"], "orphan_action": d["orphan_action"], "job_cap_usd": d["spend"]["job_cap"], "day_cap_usd": d["spend"]["day_cap"],
                         "click": d["spend"]["click"], "above_usd": d["spend"].get("above")}, ["compute backends"])
        if a.cmd == "egress":
            eg = E.ACTIVE
            if a.route and a.state:
                return emit(eg.set_route(a.route, a.state == "on"), ["the same switch is in the Lampway Privacy panel"])
            return emit({"routes": [{"id": r["id"], "label": r["label"], "state": "on" if r["enabled"] else "off", "retention": r["retention"][:60]} for r in eg.routes_view() if r["id"].startswith("compute:") or r["id"] == "fal"]}, ["compute egress compute:boat on"])
        if a.cmd in ("plan", "submit"):
            job = _job(a)
            if not job["backend"]:
                return fail(f"pick a provider for this job: --backend one of {', '.join(prefs.data['backends']) or 'none enabled yet'}", ["compute prefs --set backends=boat", "compute backends"])
            if a.cmd == "plan":
                p = runner.plan(job)["plan"]
                q = p["quote"]
                return emit({"plan_id": p["plan_id"], "backend": q["backend"], "hardware": q["hardware"], "rate_usd_per_s": q["rate_usd_per_s"], "upper_bound_usd": q["upper_bound_usd"], "basis": q["basis"], "ttl_s": q["ttl_seconds"],
                             "content_class": p["privacy"]["content_class"], "backend_class": p["privacy"]["backend_class"], "needs_click": p["needs_click"], "day_spent_usd": p["caps"]["day_spent_usd"],
                             "uploads_files": p["uploads"]["files"], "uploads_bytes": p["uploads"]["bytes"]},
                            [f"compute submit {a.recipe} --backend {a.backend} ... " + (f"--yes-price {q['upper_bound_usd']:.6g}" if p["needs_click"] else "(no click needed under your threshold)")])
            ap = None
            if job["origin"] == "user":
                p = runner.plan(job)["plan"]
                if p["needs_click"]:
                    if a.yes_price is None or abs(a.yes_price - p["quote"]["upper_bound_usd"]) > 1e-6 * max(1.0, p["quote"]["upper_bound_usd"]):
                        return fail(f"this job needs your approval of ${p['quote']['upper_bound_usd']:.6g}: re-run with --yes-price {p['quote']['upper_bound_usd']:.6g}", ["compute plan ... shows the price card"])
                    ap = runner.approve(p["plan_id"], "user")["approval_id"]
            res = runner.submit(job, ap)
            return emit({k: res[k] for k in res if k in ("key", "state", "error", "teardown", "already_exists", "accrued_usd_estimate", "accrued_usd_meter")}, ["compute status " + res.get("key", "<key>"), "compute reconcile"])
    except (R.Refused, UsageError) as exc:
        return fail(str(exc), ["compute plan ... shows the price card and the refusal reason"])
    except PermissionError as exc:
        return fail(str(exc), ["compute egress <route> on: your choice"])
    except Exception as exc:  # noqa: BLE001
        return fail(f"{type(exc).__name__}: {exc}", ["compute reconcile: re-adopts or reports anything left running"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
