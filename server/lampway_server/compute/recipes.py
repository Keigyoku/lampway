"""What runs on the box. A recipe is data: its setup, its entry command, its declared outputs, what hardware it needs. Job types: `probe` (a few facts about the box: the live test), `blender_offload`
(the captain's D8: headless Blender bakes, thumbnails and silhouette refine sent to a box: opt-in, under the caps)."""
from pathlib import Path

from .backend import Recipe

_ASSETS = Path(__file__).resolve().parent / "assets"

RECIPES = {r.id: r for r in (
    Recipe("probe", "1.0.0", setup_seconds_max=20, outputs=("result.json",),
           entry="python3 -c \"import json,os,platform;print(json.dumps({'cpus':os.cpu_count(),'python':platform.python_version(),'inputs':sorted(os.listdir('in')) if os.path.isdir('in') else []}))\" > out/result.json"),
    Recipe("blender_offload", "1.0.0", setup_seconds_max=240, outputs=("result.json",), type="default",
           setup="uv venv -q --python 3.11 .venv && uv pip install -q --python .venv/bin/python bpy numpy",
           entry=".venv/bin/python in/offload.py in out", files=(("offload.py", str(_ASSETS / "offload.py")),), params_file="params.json",
           outputs_by_param=("op", (("thumbnail", ("thumbnail.png",)), ("silhouette", ("silhouette.png",)), ("bake_ao", ("ao.png",))))),
)}


def get(recipe_id: str) -> Recipe:
    try:
        return RECIPES[recipe_id]
    except KeyError:
        raise KeyError(f"no recipe {recipe_id!r}: the recipes are {sorted(RECIPES)}") from None
