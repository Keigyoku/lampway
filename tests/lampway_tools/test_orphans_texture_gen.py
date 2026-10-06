# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""texture_gen additions (specs/mixar_docs/texture_gen.md, specs/wiki/texture_gen.md): a material reference passed second to the image slot, variants per view
picked by silhouette IoU, the result on a COPY (the source keeps its materials), a ledger row per run, a coverage refusal before anything is paid, and de-lighting.
REAL binary; the image slot and the ledger door are replaced by recording fakes."""

import hashlib
import json

from features_support import run

FAKES = '''
from mixar.modules.lampway_tools.features import texture as T
from PIL import Image
import io
calls, rows = [], []
def png(im):
    b = io.BytesIO(); im.save(b, "PNG"); return b.getvalue()
def fake_image(prompt, reference_png, count=1, extra_references=None):
    calls.append({"prompt": prompt, "count": count, "extra": [hashlib.sha256(x).hexdigest() for x in (extra_references or [])]})
    clay = Image.open(io.BytesIO(reference_png)).convert("RGBA")
    good = Image.new("RGBA", clay.size, (0, 0, 0, 0)); good.paste((200, 40, 40, 255), mask=clay.split()[3] if clay.mode == "RGBA" else None)
    if (np.asarray(clay)[..., 3] == 255).all():                        # an opaque clay render: the subject differs from the corner colour
        a = np.asarray(clay.convert("RGB")).astype(int); m = np.abs(a - a[0, 0]).sum(axis=2) > 40
        g = np.zeros(a.shape[:2] + (4,), np.uint8); g[m] = (200, 40, 40, 255); good = Image.fromarray(g, "RGBA")
    bad = Image.new("RGBA", clay.size, (0, 0, 0, 0)); bad.paste((40, 40, 200, 255), (clay.size[0] // 3, clay.size[1] // 3, clay.size[0] // 2, clay.size[1] // 2))
    return [png(bad), png(good), png(bad), png(bad)][:count] if count > 1 else [png(good)]
def fake_record(row):
    rows.append(row); return {"id": "r1"}
T.generate_image = fake_image
T.record_run = fake_record
import hashlib
ball = sphere("ball", 0.5, subdiv=4, loc=(0, 0, 0.5))
uv = call("uv_unwrap", object="ball", method="smart")
obj = uv["object"]
'''


def _go(tmp_path, body):
    r = run(tmp_path, FAKES + body)
    assert r.rc == 0, r.out[-2500:]
    return r.results[0]


def test_texture_gen_duplicates_when_keep_original(tmp_path):
    res = _go(tmp_path, '''
src = bpy.data.objects[obj]
before = [m.name for m in src.data.materials]
r = call("texture_gen", object=obj, prompt="red enamel", views=["Front", "Back"], size=96, out_dir="tex/a")
print("RESULT", json.dumps({"r": r, "before": before, "after": [m.name for m in src.data.materials],
                            "copy": [m.name for m in bpy.data.objects[r["object"]].data.materials] if r.get("ok") else None}))
''')
    r = res["r"]
    assert r["ok"] is True and r["object"] == "ball_uv_tex" and r["source"] == "ball_uv", r
    assert res["after"] == res["before"], "the source keeps its materials"
    assert res["copy"] == ["ball_uv_tex_proj"], res


def test_reference_image_is_passed_second(tmp_path):
    res = _go(tmp_path, '''
os.makedirs(root + "/refs", exist_ok=True)
Image.new("RGB", (32, 32), (180, 150, 60)).save(root + "/refs/brass.png")
want = hashlib.sha256(open(root + "/refs/brass.png", "rb").read()).hexdigest()
r = call("texture_gen", object=obj, prompt="brass", views=["Front", "Back"], size=96, out_dir="tex/b", reference_image="refs/brass.png")
print("RESULT", json.dumps({"r": r, "calls": calls, "want": want}))
''')
    assert res["r"]["ok"] is True and all(c["extra"] == [res["want"]] for c in res["calls"]) and len(res["calls"]) == 2, res
    assert "material reference" in res["calls"][0]["prompt"], res["calls"][0]


def test_count_picks_best_iou(tmp_path):
    res = _go(tmp_path, '''
r = call("texture_gen", object=obj, prompt="red", views=["Front", "Back"], size=96, out_dir="tex/c", count=4)
print("RESULT", json.dumps({"r": r, "calls": calls, "files": sorted(os.listdir(root + "/tex/c"))}))
''')
    r = res["r"]
    assert r["ok"] is True and all(c["count"] == 4 for c in res["calls"]), res
    assert r["picks"]["Front"]["variant"] == 2 and r["picks"]["Front"]["iou"] > 0.9 and r["picks"]["Front"]["ious"][0] < 0.5, r["picks"]
    assert "gen_Front_4.png" in res["files"] and r["views"]["Front"].endswith("gen_Front_2.png"), res["files"]


def test_a_ledger_row_is_recorded_for_the_run(tmp_path):
    res = _go(tmp_path, '''
r = call("texture_gen", object=obj, prompt="red", views=["Front", "Back"], size=96, out_dir="tex/d", piece="Helmet1")
atlas = hashlib.sha256(open(r["atlas"], "rb").read()).hexdigest()
print("RESULT", json.dumps({"r": r, "rows": rows, "atlas": atlas}))
''')
    rows = res["rows"]
    assert len(rows) == 1 and res["r"]["ledger"]["recorded"] is True, res
    row = rows[0]
    assert row["piece"] == "Helmet1" and row["stage"] == "texture" and row["studio"] == "local" and row["by"] == "agent", row
    assert res["atlas"] in row["output_hashes"] and len(row["output_hashes"]) == 3 and len(row["reference_hashes"]) == 2, row
    assert row["settings"]["views"] == ["Front", "Back"] and row["settings"]["image_slot"] and row["prompt_hash"], row
    assert row.get("decision") is None, "an agent never chooses a spend result"


def test_low_coverage_is_refused_before_anything_is_paid(tmp_path):
    res = _go(tmp_path, '''
r = call("texture_gen", object=obj, prompt="red", views=["Front"], size=96, out_dir="tex/e")
print("RESULT", json.dumps({"r": r, "calls": calls}))
''')
    assert res["r"]["ok"] is False and "Back/Left/Right" in res["r"]["error"] and res["calls"] == [], res


def test_delight_removes_a_baked_shadow_gradient(tmp_path):
    res = _go(tmp_path, '''
def shaded(prompt, reference_png, count=1, extra_references=None):
    clay = Image.open(io.BytesIO(reference_png)).convert("RGB")
    w, h = clay.size
    a = np.asarray(clay).astype(int); m = np.abs(a - a[0, 0]).sum(axis=2) > 40
    ramp = np.linspace(0.35, 1.0, w)[None, :, None] * np.array([200, 120, 60])[None, None, :]
    g = np.where(m[..., None], ramp, a[0, 0]).clip(0, 255).astype(np.uint8)
    return [png(Image.fromarray(g, "RGB"))]
T.generate_image = shaded
out = {}
for d in (False, True):
    r = call("texture_gen", object=obj, prompt="x", views=["Front", "Back"], size=96, out_dir=f"tex/f{int(d)}", delight=d)
    a = np.asarray(Image.open(r["atlas"]).convert("RGB")).astype(float)
    lum = a.mean(axis=2); sel = lum > 20
    out[str(d)] = float(lum[sel].std() / lum[sel].mean())
print("RESULT", json.dumps(out))
''')
    assert res["True"] < 0.5 * res["False"], res
