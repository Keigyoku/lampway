"""The Wave 6 server-run planning tools: they read the server's own catalogues and ledger (the video catalogue, the Studio actions, the experiment ledger), so
they run in the agent loop here and never go through Blender. None of them generates or confirms a spend: a spend is always a needs_approval card the user
confirms in the Client."""

import asyncio
import json

from .providers.base import ToolSpec

NAMES = {"lampway_cinematic_shot_plan"}


def _obj(props, req=()):
    return {"type": "object", "properties": props, "required": list(req), "additionalProperties": False}


def specs() -> list:
    return [
        ToolSpec("lampway_cinematic_shot_plan", "Reference blockout to AI cinematic as a typed plan; nothing is generated. action plan {scene, shots: [{id, action (ONE verb), "
                 "camera (ONE move), duration_s, end, prop}], character_refs: [{path, text naming the wearer-left/right sides}], model}: each shot gets the wiki prompt "
                 "template filled in, its stages (playblast_capture, render_condition_passes, image_edit, video_generate, frame_review) and the video price read from the "
                 "model's own pricing_skus (an unknown price stays unknown; a Higgsfield model's credits are read back at the confirm); the total is summed and the "
                 "shortest shot is named first. The image edit and the video are needs_approval: the user confirms each spend in the Client. split {scene, shot, actions: "
                 "[first, second], durations} turns a failing shot into two. review {scene, shot, review: {identity, doubling, action_order, camera: pass|fail}, by} "
                 "records a typed review and says chain, split or redo. show {scene}. Refused: two actions or two camera moves in one shot (and / then / a comma), "
                 "references without wearer-left/right text. Stored under <root>/cinematics/<scene>/plan.json.",
                 _obj({"action": {"type": "string", "description": "plan | split | review | show"}, "scene": {"type": "string"},
                       "shots": {"type": "array", "items": {"type": "object"}}, "character_refs": {"type": "array", "items": {"type": "object"}},
                       "model": {"type": "string"}, "shot": {"type": "string"}, "actions": {"type": "array", "items": {"type": "string"}},
                       "durations": {"type": "array", "items": {"type": "number"}}, "review": {"type": "object"}, "by": {"type": "string", "description": "captain | agent"},
                       "note": {"type": "string"}}, ["action", "scene"])),
    ]


def _catalogue(hub):
    video = getattr(hub, "video", None)
    return getattr(video, "client", None)


async def call(hub, root, name: str, arguments: dict) -> tuple:
    a = arguments if isinstance(arguments, dict) else {}
    try:
        if name == "lampway_cinematic_shot_plan":
            from .. import cinematic as CI
            act = a.get("action")
            if act == "plan":
                out = await asyncio.to_thread(CI.plan, str(root), a.get("scene"), a.get("shots"), a.get("character_refs"), a.get("model"), _catalogue(hub))
            elif act == "split":
                out = await asyncio.to_thread(CI.split, str(root), a.get("scene"), a.get("shot"), a.get("actions"), _catalogue(hub), a.get("durations"))
            elif act == "review":
                out = CI.review(str(root), a.get("scene"), a.get("shot"), a.get("review"), a.get("by") or "agent", a.get("note") or "")
            elif act == "show":
                out = CI._load(str(root), a.get("scene"))
            else:
                return "action is plan | split | review | show", True
            return json.dumps(out), False
    except ValueError as exc:
        return str(exc), True
    return f"unknown planning tool {name!r}", True
