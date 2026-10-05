# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""retopo method=autoremesher (resources/retopo_autoremesher.md): an out-of-process Qt-free quad remesher, configured by settings, never by the agent's arguments."""

import os
import stat
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from features_support import run  # noqa: E402

REAL = os.environ.get("LAMPWAY_AUTOREMESHER_BIN", "")


def _stub(tmp_path, body, name="stub.sh"):
    p = tmp_path / name
    p.write_text("#!/bin/bash\n" + body)
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return str(p)


ECHO = '''
while [ $# -gt 0 ]; do case "$1" in --input) IN="$2"; shift 2;; --output) OUT="$2"; shift 2;; *) shift;; esac; done
cp "$IN" "$OUT"
echo "Quads: 0"
'''


@pytest.mark.skipif(not REAL or not Path(REAL).exists(), reason="LAMPWAY_AUTOREMESHER_BIN is not set to a built lampway-quadremesh")
def test_the_real_engine_makes_a_new_all_quad_mesh_near_the_target_and_leaves_the_original(tmp_path):
    r = run(tmp_path, '''
src = sphere("dense", 0.5, subdiv=5)
before = len(src.data.polygons)
res = call("retopo", object="dense", target_faces=600, method="autoremesher")
new = bpy.data.objects.get(res.get("object", ""))
print("RESULT", json.dumps({"res": res, "before": before, "after_src": len(src.data.polygons), "new_faces": len(new.data.polygons) if new else None,
                            "quads": sum(1 for p in new.data.polygons if len(p.vertices) == 4) if new else None, "new_name": new.name if new else None,
                            "files": sorted(os.listdir(os.path.join(root, "retopo")))}))
''', env={"LAMPWAY_AUTOREMESHER_BIN": REAL})
    assert r.rc == 0, r.out[-2500:]
    out = r.results[0]
    res = out["res"]
    assert res["ok"] is True and res["method"] == "autoremesher" and out["new_name"] == "dense_retopo" and out["after_src"] == out["before"]
    assert abs(out["new_faces"] - 600) / 600 < 0.45 and out["quads"] / out["new_faces"] > 0.9, out
    assert res["report"]["max_deviation"] < 0.05 and res["report"]["non_manifold_edges"] == 0, res["report"]
    assert res["engine_report"]["quads"] == out["quads"] and res["has_uv"] is False and "uv_unwrap" in res["note"]
    assert set(out["files"]) >= {"dense.obj", "dense_out.obj"}


def test_an_engine_that_echoes_its_input_fails_the_all_quad_check_the_falsifier(tmp_path):
    stub = _stub(tmp_path, ECHO)
    r = run(tmp_path, '''
sphere("dense", 0.5, subdiv=4)
res = call("retopo", object="dense", target_faces=600, method="autoremesher")
print("RESULT", json.dumps(res))
''', env={"LAMPWAY_AUTOREMESHER_BIN": stub})
    assert r.rc == 0, r.out[-2500:]
    res = r.results[0]
    assert res["ok"] is True and res["report"]["quads"] / res["report"]["faces"] < 0.5          # the real test's assertion (> 0.9) would fail on this


def test_refusals_unconfigured_symmetry_ranges_and_a_target_far_above_the_source(tmp_path):
    stub = _stub(tmp_path, ECHO)
    body = '''
sphere("dense", 0.5, subdiv=2)
out = {}
out["unconfigured"] = call("retopo", object="dense", target_faces=100, method="autoremesher")
print("RESULT", json.dumps(out))
'''
    r = run(tmp_path, body, env={"LAMPWAY_AUTOREMESHER_BIN": ""})
    assert r.rc == 0, r.out[-2000:]
    assert "autoremesher is not configured: set settings autoremesher_bin" in r.results[0]["unconfigured"]["error"]
    r = run(tmp_path, '''
sphere("dense", 0.5, subdiv=2)
out = {"symmetry": call("retopo", object="dense", target_faces=100, method="autoremesher", symmetry=True),
       "sharp": call("retopo", object="dense", target_faces=100, method="autoremesher", sharp_edge=10),
       "adapt": call("retopo", object="dense", target_faces=100, method="autoremesher", adaptivity=1.5),
       "big": call("retopo", object="dense", target_faces=100000, method="autoremesher"),
       "timeout": call("retopo", object="dense", target_faces=100, method="autoremesher", timeout=3)}
print("RESULT", json.dumps(out))
''', env={"LAMPWAY_AUTOREMESHER_BIN": stub})
    d = r.results[0]
    assert "autoremesher has no symmetry option; use quadriflow with symmetry=true" in d["symmetry"]["error"]
    assert "sharp_edge must be between 30 and 180" in d["sharp"]["error"] and "adaptivity must be between 0 and 1" in d["adapt"]["error"]
    assert "exceeds 3x the source" in d["big"]["error"] and "a remesher cannot invent detail" in d["big"]["error"]
    assert d["timeout"]["ok"] is False and "timeout must be between 10 and 3600" in d["timeout"]["error"]


def test_a_sleeping_engine_is_killed_with_its_children_and_named(tmp_path):
    marker = tmp_path / "child_alive"
    stub = _stub(tmp_path, f'(sleep 40; touch {marker}) &\nsleep 40\n')
    r = run(tmp_path, '''
sphere("dense", 0.5, subdiv=2)
import time
t0 = time.time()
res = call("retopo", object="dense", target_faces=100, method="autoremesher", timeout=10)
print("RESULT", json.dumps({"res": res, "seconds": time.time() - t0}))
''', env={"LAMPWAY_AUTOREMESHER_BIN": stub}, timeout=120)
    assert r.rc == 0, r.out[-2000:]
    d = r.results[0]
    assert d["res"]["ok"] is False and "timed out after 10s; lower target_faces or raise timeout" in d["res"]["error"] and d["seconds"] < 25
    import time
    time.sleep(1)
    assert not marker.exists()                       # the whole process group was killed, not only the shell


def test_an_engine_that_fails_is_refused_with_its_last_log_lines_and_falls_back_to_voxel_only_when_asked(tmp_path):
    stub = _stub(tmp_path, 'for i in $(seq 1 30); do echo "log line $i"; done\nexit 4\n')
    r = run(tmp_path, '''
sphere("dense", 0.5, subdiv=3)
a = call("retopo", object="dense", target_faces=200, method="autoremesher")
b = call("retopo", object="dense", target_faces=200, method="autoremesher", fallback=True)
print("RESULT", json.dumps({"a": a, "b": b}))
''', env={"LAMPWAY_AUTOREMESHER_BIN": stub})
    d = r.results[0]
    assert d["a"]["ok"] is False and "log line 30" in d["a"]["error"] and "log line 10" not in d["a"]["error"] and "run lampway_mesh_prep first" in d["a"]["error"]
    assert d["b"]["ok"] is True and d["b"]["method"] == "voxel" and d["b"]["requested_method"] == "autoremesher" and "the voxel remesh was used" in d["b"]["note"]


def test_the_hard_surface_flag_and_the_report_keys_match_quadriflow_without_inventing_a_preference(tmp_path):
    stub = _stub(tmp_path, ECHO)
    r = run(tmp_path, '''
sphere("dense", 0.5, subdiv=3)
a = call("retopo", object="dense", target_faces=200, method="autoremesher", hard_surface=True)
b = call("retopo", object="dense", target_faces=200, method="quadriflow")
print("RESULT", json.dumps({"a": sorted(a["report"]), "b": sorted(b["report"]), "hs": a["engine_report"].get("hard_surface")}))
''', env={"LAMPWAY_AUTOREMESHER_BIN": stub})
    d = r.results[0]
    assert d["a"] == d["b"] and d["hs"] is True
