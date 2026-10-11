# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Native terminal finger helpers never substitute for an anatomical next joint."""
import pytest
from blender_run import run_script
from test_canon_normalize_rigged import PRE, RIG


@pytest.mark.parametrize("tags", [("bulge", "half"), ("half",)])
def test_terminal_finger_auxiliaries_keep_canonical_leaf_direction(tags):
    r = run_script(PRE + RIG + "TAGS=" + repr(tags) + r'''
import numpy as np
from mixar.modules.lampway_tools.canon_geom.bones import bone_segments, CONTINUATION, LEAF
for side,sign in (("l",1),("r",-1)):
    for i,finger in enumerate(("thumb","index","middle","ring","pinky")):
        for n in (1,2,3):
            b=f"{finger}_{n:02d}_{side}"
            J[b]=(sign*(.42+.025*n),.015*(i-2),.60)
            P[b]=f"hand_{side}" if n==1 else f"{finger}_{n-1:02d}_{side}"
        for tag in TAGS:
            b=f"{finger}_03_{tag}_{side}"
            J[b]=(sign*.50,.015*(i-2)+.02,.625);P[b]=f"{finger}_03_{side}"
arm=build("native_terminal_fingers")
before={b.name:[list(r) for r in b.matrix_local] for b in arm.data.bones}
r=api.normalize_rigged(armature=arm.name,profile="metahuman",dry_run=False)
doc=json.loads(arm["lw_canon"]) if "lw_canon" in arm.keys() else {}
rows={b["name"]:b for b in doc.get("body",{}).get("bones",[])}
heads={b.name:tuple(b.head_local) for b in arm.data.bones}
parents={b.name:b.parent.name if b.parent else None for b in arm.data.bones}
segments=bone_segments(heads,parents,main_child=CONTINUATION) if r.get("ok") else {}
checks=[]
for side,sign in (("l",1),("r",-1)):
    for finger in ("thumb","index","middle","ring","pinky"):
        name=f"{finger}_03_{side}"
        if name in rows:
            row=rows[name];h,e=segments[name]
            expected=h+LEAF*(h-segments[f"{finger}_02_{side}"][0])
            checks.append({"source":row["along_source"],"along":row["along"],"sign":sign,"error":float(np.linalg.norm(e-expected))})
res({"result":r,"checks":checks,"unchanged":before=={b.name:[list(r) for r in b.matrix_local] for b in arm.data.bones},"errors":CA.validate(doc) if doc else ["no doc"]})
''', timeout=300)
    assert r.rc == 0, r.out[-2500:]
    got = r.results[-1]
    assert got["result"]["ok"], got["result"]
    assert got["unchanged"] and not got["errors"]
    assert len(got["checks"]) == 10
    for row in got["checks"]:
        assert row["source"] == "leaf_parent_line"
        assert abs(row["along"][0]-row["sign"]) < 1e-6
        assert row["error"] < 1e-12


@pytest.mark.parametrize("unknown", ["pinky_04_l", "pinky_03_unknown_l", "index_03_half_l"])
def test_terminal_finger_unknown_child_is_refused(unknown):
    r = run_script(PRE + RIG + "UNKNOWN=" + repr(unknown) + r'''
from mixar.modules.lampway_tools.canon_geom.bones import chain_ends, CONTINUATION
heads={"pinky_02_l":(0,0,0),"pinky_03_l":(1,0,0),"pinky_03_half_l":(1,1,0),UNKNOWN:(1,0,1)}
parents={"pinky_02_l":None,"pinky_03_l":"pinky_02_l","pinky_03_half_l":"pinky_03_l",UNKNOWN:"pinky_03_l"}
try:
    chain_ends(heads,parents,main_child=CONTINUATION);out={"refused":False}
except ValueError as e: out={"refused":True,"error":str(e)}
res(out)
''', timeout=300)
    assert r.rc == 0, r.out[-2500:]
    got = r.results[-1]
    assert got["refused"] and "pinky_03_l" in got["error"]
