# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""part_budget_plan and platform_budget_check: an asset against a budget it did not choose (specs/wiki/part_budget_plan.md, platform_budget_check.md).

part_budget_plan proposes no numbers of its own: the table (role and camera distance to triangles and texture size) is the captain's, and a part is looked
up in it. platform_budget_check reads a dated data table of documented platform limits; limits older than STALE_DAYS are flagged stale (a policy
[UNVERIFIED]). Both are read-only. Triangles count every n-gon as n - 2; the texture size is the largest image any of the object's materials uses."""

import datetime

import bpy

from . import common as C

STALE_DAYS = 90
#: platform -> documented limits (None = no documented limit in the sources) and the date they were read
PLATFORMS = {
    "roblox_rigid": {"max_tris": 4000, "max_texture_px": 2048, "watertight": True, "single_mesh": True, "max_weights": None, "cages": False,
                     "retrieved": "2026-10-05", "source": "Roblox rigid accessory docs (resource 0a71fde4e8ba26f1a437): a single watertight mesh, 4k triangles, 2048 texture"},
    "roblox_layered": {"max_tris": 4000, "max_texture_px": 2048, "watertight": False, "single_mesh": False, "max_weights": 4, "cages": True,
                       "retrieved": "2026-10-05", "source": "Roblox layered clothing docs (resource dc2fcbf996ff2a51ac28): 4k triangles, R15 rig, inner/outer cages, up to 4 bone weights per vertex"},
    "ue_static": {"max_tris": None, "max_texture_px": None, "watertight": False, "single_mesh": False, "max_weights": None, "cages": False,
                  "retrieved": "2026-10-05", "source": "no documented limit in the wiki's sources: pass platform=custom with the project's numbers"},
}


def _tris(ob) -> int:
    return sum(len(p.vertices) - 2 for p in ob.data.polygons)


def _texture_px(ob):
    best = None
    for slot in ob.material_slots:
        m = slot.material
        if m is None or not m.use_nodes:
            continue
        for n in m.node_tree.nodes:
            if n.type == "TEX_IMAGE" and n.image is not None and n.image.size[0]:
                best = max(best or 0, int(max(n.image.size)))
    return best


def part_budget_plan(table=None, parts=None):
    if not table:
        raise C.FeatureError("the budget table is the captain's: none is built in (the wiki gives examples only); pass table [{role, camera_distance_m: [min, max], max_tris, texture_px}]")
    roles = sorted({r.get("role") for r in table})
    out = []
    for p in parts or []:
        ob = C.need_object(p.get("object", ""))
        rows = [r for r in table if r.get("role") == p.get("role")]
        if not rows:
            raise C.FeatureError(f"role {p.get('role')!r} is not in the table; its roles are {roles}")
        d = float(p.get("camera_distance_m", 0))
        row = next((r for r in rows if float(r["camera_distance_m"][0]) <= d <= float(r["camera_distance_m"][1])), None)
        if row is None:
            raise C.FeatureError(f"no table row for role {p['role']!r} at {d:g} m; its rows cover {[r['camera_distance_m'] for r in rows]}")
        tris, px = _tris(ob), _texture_px(ob)
        over = max(0, tris - int(row["max_tris"]))
        ok = over == 0 and (px is None or px <= int(row["texture_px"]))
        out.append({"object": ob.name, "role": p["role"], "camera_distance_m": d, "tris": tris, "budget": int(row["max_tris"]), "over_by": over,
                    "texture_px": px, "budget_px": int(row["texture_px"]), "pass": bool(ok)})
    if not out:
        raise C.FeatureError("give the parts: [{object, role, camera_distance_m}]")
    return {"parts": out, "pass": all(r["pass"] for r in out),
            "note": "post-processing budgets only: Tripo generation runs at maximum polycount by the captain's law; retopo/P2 meet these"}


def _report(ob):
    rep = C.mesh_report(ob)
    weights = 0
    names = {g.index: g.name for g in ob.vertex_groups}
    for v in ob.data.vertices:
        weights = max(weights, sum(1 for e in v.groups if e.weight > 0 and e.group in names))
    return rep, weights


def platform_budget_check(object, platform, limits=None):
    ob = C.need_object(object)
    if platform == "custom":
        if not isinstance(limits, dict) or not limits:
            raise C.FeatureError("platform custom needs limits {max_tris, max_texture_px, watertight, max_weights, retrieved (the date you read them)}")
        lim = {"max_tris": None, "max_texture_px": None, "watertight": False, "single_mesh": False, "max_weights": None, "cages": False,
               "retrieved": None, "source": "the caller's table", **limits}
    elif platform in PLATFORMS:
        lim = PLATFORMS[platform]
    else:
        raise C.FeatureError(f"unknown platform {platform!r}; the platforms are {', '.join(list(PLATFORMS) + ['custom'])}")
    rep, weights = _report(ob)
    checks = []
    if lim.get("max_tris") is not None:
        checks.append({"name": "tris", "value": _tris(ob), "limit": lim["max_tris"], "pass": _tris(ob) <= lim["max_tris"]})
    px = _texture_px(ob)
    if lim.get("max_texture_px") is not None:
        checks.append({"name": "texture_px", "value": px, "limit": lim["max_texture_px"], "pass": px is None or px <= lim["max_texture_px"]})
    if lim.get("watertight"):
        tight = rep["open_boundary_edges"] == 0 and rep["non_manifold_edges"] == 0
        checks.append({"name": "watertight", "value": {"open_boundary_edges": rep["open_boundary_edges"], "non_manifold_edges": rep["non_manifold_edges"]},
                       "limit": "0 and 0", "pass": tight})
    if lim.get("single_mesh"):
        checks.append({"name": "single_mesh", "value": rep["shells"], "limit": 1, "pass": rep["shells"] == 1})
    if lim.get("max_weights") is not None:
        checks.append({"name": "max_weights", "value": weights, "limit": lim["max_weights"], "pass": weights <= lim["max_weights"]})
    if lim.get("cages"):
        cages = [f"{ob.name}_InnerCage", f"{ob.name}_OuterCage"]
        checks.append({"name": "cages", "value": [c for c in cages if c in bpy.data.objects], "limit": cages, "pass": all(c in bpy.data.objects for c in cages),
                       "note": "cage names follow the platform's _InnerCage / _OuterCage convention [UNVERIFIED]"})
    stale = None
    if lim.get("retrieved"):
        age = (datetime.date.today() - datetime.date.fromisoformat(str(lim["retrieved"]))).days
        stale = age > STALE_DAYS
    return {"object": ob.name, "platform": platform, "limits_retrieved": lim.get("retrieved"), "stale": stale,
            "stale_note": f"the limits were read {lim.get('retrieved')}: re-read the platform's documentation before relying on them" if stale else "",
            "source": lim.get("source"), "checks": checks, "pass": all(c["pass"] for c in checks)}
