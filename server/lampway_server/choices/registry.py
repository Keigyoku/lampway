# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The registry: specs/choices/PURPOSES.md as data (55 purposes) plus ``normalize.judge`` (the canon lane's typed judge). One place a
purpose and its options are described; the resolver, the routes, the agent tool and the receipts read it.

An option id names where it runs: ``openrouter:<model>``, ``chatgpt_plan:<model>``, ``anthropic:<model>``, ``openai:<model>`` (the
OpenAI-compatible endpoint), ``mock``,
``studio:<Studio action id>``, ``higgsfield:<model>``, ``fal:<endpoint>``, ``compute:<backend>``, ``local:<engine>``,
``deterministic:<method>`` and ``follow:<purpose>``. ``option_facts`` derives the connection, the route, where it runs and the retention
class from the id, so a fact is never written twice."""

from dataclasses import dataclass, field
from typing import Optional

GROUPS = (("agents", "Agents"), ("images", "Images"), ("video", "Video"), ("3d", "3D"), ("embeddings", "Embeddings"),
          ("tracking", "Tracking and motion"), ("compute", "Compute"), ("prompts", "Prompts, looks and surfaces"))
POLICIES = ("chain", "any_local", "none")


@dataclass(frozen=True)
class Purpose:
    id: str
    label: str
    group: str
    needs: str
    content_class: str                       # private | public | synthetic
    options: tuple
    default: tuple = ()                      # the shipped chain (preferred first); () = nothing chosen yet
    policy: str = "chain"                    # the agents' per-job override policy (CH3)
    params: dict = field(default_factory=dict)
    caps: dict = field(default_factory=dict)  # option -> capability bounds the job's needs are checked against
    note: str = ""


# ---------------------------------------------------------------------------------------------------------------------- option facts
# No agent CLI is an option: claude_cli, codex_cli and codex_app_server were retired from every purpose (agent-modes spec R0); those
# CLIs run as the user's own agent instead (Bring Your Own Agent).
_ROUTES = {"openrouter": "openrouter", "chatgpt_plan": "chatgpt_plan", "anthropic": "claude_plan", "higgsfield": "higgsfield", "fal": "fal",
           "openai": "custom_llm"}
_CONNECTIONS = {"openrouter": "openrouter", "chatgpt_plan": "chatgpt_plan", "anthropic": "anthropic", "higgsfield": "higgsfield", "fal": "fal",
                "openai": "custom_llm"}
_STUDIO_CONNECTIONS = {"tripo": "studio:tripo", "meshy": "studio:meshy", "hyper3d": "studio:hyper3d", "hi3d": "studio:hi3d"}


def provider_of(oid: str) -> str:
    return oid.split(":", 1)[0]


def model_of(oid: str) -> Optional[str]:
    head, sep, rest = oid.partition(":")
    return rest if sep and head not in ("studio", "local", "deterministic", "follow", "compute") else None


def option_facts(oid: str) -> dict:
    """{provider, model, runs, connection, route, retention} for an option id (no network, no state)."""
    prov = provider_of(oid)
    facts = {"provider": prov, "model": model_of(oid), "runs": "local", "connection": None, "route": None, "retention": "local"}
    if prov in ("local", "deterministic", "mock", "follow"):
        return facts
    if prov == "studio":
        action = oid.split(":", 1)[1]
        studio = action.split(".", 1)[0]
        rest = action.startswith("tripo.rest.")
        conn = "studio:tripo_api" if rest else ("mcp:hyper3d" if action.startswith("hyper3d.mcp.") else _STUDIO_CONNECTIONS.get(studio))
        facts.update(provider=f"studio:{studio}", model=None, runs=studio, connection=conn, route=f"studio:{studio}", retention="unknown")
        return facts
    if prov == "compute":
        backend = oid.split(":", 1)[1]
        facts.update(runs=backend, connection=f"compute:{backend}" if backend != "fal" else "fal", route=f"compute:{backend}" if backend != "fal" else "fal",
                     retention="conditional" if backend == "boat" else ("retains" if backend == "fal" else "unknown"))
        return facts
    facts.update(runs=prov, connection=_CONNECTIONS.get(prov), route=_ROUTES.get(prov),
                 retention="retains" if prov == "fal" else ("zdr?" if prov == "openrouter" else "unknown"))
    return facts


# ---------------------------------------------------------------------------------------------------------------------- the purposes
_OR_IMG = ("openrouter:openai/gpt-image-2.5-flare", "openrouter:openai/gpt-image-2.5-sunburst", "openrouter:sourceful/riverflow-v2.5-pro",
           "openrouter:google/gemini-3.1-flash-image", "openrouter:*")
_CHAT = ("chatgpt_plan:gpt-6.1-sol", "anthropic:claude-sonnet-5-5", "openrouter:anthropic/claude-sonnet-5.5")
_VIDEO = ("openrouter:heygen/heygen-video-1", "openrouter:bytedance/seedance-1-5-pro", "openrouter:bytedance/seedance-2.0-mini",
          "openrouter:black-forest-labs/flux-video-edit", "openrouter:black-forest-labs/flux-video-upscale", "higgsfield:seedance_2_0")
_DECIDE = ("openrouter:inception/mercury-decide:free", "openrouter:cloudflare/clef", "openrouter:liquid/d1", "openrouter:perplexity/pplx-decider-v1-27b",
           "openrouter:upstage/solar-decide")
_EMBED_UP = ("openrouter:nvidia/nemotron-3-embed-1b:free", "openrouter:baai/bge-m3", "openrouter:qwen/qwen3-embedding-8b",
             "openrouter:voyageai/voyage-multimodal-3.5", "openrouter:google/gemini-embedding-2")

P = Purpose
_ALL = [
    # ------------------------------------------------------------------------------------------------------------- A. Agents
    P("agent.main", "Main agent", "agents", "text + tools", "private",
      _CHAT + ("openai:local", "mock", "chatgpt_plan:*", "anthropic:*", "openrouter:*"), (), "none",
      note="the shipped chain comes from the settings (provider_prefs)"),
    P("agent.worker", "Swarm workers", "agents", "text + tools, up to 6 at once", "private",
      ("openrouter:deepseek/deepseek-v4.1-flash", "chatgpt_plan:gpt-6.1-sol", "follow:agent.main", "chatgpt_plan:*", "openrouter:*"), (), "none"),
    P("agent.decide", "Decisions judge", "agents", "options in, one choice out", "private", _DECIDE + ("openrouter:*",), _DECIDE),
    P("agent.vision_judge", "Vision judge (view_verify)", "agents", "image + rubric in, JSON verdict out", "private",
      ("chatgpt_plan:gpt-6.1-sol", "openrouter:google/gemini-3.1-flash-image", "follow:agent.main", "openrouter:*")),
    P("agent.dictation", "Dictation", "agents", "audio in, text out", "private", ("openrouter:google/gemini-3.8-flash", "openrouter:*"),
      ("openrouter:google/gemini-3.8-flash",)),
    P("agent.handwriting", "Handwriting", "agents", "image in, text out", "private", ("openrouter:google/gemini-3.1-flash-image", "follow:agent.main")),
    P("agent.voice_live", "Realtime voice", "agents", "audio duplex", "private", ()),
    P("agent.material_script", "Material scripts (MatGen)", "agents", "text in, code out", "public", ("follow:agent.main",) + _CHAT, ("follow:agent.main",)),
    P("agent.cockpit", "Cockpit pane", "agents", "a terminal session", "private", ("local:claude", "local:codex", "local:opencode", "local:shell"), (), "none"),
    P("normalize.judge", "Normalization judge (System One)", "agents", "a normalization step's evidence in, a typed verdict out", "private",
      ("follow:agent.main", "chatgpt_plan:gpt-6.1-sol", "openrouter:anthropic/claude-sonnet-5.5", "openrouter:google/gemini-3.1-flash-image"),
      ("follow:agent.main",), note="the canon lane's typed judge for normalization"),
    # ------------------------------------------------------------------------------------------------------------- B. Images
    P("image.plates", "Plates", "images", "text + 1-3 ordered references in, image out, 4 variants", "private",
      _OR_IMG + ("studio:tripo.image",), (), "chain", {"size": "2880x2880", "template": "plate-4k-crisper"}),
    P("image.mask", "Material-ID masks", "images", "image in, flat colour zones out", "private", _OR_IMG + ("local:material_id",), ()),
    P("image.concept", "Concepts", "images", "text (+ refs) in", "private",
      ("openrouter:black-forest-labs/flux-3-image", "openrouter:bytedance-seed/seedream-5-0-lite", "openrouter:qwen/qwen-image-3") + _OR_IMG, ()),
    P("image.tile", "Seamless tiles", "images", "text in, tileable image out", "public",
      ("openrouter:openai/gpt-image-2.5-flare", "openrouter:google/gemini-3.1-flash-image", "openrouter:recraft/recraft-v4.1-flash", "local:seamless_tile"), ()),
    P("image.reference_sheet", "Reference sheets", "images", "text (+ approved front) in", "private", _OR_IMG,
      ("openrouter:openai/gpt-image-2.5-sunburst",)),
    P("image.anim_start_frame", "Animation start frames", "images", "render in, image out", "private", _OR_IMG, ("openrouter:openai/gpt-image-2.5-flare",)),
    P("image.upscale", "Image upscale", "images", "image in, larger image out", "private", ("local:lanczos", "studio:tripo.image") + _OR_IMG,
      ("local:lanczos",), "any_local"),
    P("image.edit", "Image edits", "images", "image + instruction in", "private", _OR_IMG + ("higgsfield:gpt_image_2_5", "local:repair_texture")),
    P("image.ai_render", "AI Render and Texture Gen views", "images", "clay render in", "private",
      ("follow:image.plates",) + _OR_IMG + ("openrouter:black-forest-labs/flux-3-image",), ("follow:image.plates",),
      note="the Client's image slot with no purpose (HC10): it follows Plates, what ran before Choices"),
    P("image.depth_to_image", "Depth to image", "images", "depth in, image out", "private", ()),
    # ------------------------------------------------------------------------------------------------------------- C. Video
    P("video.bulk", "Bulk clips", "video", "prompt + frames in", "private", _VIDEO, ()),
    P("video.loop", "Loops", "video", "one image in, first frame = last", "private", _VIDEO, ()),
    P("video.motion", "Motion transfer", "video", "image + driving video in", "private",
      _VIDEO + ("higgsfield:hf_mult_motion_control", "higgsfield:kling3_0_motion_control"), ()),
    P("video.edit", "Video edits", "video", "video + text in", "private", _VIDEO, ()),
    P("video.upscale", "Video upscale", "video", "one video in", "private", _VIDEO, ()),
    P("video.side_track", "Animation clips", "video", "reference image (+ driver clip) in", "private",
      ("higgsfield:seedance_2_0", "openrouter:bytedance/seedance-2.0-mini", "openrouter:heygen/heygen-video-1"), ("higgsfield:seedance_2_0",)),
    P("video.turntable", "Turntables", "video", "image or mesh in", "private",
      ("openrouter:bytedance/seedance-1-5-pro", "local:workbench", "local:eevee"), ("openrouter:bytedance/seedance-1-5-pro",), "any_local"),
    # ------------------------------------------------------------------------------------------------------------- D. 3D
    P("3d.image_to_3d", "Image to 3D", "3d", "1 image in, mesh out", "private",
      ("local:visual_hull", "local:extrude", "local:relief", "studio:tripo.mesh", "studio:meshy.image_to_3d", "studio:hi3d.image_to_3d",
       "studio:hyper3d.generate", "studio:hyper3d.mcp.generate", "studio:tripo.rest.image_to_model"), ("local:visual_hull",), "any_local"),
    P("3d.multiview_to_3d", "Multi-view to 3D", "3d", "2-4 ordered views in, mesh out", "private",
      ("studio:tripo.mesh", "studio:meshy.multi_image_to_3d", "studio:hi3d.image_to_3d", "studio:hyper3d.generate", "studio:hyper3d.mcp.generate",
       "local:visual_hull"), ("studio:tripo.mesh",), "any_local"),
    P("3d.text_to_3d", "Text to 3D", "3d", "text in, mesh out", "public", ("studio:meshy.text_to_3d", "studio:hyper3d.generate", "studio:hyper3d.mcp.generate")),
    P("3d.texture", "Texture on our mesh", "3d", "mesh + UVs + plates in", "private",
      ("local:texture_gen", "studio:tripo.texture", "studio:meshy.retexture", "studio:hyper3d.texture_only", "studio:hi3d.texture_only",
       "studio:tripo.rest.texture"), ("local:texture_gen",), "any_local"),
    P("3d.pbr", "PBR maps", "3d", "textured mesh in", "private", ("local:pbr_merge", "local:pbr_pack", "studio:tripo.pbr"), ("local:pbr_merge",), "any_local"),
    P("3d.retopo", "Retopology", "3d", "mesh in", "private", ("local:quadriflow", "local:voxel", "local:autoremesher", "studio:meshy.remesh",
                                                                 "studio:tripo.rest.decimate"), ("local:quadriflow", "local:voxel"), "any_local"),
    P("3d.uv", "UV unwrap", "3d", "mesh in", "private", ("local:smart", "local:angle", "local:conformal", "studio:tripo.uv.unwrap", "studio:meshy.uv_unwrap"),
      ("local:smart",), "any_local"),
    P("3d.rig", "Auto rig", "3d", "mesh in", "private", ("local:heat_map", "local:proximity"), ("local:heat_map",), "any_local"),
    P("3d.segment_mesh", "Mesh parts", "3d", "mesh in", "private", ("local:shells", "local:sharp", "local:uv_islands", "local:transfer_parts",
                                                                       "studio:hyper3d.bang", "studio:hyper3d.mcp.generate_bang", "studio:hi3d.split"),
      ("local:shells",), "any_local"),
    P("3d.segment_image", "Image part masks", "3d", "image in, masks out", "private", ("local:alpha_components", "local:color_regions"),
      ("local:alpha_components",), "any_local"),
    P("3d.relief", "Relief maps", "3d", "image in, depth PNG out", "private", ("local:relief", "studio:tripo.relief"), ("local:relief",), "any_local"),
    P("3d.animate", "Retarget and animate", "3d", "rig + motion in", "private", ("local:matrix", "local:constraints"), ("local:matrix",), "any_local"),
    P("scene.generate", "Scene generation", "3d", "image or text in", "private", ()),
    # ------------------------------------------------------------------------------------------------------------- E. Embeddings
    P("embed.text_doc", "Documents", "embeddings", "text in, vector out", "private", ("local:bge-small-en-v1.5",) + _EMBED_UP, ("local:bge-small-en-v1.5",), "any_local"),
    P("embed.text_query", "Queries", "embeddings", "text in, vector out", "private", ("local:clip-vit-b-32",) + _EMBED_UP, ("local:clip-vit-b-32",), "any_local"),
    P("embed.image_look", "Images by look", "embeddings", "image in, vector out", "private", ("local:clip-vit-b-32", "openrouter:voyageai/voyage-multimodal-3.5"),
      ("local:clip-vit-b-32",), "any_local"),
    P("embed.text_to_image", "Text to image search", "embeddings", "text in, image vectors", "private",
      ("local:clip-vit-b-32", "openrouter:voyageai/voyage-multimodal-3.5", "openrouter:google/gemini-embedding-2"), ("local:clip-vit-b-32",), "any_local"),
    P("embed.video_keyframes", "Video by keyframes", "embeddings", "frames in, vector out", "private", ("deterministic:video_kf_hist",),
      ("deterministic:video_kf_hist",), "any_local"),
    P("embed.mesh_views", "Meshes by views", "embeddings", "views in, vector out", "private", ("deterministic:shape_d2",), ("deterministic:shape_d2",), "any_local"),
    P("embed.prompt_template", "Prompt templates", "embeddings", "text in, vector out", "public",
      ("local:bge-small-en-v1.5", "openrouter:nvidia/nemotron-3-embed-1b:free", "openrouter:qwen/qwen3-embedding-8b", "openrouter:baai/bge-m3"),
      ("local:bge-small-en-v1.5",), "any_local"),
    P("embed.asset_search_legacy", "Asset search (client tab)", "embeddings", "images in, search out", "private", ("local:asset_index",), ("local:asset_index",), "any_local"),
    # ------------------------------------------------------------------------------------------------------------- F. Tracking and motion
    P("track.body_2d", "2D body keypoints", "tracking", "frames in, 15 joints out", "private", ("local:rtmw",)),
    P("track.body_3d", "Video to body motion", "tracking", "clip + masks in", "private",
      ("local:anim_multiview_fit", "higgsfield:sam_3_3d_body", "fal:fal-ai/sam-3/3d-body", "local:sam3d_body"), (), note="BUILD_ORDER decision 2 is the captain's"),
    P("motion.text_to_motion", "Text to motion", "tracking", "text in, motion out", "public", (), note="BUILD_ORDER decision 5 is the captain's"),
    # ------------------------------------------------------------------------------------------------------------- G. Compute
    P("compute.blender_offload", "Headless Blender jobs", "compute", "files in", "private",
      ("compute:boat", "compute:modal", "compute:runpod", "compute:fal", "local:render_worker"), (), note="CH6: nothing is pre-chosen"),
    P("compute.gpu_model", "Hosted GPU models", "compute", "per recipe", "private", ("compute:modal", "compute:runpod", "compute:fal"), (),
      note="cloud D4 is the captain's"),
    # ------------------------------------------------------------------------------------------------------------- H. Prompts, looks, surfaces
    P("prompt.default_template", "Default prompt templates", "prompts", "a template per purpose", "public", ("local:prompt_library",), ("local:prompt_library",), "any_local"),
    P("look.ue_profile", "UE Look profile", "prompts", "a profile per project", "public", ("local:engine_defaults",), ("local:engine_defaults",), "any_local"),
    P("cockpit.terminal", "Cockpit terminal", "prompts", "where cockpit panes are shown", "public", ("local:browser", "local:wezterm"), ("local:browser",), "any_local"),
]
PURPOSES = {p.id: p for p in _ALL}
COSTLY_PREFIXES = ("openrouter:", "higgsfield:", "fal:", "studio:", "compute:", "anthropic:")


# A prompt template's ``purpose`` (prompts/prompt_template.schema.json) -> the Choices purpose whose choice runs it (CH5).
TEMPLATE_PURPOSES = {"plate": "image.plates", "albedo": "image.plates", "texture-plate": "image.plates", "material-id": "image.mask",
                     "concept": "image.concept", "tile": "image.tile", "character-reference": "image.reference_sheet",
                     "character-sheet": "image.reference_sheet", "character-part": "image.reference_sheet",
                     "anim-start-frame": "image.anim_start_frame", "anim-walk": "video.side_track", "anim-split": "video.side_track",
                     "articulation": "video.side_track", "anim-loop": "video.loop", "anim-motion-transfer": "video.motion", "turntable": "video.turntable"}


def offers(purpose: Purpose, oid: str) -> bool:
    """An option this purpose offers: listed, or of a provider whose catalogue the purpose takes whole (``openrouter:*``)."""
    if oid in purpose.options:
        return True
    prov, sep, model = oid.partition(":")
    return bool(sep and model and model != "*" and f"{prov}:*" in purpose.options)


def listed(purpose: Purpose) -> tuple:
    """The named options (a family pattern is not an option the UI can show)."""
    return tuple(o for o in purpose.options if not o.endswith(":*"))


class UnknownPurpose(KeyError):
    def __str__(self):
        return self.args[0]


def get(pid: str) -> Purpose:
    p = PURPOSES.get(pid)
    if p is None:
        raise UnknownPurpose(f"no purpose {pid}: the purposes are {', '.join(sorted(PURPOSES))}")
    return p


def group_label(gid: str) -> str:
    return dict(GROUPS).get(gid, gid)
