# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Studio MCP driver (AXI output, TOON): `python -m lampway_server.studios.mcp_driver hyper3d.<tool> (--plan | --run --out DIR) --args JSON`.

Hyper3D's hosted MCP (https://api.hyper3d.com/api/mcp) on Lampway's OWN sign-in (mcp_oauth.HYPER3D, its session in the Connections store;
another client's token is never read). The laws, the REST driver's (studios/rest/driver.py):

  * --plan spends nothing: no tools/call. The MCP publishes no price and has no balance tool, so a paid tool needs
    ``accept_up_to_credits`` (an unknown price is never waved through); the balance is read from the REST API when that key is connected.
  * --run is the confirmed run: refused unless the studio guard is armed (the service arms exactly one confirmed run). A paid tool is
    called exactly ONCE; a transport timeout means the outcome is unknown: it is reported HUNG and NEVER resent.
  * downloads are https only (no userinfo), into --out, a sha256 per file; no signed URL and no token is printed."""
from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from . import axi

PAID = ("generate", "generate_bang")
TOOLS = ("create_uploads", "import_images", "generate", "generate_bang", "get_status", "wait", "get_result")
MAX_FILE_BYTES = 512 * 1024 * 1024
DATED_NOTE = "unknown: the MCP publishes no price; the ceiling is what you accept"


def _fail(why, nexts=()):
    print(f"error: {why}")
    axi.helps(list(nexts))
    return 1


def _client(env, transport, store):
    from .. import mcp_oauth as MO
    from ..connections.hub import default_secrets_dir
    from ..connections.store import choose_store
    from ..mcp_client import McpClient
    secrets_dir = default_secrets_dir(env)
    if store is None:
        store, _ = choose_store(secrets_dir)
    auth = MO.for_store(MO.HYPER3D, lambda: store, secrets_dir, http=httpx.Client(transport=transport, timeout=30.0))
    if not auth.status()["signed_in"]:
        raise MO.NotSignedIn("Hyper3D is not signed in: sign in from Connections")
    return McpClient(auth, url=MO.HYPER3D.mcp_url, label="Hyper3D", transport=transport, timeout=60.0)


def _rest_balance(env, transport):
    """The REST balance when Hyper3D REST is connected (its key reaches this driver as HYPER3D_API_KEY), else None."""
    if not (env.get("HYPER3D_API_KEY") or env.get("RODIN_API_KEY")):
        return None
    from .rest import client as RC
    from .rest import shapes as SH
    try:
        return RC.RestStudio(SH.HYPER3D, {**env, "LAMPWAY_STUDIO_POLL_S": env.get("LAMPWAY_STUDIO_POLL_S", "0")}, transport).balance()
    except RC.StudioError:
        return None


def _download(url, out_dir, name, transport) -> dict:
    p = urlsplit(url)
    if p.scheme != "https" or p.username or p.password or not p.hostname:
        raise ValueError("refusing a download that is not plain https")
    dest = Path(out_dir) / Path(name or p.path).name
    part = dest.with_suffix(dest.suffix + ".part")
    h, n = hashlib.sha256(), 0
    with httpx.Client(transport=transport, timeout=120.0, follow_redirects=False) as client, client.stream("GET", url) as r:
        if r.status_code >= 400:
            raise ValueError(f"the download answered HTTP {r.status_code}")
        with open(part, "wb") as fh:
            for chunk in r.iter_bytes():
                n += len(chunk)
                if n > MAX_FILE_BYTES:
                    raise ValueError("a file is over 512 MB: refused")
                h.update(chunk)
                fh.write(chunk)
    os.replace(part, dest)
    return {"name": dest.name, "path": str(dest), "bytes": n, "sha256": h.hexdigest()}


def _upload(client, images, transport) -> list:
    files = [{"filename": Path(i).name, "mime_type": mimetypes.guess_type(i)[0] or "image/png", "size_bytes": Path(i).stat().st_size} for i in images]
    slots = (client.call("rodin_create_uploads", {"files": files}) or {}).get("uploads") or []
    if len(slots) != len(images):
        raise ValueError("Hyper3D did not return an upload slot per image")
    with httpx.Client(transport=transport, timeout=120.0, follow_redirects=False) as http:
        for slot, path in zip(slots, images):
            r = http.put(slot["upload_url"], content=Path(path).read_bytes())
            if r.status_code >= 400:
                raise ValueError(f"an upload answered HTTP {r.status_code}")
    return [s["upload_id"] for s in slots]


def _validate(tool, raw) -> dict:
    a = dict(raw or {})
    if tool == "import_images":
        raise ValueError("rodin_import_images takes ChatGPT's own file parameters: use hyper3d.mcp.generate with local images")
    if tool == "generate":
        if not a.get("prompt") and not a.get("images"):
            raise ValueError("generate needs a prompt and/or images (1 to 5)")
        if len(a.get("images") or []) > 5:
            raise ValueError("generate takes 1 to 5 reference images")
    if tool == "generate_bang" and not a.get("asset_id"):
        raise ValueError("generate_bang needs asset_id: a Rodin generation_id (the MCP's Bang takes Rodin generations only)")
    if tool in ("get_status", "wait", "get_result") and not a.get("generation_id"):
        raise ValueError(f"{tool} needs generation_id")
    return a


def main(argv=None, env=None, transport=None, store=None) -> int:
    from ..mcp_client import TransportTimeout, MCPError
    from ..mcp_oauth import NotSignedIn
    argv = list(sys.argv[1:] if argv is None else argv)
    env = dict(env if env is not None else os.environ)
    if len(argv) < 2 or "--args" not in argv or not ({"--plan", "--run"} & set(argv)):
        axi.home(__file__, "Studio MCP driver: Hyper3D (Rodin) through Lampway's own MCP sign-in")
        return _fail("usage: hyper3d.<tool> (--plan | --run --out DIR) --args JSON", ["sign in to Hyper3D from Connections first"])
    full, plan = argv[0], "--plan" in argv
    studio, _, tool = full.partition(".")
    if studio != "hyper3d" or tool not in TOOLS:
        return _fail(f"no such action {full!r}: the actions are {sorted('hyper3d.' + t for t in TOOLS)}")
    out_dir = argv[argv.index("--out") + 1] if "--out" in argv else None
    try:
        raw = json.loads(argv[argv.index("--args") + 1])
        ceiling = raw.pop("accept_up_to_credits", None)
        args = _validate(tool, raw)
        paid = tool in PAID
        if paid and ceiling is None:
            return _fail(f"the price of hyper3d.{tool} is not published: pass accept_up_to_credits (the most you will let it spend); an unknown price is never waved through")
        if plan:
            if not paid:
                axi.kv({"dry_run": "verified", "studio": "hyper3d", "action": tool, "price_effective_credits": 0})
                return 0
            client = _client(env, transport, store)
            client.tools()                                                         # signed in and alive; no tool is called
            kv = {"dry_run": "verified", "studio": "hyper3d", "action": tool, "unit": "credits", "price_credits": None, "price_ceiling_credits": ceiling,
                  "price_source": DATED_NOTE, "balance_credits": _rest_balance(env, transport), "price_effective_credits": float(ceiling)}
            axi.kv(kv)
            axi.helps(["confirm in the Client (Studios panel): only you can; nothing was created"])
            return 0
        if paid and env.get("LAMPWAY_STUDIO_ARMED") != "1":
            return _fail(f"hyper3d.{tool} spends credits and the studio guard is not armed: only the user's confirmed run is armed",
                         ["confirm the approval in the Client (Studios panel)"])
        client = _client(env, transport, store)
        if tool == "create_uploads":
            ids = _upload(client, args.get("images") or [], transport)
            axi.kv({"studio": "hyper3d", "action": tool, "upload_ids": ",".join(ids)})
            return 0
        if tool in ("get_status", "wait"):
            res = client.call("rodin_" + tool, {"generation_id": args["generation_id"]})
            axi.kv({"studio": "hyper3d", "action": tool, "generation_id": args["generation_id"], "status": res.get("status")})
            return 0
        before = _rest_balance(env, transport) if paid else None
        if tool == "generate":
            call = {k: v for k, v in args.items() if k in ("prompt", "mesh_mode", "tier", "texture_delight", "quality_override", "geometry_file_format")}
            if args.get("images"):
                call["reference_upload_ids"] = _upload(client, args["images"], transport)
        elif tool == "generate_bang":
            call = {k: v for k, v in args.items() if k in ("asset_id", "instruction", "strength", "explode_strength", "escore", "reference_scale", "seed",
                                                          "geometry_file_format", "resolution")}
        else:
            call = {"generation_id": args["generation_id"]}
        if paid:
            try:
                res = client.call("rodin_" + tool, call)                         # exactly ONE paid call
            except TransportTimeout:
                return _fail(f"hyper3d.{tool} did not answer in time: the generation may exist. HUNG (never re-click): look for it in your Hyper3D "
                             "history and acknowledge this job in Studios")
            gid = res.get("generation_id")
            if not gid:
                return _fail(f"hyper3d.{tool} returned no generation_id: nothing was resubmitted")
            deadline = time.time() + float(env.get("LAMPWAY_STUDIO_MAX_WAIT_S", "1800"))
            while True:
                st = client.call("rodin_wait", {"generation_id": gid})
                if str(st.get("status", "")).lower() in ("done", "succeeded", "completed", "failed", "error") or time.time() > deadline:
                    break
                time.sleep(float(env.get("LAMPWAY_STUDIO_POLL_S", "3")))
            if str(st.get("status", "")).lower() in ("failed", "error"):
                return _fail(f"hyper3d.{tool} generation {gid} failed: nothing was resubmitted; check the balance for the provider's refund")
        else:
            gid = args["generation_id"]
        result = client.call("rodin_get_result", {"generation_id": gid})
        files = []
        if out_dir:
            Path(out_dir).mkdir(parents=True, exist_ok=True)
            files = [_download(f["url"], out_dir, f.get("name"), transport) for f in result.get("files") or [] if f.get("url")]
        after = _rest_balance(env, transport) if paid else None
        axi.kv({"studio": "hyper3d", "action": tool, "generation_id": gid, "status": "done", "balance_before": before, "balance_after": after, "out_dir": out_dir})
        axi.table("files", files, ["name", "path", "bytes", "sha256"])
        return 0
    except NotSignedIn as exc:
        return _fail(str(exc), ["sign in to Hyper3D from Connections"])
    except (ValueError, MCPError, OSError) as exc:
        from ..logredact import redact_text
        return _fail(redact_text(str(exc))[:300])


if __name__ == "__main__":
    raise SystemExit(main())
