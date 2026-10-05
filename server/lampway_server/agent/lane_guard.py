"""The lane guard: the server's enforcement of "a worker touches only its own lane".

Lanes isolate SCENES, not ``bpy.data``: object names are global and a worker's script sees every other lane's objects.
The prompt tells workers not to touch them; this module makes the server check. Every worker script is wrapped so
that, in the SAME main-thread slot (the client runs scripts one at a time, so nothing else can run between the two
halves), the wrapper

  1. fingerprints every object outside the worker's lane scene (name, transform, parent, visibility, collections,
     data block, material slots, modifiers and a hash of the mesh vertices), keyed by the object's pointer so a
     rename is still the same object;
  2. runs the body under ``try`` so the check runs even when the body raises (the error is carried as
     ``body_error`` and the server turns it back into a failed tool result);
  3. compares: a deletion or an edit of geometry/data/materials/modifiers cannot be undone and goes to
     ``unrestored`` (the server fails the worker, and its lane is discarded at collect); a move, rename, re-parent,
     visibility flip or collection change is put back and goes to ``restored``. A worker renaming its OWN object is no
     violation: it is reported in ``renamed_own`` so the worker's created list follows the new name.

The body is spliced in through the AST (never by indenting text), so a body with any string literal survives; a body
that does not parse is returned unchanged for the executor to report.
"""

import ast
import json

GUARD_KEY = "lane_guard"
BODY_ERROR_KEY = "body_error"

_TEMPLATE = r'''
import bpy, json, hashlib, numpy
_lw_lane = bpy.data.scenes.get(__LANE__)
_lw_own = {_o.as_pointer(): _o.name for _o in _lw_lane.collection.all_objects} if _lw_lane is not None else {}
def _lw_fp(_o):
    _d = _o.data
    _geo = ""
    if _o.type == 'MESH' and _d is not None:
        _n = len(_d.vertices)
        if _n:
            _buf = numpy.empty(_n * 3, dtype=numpy.float32)
            _d.vertices.foreach_get('co', _buf)
            _geo = hashlib.sha1(_buf.tobytes()).hexdigest()
        _geo = f"{_n}:{len(_d.polygons)}:{_geo}"
    return {"name": _o.name,
            "loc": [round(float(v), 6) for v in _o.location], "rot": [round(float(v), 6) for v in _o.rotation_euler],
            "scale": [round(float(v), 6) for v in _o.scale],
            "parent": _o.parent.name if _o.parent else None,
            "hide_viewport": bool(_o.hide_viewport), "hide_render": bool(_o.hide_render),
            "data": _d.name if _d is not None else None, "geo": _geo,
            "mats": [s.material.name if s.material else None for s in _o.material_slots],
            "mods": [m.name for m in _o.modifiers],
            "colls": sorted(c.name for c in _o.users_collection)}
_lw_before = {_o.as_pointer(): _lw_fp(_o) for _o in bpy.data.objects if _o.as_pointer() not in _lw_own}
_lw_body_error = None
try:
    pass
except Exception as _lw_exc:
    _lw_body_error = f"{type(_lw_exc).__name__}: {_lw_exc}"
_lw_after = {_o.as_pointer(): _o for _o in bpy.data.objects}
_lw_violations, _lw_restored, _lw_unrestored = [], [], []
def _lw_collection(_name):
    for _s in bpy.data.scenes:
        if _s.collection.name == _name:
            return _s.collection
    return bpy.data.collections.get(_name)
for _lw_ptr, _lw_fp0 in _lw_before.items():
    _lw_o = _lw_after.get(_lw_ptr)
    _lw_name = _lw_fp0["name"]
    if _lw_o is None:
        _lw_violations.append({"object": _lw_name, "kind": "deleted"})
        _lw_unrestored.append(_lw_name)
        continue
    if _lw_o.name != _lw_name:
        _lw_squatter = bpy.data.objects.get(_lw_name)
        if _lw_squatter is not None and _lw_squatter is not _lw_o:
            _lw_squatter.name = _lw_name + ".lw_renamed"
        _lw_o.name = _lw_name
        _lw_violations.append({"object": _lw_name, "kind": "renamed"})
    _lw_fp1 = _lw_fp(_lw_o)
    if any(_lw_fp1[k] != _lw_fp0[k] for k in ("geo", "data", "mats", "mods")):
        _lw_violations.append({"object": _lw_name, "kind": "edited"})
        _lw_unrestored.append(_lw_name)
        continue
    if any(_lw_fp1[k] != _lw_fp0[k] for k in ("loc", "rot", "scale", "parent", "hide_viewport", "hide_render")):
        _lw_o.location = _lw_fp0["loc"]
        _lw_o.rotation_euler = _lw_fp0["rot"]
        _lw_o.scale = _lw_fp0["scale"]
        _lw_o.parent = bpy.data.objects.get(_lw_fp0["parent"]) if _lw_fp0["parent"] else None
        _lw_o.hide_viewport = _lw_fp0["hide_viewport"]
        _lw_o.hide_render = _lw_fp0["hide_render"]
        _lw_violations.append({"object": _lw_name, "kind": "moved"})
    if _lw_fp1["colls"] != _lw_fp0["colls"]:
        for _c in _lw_fp1["colls"]:
            if _c not in _lw_fp0["colls"]:
                _coll = _lw_collection(_c)
                if _coll is not None and _lw_o.name in _coll.objects:
                    _coll.objects.unlink(_lw_o)
        for _c in _lw_fp0["colls"]:
            if _c not in _lw_fp1["colls"]:
                _coll = _lw_collection(_c)
                if _coll is not None and _lw_o.name not in _coll.objects:
                    _coll.objects.link(_lw_o)
        _lw_violations.append({"object": _lw_name, "kind": "relinked"})
    if any(v["object"] == _lw_name for v in _lw_violations) and _lw_name not in _lw_unrestored:
        _lw_restored.append(_lw_name)
_lw_renamed_own = {}
for _lw_ptr, _lw_old in _lw_own.items():
    _lw_o = _lw_after.get(_lw_ptr)
    if _lw_o is not None and _lw_o.name != _lw_old:
        _lw_renamed_own[_lw_old] = _lw_o.name
_lw_guard = {"violations": _lw_violations, "restored": sorted(set(_lw_restored)), "unrestored": sorted(set(_lw_unrestored)),
             "renamed_own": _lw_renamed_own}
_lw_result = globals().get("__RESULT__")
_lw_out = dict(_lw_result) if isinstance(_lw_result, dict) else ({} if _lw_result is None else {"return_value": _lw_result})
_lw_out[__GUARD_KEY__] = _lw_guard
if _lw_body_error is not None:
    _lw_out[__BODY_ERROR_KEY__] = _lw_body_error
__RESULT__ = _lw_out
'''


def guarded_script(lane_scene: str, body: str) -> str:
    """``body`` wrapped by the guard for the worker whose lane scene is ``lane_scene``."""
    try:
        body_tree = ast.parse(body)
    except SyntaxError:
        return body
    template = (_TEMPLATE.replace("__LANE__", json.dumps(lane_scene))
                .replace("__GUARD_KEY__", json.dumps(GUARD_KEY))
                .replace("__BODY_ERROR_KEY__", json.dumps(BODY_ERROR_KEY)))
    tree = ast.parse(template)
    guard_try = next(n for n in tree.body if isinstance(n, ast.Try))
    guard_try.body = body_tree.body or [ast.Pass()]
    return ast.unparse(ast.fix_missing_locations(tree)) + "\n"


def unwrap(result):
    """``(result for the model, guard section)``: the guard's keys taken out of the envelope, and a body error turned
    back into the failed envelope the executor would have produced."""
    if not isinstance(result, dict):
        return result, None
    guard = result.get(GUARD_KEY)
    clean = {k: v for k, v in result.items() if k not in (GUARD_KEY, BODY_ERROR_KEY)}
    if result.get(BODY_ERROR_KEY):
        clean["success"] = False
        clean["error"] = result[BODY_ERROR_KEY]
    return clean, (guard if isinstance(guard, dict) else None)


def describe(guard: dict) -> str:
    """One sentence for the worker about what the guard found."""
    parts = []
    if guard.get("restored"):
        parts.append(f"you changed objects outside your lane ({', '.join(guard['restored'])}); they were put back")
    if guard.get("unrestored"):
        parts.append(f"you deleted or edited objects outside your lane ({', '.join(guard['unrestored'])}), which cannot be "
                     "put back")
    return ("Lane guard: " + "; ".join(parts) + ". Only create and edit objects you made yourself.") if parts else ""
