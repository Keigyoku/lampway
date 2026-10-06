# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""layered_material (specs/mixar_docs/layered_material.md): the Client's layer-paint stack from the agent: init, inspect, add fill / paint / image / group layers (with an edge-detect, colour-ID, vertex-colour or image
mask), procedural layers from the library, parameter edits and manifests. A thin, VALIDATED wrapper over the paint package's own agent_tools (`paint/core/agent_tools`) and its layer operator: no new
algorithm. Mask invert is the package's own INVERT mask modifier (the helper its wm.m_new_mask_modifier operator calls, then the layer's nodes are rearranged and reconnected as the operator
does): ``mask.invert`` on add_layer, or action mask_invert {invert} on a layer's first mask (one modifier, toggled by its enable). Not built: curvature-baked masks (use mask type edge_detect), and
manifests whose base layer downloads map URLs are the builder's (offline path unverified)."""

import bpy

from . import common as C

ACTIONS = ("init", "inspect", "set_params", "add_layer", "add_procedural", "apply_manifest", "mask_invert")
BLENDS = ("MIX", "ADD", "MULTIPLY", "SUBTRACT", "SCREEN", "OVERLAY")
TYPES = {"fill": "COLOR", "paint": "IMAGE", "image": "IMAGE", "group": "GROUP", "procedural": "PROCEDURAL"}
MASKS = ("EDGE_DETECT", "COLOR_ID", "VCOL", "IMAGE")
PROJECTIONS = ("UV", "TRIPLANAR", "PLANAR", "SPHERICAL", "CYLINDRICAL", "DECAL")


def _agent_tools():
    from mixar.modules.paint.core import agent_tools as AT
    from mixar.modules.paint.core.agent_tools import _common as CM
    return AT, CM


def _mesh(name):
    ob = bpy.data.objects.get(name or "")
    if ob is None:
        raise C.FeatureError(f"no object named {name!r}; the meshes are {sorted(o.name for o in bpy.data.objects if o.type == 'MESH')}")
    if ob.type != "MESH":
        raise C.FeatureError(f"{name} is not a mesh ({ob.type}): the layer stack lives on a mesh's material")
    return ob


def _row(i, l):
    ch = [c["name"] for c in l.get("channels", []) if c.get("enabled")]
    masks = l.get("masks") or []
    return {"index": i, "name": l.get("name"), "type": l.get("type"), "enabled": l.get("enabled"), "blend": l.get("blend_type"), "opacity": l.get("opacity"), "channels": ch,
            "mask": ({"type": masks[0]["type"], "name": masks[0]["name"], "blend": masks[0].get("blend_type")} if masks else None), "masks": len(masks)}


def _stack(ob):
    AT, _CM = _agent_tools()
    r = AT.inspect_paint_layer_stack(ob.name)
    if not r.get("success"):
        raise C.FeatureError("initialise a layer paint project first (lampway_layered_material action=init): " + str(r.get("error") or ""))
    return r


def _mp(ob):
    _AT, CM = _agent_tools()
    node = CM._find_mpaint_node(ob)
    return node.node_tree.mp if node is not None else None


def _inverted(mask) -> bool:
    return any(m.type == "INVERT" and m.enable for m in mask.modifiers)


def set_mask_invert(ob, index, invert):
    """The paint package's INVERT mask modifier on the layer's first mask: added once (its own helper, then the operator's rearrange/reconnect), toggled by enable."""
    from mixar.modules.paint.core.io.arrangements.layer_arrangements import rearrange_layer_nodes
    from mixar.modules.paint.core.io.connections.layer_connections import reconnect_layer_nodes
    from mixar.modules.paint.ui.mask_modifier.mask_modifier_operators_helpers import add_new_mask_modifier
    mp = _mp(ob)
    if mp is None:
        raise C.FeatureError("initialise a layer paint project first (lampway_layered_material action=init)")
    i = int(index) if int(index) >= 0 else mp.active_layer_index
    if not 0 <= i < len(mp.layers):
        raise C.FeatureError(f"no layer {index}: the stack has {len(mp.layers)} layers")
    layer = mp.layers[i]
    if not len(layer.masks):
        raise C.FeatureError(f"layer {i} ({layer.name}) has no mask to invert: add the layer with a mask first")
    mask = layer.masks[0]
    mods = [m for m in mask.modifiers if m.type == "INVERT"]
    if invert and not mods:
        add_new_mask_modifier(mask, "INVERT")
        rearrange_layer_nodes(layer)
        reconnect_layer_nodes(layer)
        mods = [m for m in mask.modifiers if m.type == "INVERT"]
    for m in mods:
        m.enable = bool(invert)
    return i


def _out(ob, extra=None):
    r = _stack(ob)
    mp = _mp(ob)
    res = {"ok": True, "object": ob.name, "material": r.get("material_name"), "stack": [_row(i, l) for i, l in enumerate(r["layers"])], "active_layer_index": r.get("active_layer_index")}
    for row in res["stack"]:
        if row["mask"] is not None and mp is not None and row["index"] < len(mp.layers) and len(mp.layers[row["index"]].masks):
            row["mask"]["invert"] = _inverted(mp.layers[row["index"]].masks[0])
    res.update(extra or {})
    return res


def _validate_layer(layer):
    t = str(layer.get("type") or "fill").lower()
    if t not in TYPES:
        raise C.FeatureError(f"unknown layer type {t!r}: the types are {sorted(TYPES)}")
    blend = str(layer.get("blend") or "MIX").upper()
    if blend not in BLENDS:
        raise C.FeatureError(f"unknown blend {blend!r}: the blends are {', '.join(BLENDS)}")
    mask = layer.get("mask")
    mt = None
    if mask:
        mt = str(mask.get("type") or "").upper()
        if mt not in MASKS:
            raise C.FeatureError(f"unknown mask type {mt!r}: the masks are {', '.join(MASKS)}")
    proj = layer.get("projection")
    if proj is not None and str(proj).upper() not in PROJECTIONS:
        raise C.FeatureError(f"unknown projection {proj!r}: {', '.join(p.lower() for p in PROJECTIONS)}")
    op = layer.get("opacity")
    if op is not None and not 0.0 <= float(op) <= 1.0:
        raise C.FeatureError("opacity is 0..1")
    return t, blend, mt, (str(proj).upper() if proj is not None else None)


def layered_material(action="inspect", object=None, material=None, layer=None, manifest=None, layer_index=-1, params=None):  # noqa: A002
    if action not in ACTIONS:
        raise C.FeatureError(f"action is one of {list(ACTIONS)}")
    AT, CM = _agent_tools()
    if action == "apply_manifest":
        from mixar.modules.paint.layered_build import manifest as MF
        try:
            MF.validate_manifest(manifest or {})
        except MF.ManifestError as exc:
            raise C.FeatureError(str(exc))
        ob = _mesh(object)
        r = AT.apply_layered_material_manifest(manifest, [ob.name])
        if not r.get("success"):
            raise C.FeatureError("the manifest could not be applied: " + str(r.get("errors") or r.get("error")))
        return _out(ob, {"applied": r.get("applied")})
    ob = _mesh(object)
    if action == "init":
        r = AT.initialize_layer_paint_project([ob.name], material_name=material or "")
        if not r.get("success"):
            raise C.FeatureError("init failed: " + str(r.get("errors") or r.get("error")))
        return _out(ob, {"initialised": bool(r.get("initialized")), "already_initialised": bool(r.get("already_initialized"))})
    if action == "inspect":
        return _out(ob)
    if action == "set_params":
        _stack(ob)
        r = AT.set_paint_layer_parameters(ob.name, int(layer_index), dict(params or {}))
        if not r.get("success"):
            raise C.FeatureError("the edit failed: " + str(r.get("error")))
        return _out(ob, {"changed": r.get("changed")})
    if action == "mask_invert":
        _stack(ob)
        i = set_mask_invert(ob, layer_index, bool((params or {}).get("invert", True)))
        return _out(ob, {"layer_index": i})
    if action == "add_procedural":
        from . import procedural_library as PL
        mid = material or (layer or {}).get("material_id")
        PL._need(mid or "")
        PL.seed(_root())
        r = AT.add_procedural_material_layer(material_id=mid, object_names=[ob.name], layer_name=(layer or {}).get("name") or "")
        if not r.get("success"):
            raise C.FeatureError("the procedural layer could not be added: " + str(r.get("error") or r.get("errors")))
        return _out(ob, {"material_id": mid})
    # add_layer
    t, blend, mt, proj = _validate_layer(layer or {})
    st = _stack(ob)
    before = [l["name"] for l in st["layers"]]
    if proj == "UV" and not ob.data.uv_layers:
        raise C.FeatureError("this mesh has no UV map: use projection triplanar or unwrap first")
    CM._activate_object(ob)
    name = (layer or {}).get("name") or ""
    if t == "group":
        res = bpy.ops.layers.add_layer_group("EXEC_DEFAULT")
    else:
        size = int((layer or {}).get("size") or 1024)
        kw = {"type": TYPES[t], "name": name, "add_mask": mt is not None}
        if t == "fill":
            kw["solid_color"] = tuple(float(x) for x in ((layer or {}).get("color") or (1.0, 1.0, 1.0)))[:3]
        if t in ("paint", "image"):
            kw.update(width=size, height=size)
        if mt:
            kw["mask_type"] = mt
        res = bpy.ops.wm.m_new_layer("EXEC_DEFAULT", **kw)
    if "FINISHED" not in res:
        raise C.FeatureError(f"the paint package refused the layer ({res})")
    after = AT.inspect_paint_layer_stack(ob.name)["layers"]
    new = next((i for i, l in enumerate(after) if l["name"] not in before), None)
    if new is None:
        raise C.FeatureError("the layer was created but could not be found in the stack")
    updates = {}
    if t == "group" and name:
        updates["name"] = name
    if blend != "MIX":
        updates["blend_type"] = blend
    if (layer or {}).get("opacity") is not None:
        updates["opacity"] = float(layer["opacity"])
    if proj:
        updates["projection_type"] = proj
    if updates:
        AT.set_paint_layer_parameters(ob.name, new, updates)
    if mt and (layer or {}).get("mask", {}).get("invert"):
        set_mask_invert(ob, new, True)
    return _out(ob, {"added_index": new})


def _root():
    from .. import settings as S
    return S.load().project_root
