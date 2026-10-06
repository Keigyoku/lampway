"""The Client's job types backed by Lampway's own tools (STATUS O13; specs/mixar_docs/job_services.md): the mesh jobs run the Lampway tool of that name in a
headless Lampway (LAMPWAY_BLENDER: the app's own binary, niced), on the uploaded file, and answer with the GLB(s). Free and local: nothing is
spent and nothing leaves the machine. Without a binary none of them registers (the tabs stay hidden, the Client's own kill switch).

backed    retopology (retopo, QuadriFlow), hunyuan_uv (uv_unwrap), hunyuan_part / tripo_segment / tripo_smart_segment (segment_mesh shells: one GLB per part with
          its name), tripo_rig (auto_rig: the humanoid armature and the skinned mesh in one GLB), image_to_3d / hunyuan_rapid / model_3d with an image
          (image_to_3d's extrusion of the image: a stand-in shape, not a generated model)
unbacked  each with its reason (UNBACKED_REASONS): the model-only jobs (text-to-3D, PBR generation, scene and world generation), the jobs whose Studio driver
          does not exist (Tripo retopology, Tripo's retarget presets) and the payloads not read (depth_to_image)"""

import base64
import json
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Callable, Optional

from .jobqueue import FilesOutput

UNBACKED_REASONS = {
    "retopology_tripo": "Tripo Studio retopology has no driver (studios/actions.py); the free local retopology is service 'retopology'",
    "tripo_retarget": "Tripo's retarget presets are Tripo's animation library: no driver; Lampway's animation_retarget needs a source animation, not a preset name",
    "mesh_segment": "the Client asks for free-text part labels (description, expected_parts); Lampway labels islands from a recipe (segment_mesh labels), never from a guess",
    "pbr_gen": "PBR generation is a model (hunyuan-pbr); Lampway's PBR route is Tripo PBR on a Smart UV copy (studio_plan tripo.pbr) or bake_maps + pbr_pack",
    "scene_reconstruction": "scene reconstruction (SAM 3D) is a model slot with no provider configured",
    "scene_gen": "parts-to-3D scene generation is a model slot with no provider configured",
    "scene_gen_exp_labels": "its payload was not read (audit/protocol.json) and it needs a generation model",
    "world_labs": "Gaussian-splat world generation is a model (World Labs); Lampway imports splats (splat_import) but does not generate them",
    "depth_to_image": "its payload was not read (audit/protocol.json: 'payloads not read'); AI Render is the agent tool lampway_ai_render",
}
_ROW = lambda label, slug, desc: {"label": label, "surface": "moodboard", "models": [{"slug": slug, "label": desc, "is_default": True, "max_reference_images": 0, "parameters": {}}]}  # noqa: E731

SCRIPT = r'''
import bpy, json, os, sys
a = json.loads(open(sys.argv[sys.argv.index("--") + 1]).read())
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o)
from mixar.modules.lampway_tools import api
src, op, p, out = a["input"], a["op"], a["params"], a["out"]
res = {"files": [], "report": {}}
def imported():
    ext = os.path.splitext(src)[1].lower()
    if ext not in (".glb", ".gltf", ".obj", ".fbx"):
        raise SystemExit("unsupported mesh file " + ext)
    from mixar.modules.lampway_tools import canon_io          # the one importer: the job file lands stamped lw_raw
    canon_io.import_raw(src)
    ms = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if not ms:
        raise SystemExit("no mesh in the file")
    for o in bpy.context.view_layer.objects:
        o.select_set(o in ms)
    bpy.context.view_layer.objects.active = ms[0]
    if len(ms) > 1:
        bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    return ob.name
def export(objs, name):
    for o in bpy.context.view_layer.objects:
        o.select_set(o.name in objs)
    path = os.path.join(out, name)
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True)
    res["files"].append([path, name])
if op == "image_to_3d":
    r = api.image_to_3d(images={"Front": src}, mode="extrude", name="lw_job_mesh")
    if not r.get("ok"):
        raise SystemExit(r.get("error"))
    export([r["object"]], "mesh.glb")
else:
    name = imported()
    if op == "retopo":
        # a GLB splits vertices at UV seams and QuadriFlow refuses the split mesh ("Remeshing failed"; the tool no longer falls back
        # to voxel silently): weld by position at the canon's distance first (canon 01, a generated mesh is welded) and say so
        import bmesh
        from mixar.modules.lampway_tools.canon_geom import WELD_M
        me = bpy.data.objects[name].data
        n0 = len(me.vertices)
        bm = bmesh.new(); bm.from_mesh(me); bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=WELD_M); bm.to_mesh(me); bm.free()
        res["welded_vertices"] = n0 - len(me.vertices)
        r = api.retopo(object=name, target_faces=int(p.get("target_faces", 2000)))
    elif op == "uv":
        r = api.uv_unwrap(object=name)
    elif op == "parts":
        r = api.segment_mesh(object=name, method="shells")
    elif op == "rig":
        r = api.auto_rig(object=name)
    else:
        raise SystemExit("unknown op " + op)
    if not r.get("ok"):
        raise SystemExit(r.get("error"))
    if op == "parts":
        coll = bpy.data.collections.get(r.get("collection") or name + "_parts")
        names = []
        for i, o in enumerate(sorted(coll.objects, key=lambda o: o.name)):
            export([o.name], f"part_{i + 1:02d}.glb")
            names.append(o.name)
        res["part_names"] = names
    elif op == "rig":
        export([r["armature"], r["mesh"]], "rigged.glb")
    else:
        export([r["object"]], "result.glb")
    res["report"] = r.get("report") or {}
print("LWJOB " + json.dumps(res, default=str))
'''


def blender_binary(env=None) -> Optional[str]:
    env = os.environ if env is None else env
    p = env.get("LAMPWAY_BLENDER")                    # the launcher's setting (the app's own binary); LAMPWAY_BIN is the test suites' and is not read here
    return p if p and Path(p).exists() else None


class BlenderRun:
    """op + an input file + params -> {files: [(bytes, name)], report, part_names?}: one headless Lampway process per job, niced, in its own 0700 directory."""

    def __init__(self, binary: str, work: Path, timeout: float = 1800.0):
        self.binary, self.work, self.timeout = binary, Path(work), timeout

    def _dir(self):
        d = self.work / f"lwjob-{uuid.uuid4().hex[:10]}"
        d.mkdir(parents=True, mode=0o700)
        return d

    def __call__(self, op, input_path, params):
        d = self._dir()
        try:
            (d / "out").mkdir()
            args = d / "args.json"
            args.write_text(json.dumps({"op": op, "input": str(input_path), "params": params or {}, "out": str(d / "out")}))
            script = d / "job.py"
            script.write_text(SCRIPT)
            env = dict(os.environ, LAMPWAY_PROJECT_ROOT=str(d), LAMPWAY_BRIDGE_PORT="0", XDG_CONFIG_HOME=str(d / "xdg"))
            p = subprocess.run(["nice", "-n", "15", self.binary, "-b", "--python-exit-code", "1", "-P", str(script), "--", str(args)],
                               capture_output=True, text=True, timeout=self.timeout, env=env)
            line = next((l for l in (p.stdout or "").splitlines() if l.startswith("LWJOB ")), None)
            if p.returncode != 0 or line is None:
                tail = ((p.stdout or "") + (p.stderr or "")).strip().splitlines()[-3:]
                raise RuntimeError("the headless Lampway job failed: " + " | ".join(tail)[:600])
            res = json.loads(line[len("LWJOB "):])
            res["files"] = [(Path(path).read_bytes(), name) for path, name in res["files"]]
            return res
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def make_test_glb(self, path):
        """A UV sphere as a GLB (for the real-run test): the same binary, a one-line scene."""
        script = Path(self.work) / f"mk-{uuid.uuid4().hex[:6]}.py"
        script.write_text(f"import bpy\nfor o in list(bpy.data.objects): bpy.data.objects.remove(o)\nbpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24)\n"
                          f"bpy.ops.export_scene.gltf(filepath={str(path)!r}, export_format='GLB')\n")
        subprocess.run(["nice", "-n", "15", self.binary, "-b", "--python-exit-code", "1", "-P", str(script)], capture_output=True, text=True, timeout=600,
                       env=dict(os.environ, LAMPWAY_BRIDGE_PORT="0"), check=True)
        script.unlink()
        return path


def _decode(payload, *keys):
    for k in keys:
        node = payload
        for part in k.split("."):
            node = node.get(part) if isinstance(node, dict) else None
        if node:
            return node
    return None


def _job(run: Callable, op: str, b64_keys, name_keys, default_name, params_of=lambda p: {}, kind="GLB"):
    def backend(model, payload):
        payload = payload if isinstance(payload, dict) else {}
        data = _decode(payload, *b64_keys)
        if not data:
            if op == "image_to_3d" and payload.get("prompt"):
                raise ValueError("text-to-3D needs a model: Lampway builds a shape from an IMAGE only (send image_bytes_b64)")
            raise ValueError(f"no mesh or image in the payload (expected one of {', '.join(b64_keys)})")
        name = os.path.basename(str(_decode(payload, *name_keys) or default_name)) or default_name
        with tempfile.TemporaryDirectory(prefix="lwjob-in-") as tmp:
            path = Path(tmp) / name
            path.write_bytes(base64.b64decode(data))
            res = run(op, str(path), params_of(payload))
        extra = {"provider": "lampway-local", "tool": op, "report": res.get("report") or {}}
        if res.get("part_names"):
            extra["part_names"] = res["part_names"]
        return FilesOutput(files=[(b, "model/gltf-binary", n) for b, n in res["files"]], kind=kind, extra=extra)
    backend.__name__ = f"lampway_local_{op}"
    return backend


def _faces(payload):
    p = payload.get("params") or {}
    level = str(p.get("face_level") or "").lower()
    return {"target_faces": int(p.get("face_limit") or {"low": 2000, "medium": 8000, "high": 20000}.get(level, 2000))}


def register_local(registry, run: Callable) -> list:
    mesh_keys, mesh_names = ("file_bytes_b64", "rig.file_bytes_b64"), ("file_filename", "rig.file_filename")
    img_keys, img_names = ("image_bytes_b64",), ("image_filename",)
    rows = [
        ("retopology", _job(run, "retopo", mesh_keys, mesh_names, "mesh.glb", _faces), _ROW("Retopology", "lampway_quadriflow", "Lampway QuadriFlow (local, free)")),
        ("hunyuan_uv", _job(run, "uv", mesh_keys, mesh_names, "mesh.glb"), _ROW("Auto UV", "lampway_smart_uv", "Lampway Smart UV (local, free)")),
        ("hunyuan_part", _job(run, "parts", mesh_keys, mesh_names, "mesh.glb"), _ROW("Parts", "lampway_shells", "Lampway shells (local, free)")),
        ("tripo_segment", _job(run, "parts", mesh_keys, mesh_names, "mesh.glb"), _ROW("Segment", "lampway_shells", "Lampway shells (local, free)")),
        ("tripo_smart_segment", _job(run, "parts", mesh_keys, mesh_names, "mesh.glb"), _ROW("Smart Segment", "lampway_shells", "Lampway shells (local, free)")),
        ("tripo_rig", _job(run, "rig", mesh_keys, mesh_names, "mesh.glb"), _ROW("Auto Rig", "lampway_auto_rig", "Lampway humanoid auto rig (local, free)")),
        ("image_to_3d", _job(run, "image_to_3d", img_keys, img_names, "image.png"), _ROW("Image to 3D", "lampway_extrude", "Lampway extrusion of the image (local, free; a stand-in shape)")),
        ("hunyuan_rapid", _job(run, "image_to_3d", img_keys, img_names, "image.png"), _ROW("Rapid 3D", "lampway_extrude", "Lampway extrusion of the image (local, free; a stand-in shape)")),
        ("model_3d", _job(run, "image_to_3d", img_keys, img_names, "image.png"), _ROW("3D", "lampway_extrude", "Lampway extrusion of the image (local, free; needs an image)")),
    ]
    for key, backend, row in rows:
        registry.register(key, backend, row, spend=False, backend_name="lampway-local")
    return [k for k, _b, _r in rows]


def default_registry(env=None, work=None):
    from .services import ServiceRegistry
    reg = ServiceRegistry()
    binary = blender_binary(env)
    if binary:
        register_local(reg, BlenderRun(binary, Path(work or tempfile.gettempdir())))
    return reg
