"""Read-only check of Higgsfield's MCP against what the SPEC and this code assume: ``python -m lampway_server.higgsfield_diff`` after signing in at
/app/higgsfield. Calls tools/list, balance and models_explore only; it never calls a generation tool."""

import json
import sys

from .higgsfield import normalise_model

EXPECTED_TOOLS = ("models_explore", "generate_video", "generate_image", "media_upload", "media_confirm", "jobs_wait", "motion_control", "balance")
EXPECTED_ARGS = {
    "generate_video": ("model", "prompt", "duration", "resolution", "aspect_ratio", "count", "medias", "generate_audio", "get_cost", "use_unlim"),
    "generate_image": ("model", "prompt", "get_cost"),
    "media_upload": ("type",), "media_confirm": ("type",), "jobs_wait": ("jobs", "timeout_seconds"),
    "motion_control": ("image_id", "motion_video_id", "resolution", "scene_control"), "models_explore": ("action", "type"),
}


def diff(mcp) -> dict:
    tools = {t["name"]: t for t in mcp.tools()}
    report = {"tools_present": sorted(tools), "tools_missing": [t for t in EXPECTED_TOOLS if t not in tools], "args": {}}
    for name, expected in EXPECTED_ARGS.items():
        props = set(((tools.get(name) or {}).get("inputSchema") or {}).get("properties") or {})
        if tools.get(name) is not None:
            report["args"][name] = {"missing_from_schema": [a for a in expected if a not in props], "also_in_schema": sorted(props - set(expected))}
    bal = mcp.call("balance", {})
    report["balance"] = {"plan": bal.get("plan"), "credits": bal.get("credits")}
    note, ids, unparsed = "", [], []
    try:
        data = mcp.call("models_explore", {"action": "list", "type": "video"})
        raw = data.get("models") or data.get("items") or []
        for m in raw:
            (ids if isinstance(m, dict) and m.get("id") else unparsed).append(normalise_model(m, "video")["id"] if isinstance(m, dict) and m.get("id") else str(m)[:80])
        if not raw:
            note = f"models_explore returned no 'models' or 'items' list; its keys: {sorted(data)[:10]}"
    except Exception as exc:  # noqa: BLE001
        note = f"models_explore failed: {type(exc).__name__}: {exc}"
    report.update(video_models=len(ids), video_model_ids=ids, unparsed_models=unparsed, catalogue_note=note)
    return report


def main() -> int:
    import os
    from pathlib import Path
    from .config import Settings
    from .higgsfield_auth import HiggsfieldAuth, NotSignedIn
    from .higgsfield_mcp import HiggsfieldMCP
    settings = Settings.from_env()
    auth = HiggsfieldAuth(Path(os.environ.get("LAMPWAY_STATE_DIR") or settings.state_dir))
    try:
        print(json.dumps(diff(HiggsfieldMCP(auth)), indent=1))
    except NotSignedIn as exc:
        print(f"error: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
