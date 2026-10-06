"""The Studio REST driver (AXI output, TOON): `python -m lampway_server.studios.rest.driver <studio>.<action> (--plan | --run --out DIR) --args JSON`.

--plan reads the list price and the balance and spends nothing. --run is the confirmed run: it refuses unless the studio guard is armed (the service arms exactly one confirmed run), reads the balance, creates ONE
task, polls it, downloads the files and reports the credits consumed and the balance after. Keys come from the environment only; nothing secret and no signed URL is printed."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from .. import axi
from . import client as RC
from . import shapes as SH

DATED_NOTE = f"list price (the provider docs' own table, {SH.DATED}; not a quote)"


def _fail(why, nexts=()):
    print(f"error: {why}")
    axi.helps(list(nexts))
    return 1


def main(argv=None, env=None, transport=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    env = dict(env if env is not None else os.environ)
    if len(argv) < 2 or "--args" not in argv or not ({"--plan", "--run"} & set(argv)):
        axi.home(__file__, "Studio REST driver: Meshy, Hyper3D (Rodin), Hi3D (Hitem3D) and Tripo REST")
        return _fail("usage: <studio>.<action> (--plan | --run --out DIR) --args JSON", ["python -m lampway_server.studios.rest.driver meshy.uv_unwrap --plan --args '{\"model\": \"piece.glb\"}'"])
    full, plan = argv[0], "--plan" in argv
    studio_name, _, action_name = full.partition(".")
    if studio_name not in SH.STUDIOS:
        return _fail(f"no such studio {studio_name!r}: the studios are {sorted(SH.STUDIOS)}")
    out_dir = argv[argv.index("--out") + 1] if "--out" in argv else None
    try:
        raw = json.loads(argv[argv.index("--args") + 1])
        ceiling = raw.pop("accept_up_to_credits", None)
        shape = SH.STUDIOS[studio_name]
        if action_name not in shape.actions:
            return _fail(f"no such action {full!r}: the actions are {sorted(studio_name + '.' + a for a in shape.actions)}")
        act = shape.actions[action_name]
        clean = act.validate(raw)
        st = RC.RestStudio(shape, env, transport)
        st.check_key()                                                            # needs_key before any request
        price = act.price(clean)
        if price is None and ceiling is None:
            return _fail(f"the price of {full} is not published: pass accept_up_to_credits (the most you will let it spend); an unknown price is never waved through")
        bal = st.balance()
        eff = float(price if price is not None else ceiling)
        if plan:
            kv = {"dry_run": "verified", "studio": studio_name, "action": action_name, "unit": "credits", "price_credits": price, "price_ceiling_credits": ceiling if price is None else None,
                  "price_source": DATED_NOTE if price is not None else "unknown: not published; the ceiling is what you accept", "balance_credits": bal,
                  "price_effective_credits": eff}
            if shape.usd_per_credit:
                kv["usd_estimate"] = round(eff * shape.usd_per_credit, 4)
            axi.kv(kv)
            axi.helps(["confirm in the Client (Studios panel): only you can; nothing was created"])
            return 0
        if env.get("LAMPWAY_STUDIO_ARMED") != "1":
            return _fail(f"{full} spends credits and the studio guard is not armed: only the user's confirmed run is armed", ["confirm the approval in the Client (Studios panel)"])
        if eff > bal:
            return _fail(f"the balance is {bal:g} credits, less than the {eff:g} this run can cost: nothing was created")
        h = st.create(act, clean)                                                   # exactly ONE create
        res = st.poll(act, h)
        after = st.balance()
        consumed = res.get("consumed") if res.get("consumed") is not None else round(bal - after, 4)
        if res["state"] == "failed":
            return _fail(f"{full} task {h['id']} failed: {res['error']}. Credits consumed by the provider's account: {consumed:g} (balance {bal:g} to {after:g}); failed tasks are refunded by the provider's rules: check the balance. Nothing was resubmitted")
        files = [st.download(u, out_dir, n) for n, u in res["urls"]] if out_dir else []
        axi.kv({"studio": studio_name, "action": action_name, "task_id": h["id"], "status": "SUCCEEDED" if studio_name == "meshy" else "done", "consumed_credits": consumed, "balance_before": bal, "balance_after": after,
                "out_dir": out_dir})
        axi.table("files", files, ["name", "path", "bytes", "sha256"])
        return 0
    except SH.ParamError as exc:
        return _fail(str(exc))
    except RC.StudioError as exc:
        return _fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
