"""Read-only check of Higgsfield's MCP against what the SPEC and this code assume: ``python -m lampway_server.higgsfield_diff`` after signing in at
/app/higgsfield. Calls tools/list, balance and models_explore only; it never calls a generation tool."""

import json
import sys

from .higgsfield import PARAMS_TOOLS, Higgsfield

EXPECTED_TOOLS = ("models_explore", "generate_video", "generate_image", "media_upload", "media_confirm", "jobs_wait", "balance")
# The arguments this code sends, as the LIVE schemas name them (recorded 2026-10-05). The generation tools take ONE argument, ``params``; what is
# listed here for them is what must be accepted INSIDE it, either declared or through additionalProperties.
EXPECTED_ARGS = {
    "generate_video": ("model", "prompt", "duration", "resolution", "aspect_ratio", "count", "medias", "generate_audio", "get_cost", "use_unlim"),
    "generate_image": ("model", "prompt", "resolution", "aspect_ratio", "count", "medias", "get_cost"),
    "media_upload": ("files",), "media_confirm": ("type", "media_ids"), "jobs_wait": ("jobs", "timeout_seconds"),
    "models_explore": ("action", "type", "limit", "after"),
}


def _args_schema(schema: dict) -> dict:
    """The schema of the arguments that matter: for the generation tools the object inside ``params``."""
    props = (schema or {}).get("properties") or {}
    if "params" in props:
        alts = props["params"].get("anyOf") or [props["params"]]
        return next((a for a in alts if a.get("type") == "object"), {})
    return schema or {}


def diff(mcp) -> dict:
    tools = {t["name"]: t for t in mcp.tools()}
    report = {"tools_present": sorted(tools), "tools_missing": [t for t in EXPECTED_TOOLS if t not in tools], "args": {}}
    for name, expected in EXPECTED_ARGS.items():
        if tools.get(name) is None:
            continue
        top = (tools[name].get("inputSchema") or {})
        schema = _args_schema(top)
        props = set(schema.get("properties") or {})
        open_ended = schema.get("additionalProperties") is not False           # undeclared keys inside params are accepted
        missing = [a for a in expected if a not in props and not (name in PARAMS_TOOLS and open_ended)]
        wrapped = name in PARAMS_TOOLS and "params" not in (top.get("properties") or {})
        report["args"][name] = {"missing_from_schema": missing, "also_in_schema": sorted(props - set(expected)), "takes_params_wrapper": name in PARAMS_TOOLS and not wrapped}
        if wrapped:
            report["args"][name]["missing_from_schema"] = ["params"] + missing
    bal = mcp.call("balance", {})
    report["balance"] = {"plan": bal.get("subscription_plan_type") or bal.get("plan"), "credits": bal.get("credits")}
    note, ids, unparsed = "", [], []
    try:
        rows = Higgsfield(mcp).models("video")                                 # every page, not the first twenty
        ids = [m["id"] for m in rows]
        if not rows:
            note = "models_explore returned no models"
    except Exception as exc:  # noqa: BLE001
        note = f"models_explore failed: {type(exc).__name__}: {exc}"
    report.update(video_models=len(ids), video_model_ids=ids, unparsed_models=unparsed, catalogue_note=note)
    report["mismatches"] = len(report["tools_missing"]) + sum(len(v["missing_from_schema"]) for v in report["args"].values()) + (0 if report["balance"]["plan"] else 1)
    return report


def dump(mcp, out_dir) -> None:
    """Record what the live server says (read-only: tools/list, balance, models_explore list) as test fixtures: the definitions of the tools this code
    calls, and the raw bodies, so the fake can be checked against the recording instead of against our assumptions."""
    from pathlib import Path
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    wanted = [t for t in mcp.tools() if t.get("name") in EXPECTED_TOOLS]
    (out / "tools_list.json").write_text(json.dumps(wanted, indent=1, sort_keys=True), encoding="utf-8")
    (out / "balance.json").write_text(json.dumps(mcp.call("balance", {}), indent=1, sort_keys=True), encoding="utf-8")
    for kind in ("video", "image"):
        (out / f"models_{kind}.json").write_text(json.dumps(mcp.call("models_explore", {"action": "list", "type": kind, "limit": 100}), indent=1, sort_keys=True), encoding="utf-8")


def main() -> int:
    import os
    from pathlib import Path
    from .config import Settings
    from .higgsfield_auth import HiggsfieldAuth, NotSignedIn
    from .higgsfield_mcp import HiggsfieldMCP
    settings = Settings.from_env()
    auth = HiggsfieldAuth(Path(os.environ.get("LAMPWAY_STATE_DIR") or settings.state_dir))
    try:
        mcp = HiggsfieldMCP(auth)
        if len(sys.argv) > 2 and sys.argv[1] == "--dump":
            dump(mcp, sys.argv[2])
        print(json.dumps(diff(mcp), indent=1))
    except NotSignedIn as exc:
        print(f"error: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
