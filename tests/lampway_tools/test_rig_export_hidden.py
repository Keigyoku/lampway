# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure production-AST component controls; actual Blender acceptance is separate."""
import ast
import copy
import os
from contextlib import contextmanager, nullcontext
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

REPO = Path(__file__).resolve().parents[2]
SOURCE = Path(os.environ.get('HIDDEN_VISIBILITY_SOURCE', str(REPO / 'src/scripts/mixar/modules/lampway_tools/features')))


class Object:
    def __init__(self, name, hidden=False):
        self.name = name
        self.hide_viewport = self.hide_render = self.hide_select = self.layer_hidden = hidden
        self.selected = False
        self.mode = 'OBJECT'
        self.users_collection = []
        self.data = NS(name=name, copy=lambda: NS(animation_data_clear=lambda: None))
        self.pose = NS(bones=[])
        self.modifiers = []
        self.parent = None
        self.matrix_world = ('unchanged-world-transform', name)

    def hide_get(self): return self.layer_hidden
    def hide_set(self, v): self.layer_hidden = v
    def select_get(self): return self.selected
    def select_set(self, v): self.selected = v
    def animation_data_clear(self): pass
    def copy(self):
        ob = copy.copy(self)
        ob.users_collection = list(self.users_collection)
        return ob
    def visible_get(self):
        return not (self.hide_viewport or self.layer_hidden) and any(not c.hidden for c in self.users_collection)


class Links(list):
    def __init__(self, owner=None): super().__init__(); self.owner = owner
    def link(self, value):
        self.append(value)
        if self.owner is not None and self.owner not in value.users_collection:
            value.users_collection.append(self.owner)


class Collections(list):
    def new(self, name):
        col = NS(name=name, hidden=False)
        col.objects = Links(col)
        self.append(col)
        return col
    def remove(self, col):
        for ob in col.objects:
            ob.users_collection.remove(col)
        if hasattr(self, "parent_children") and col in self.parent_children:
            self.parent_children.remove(col)
        super().remove(col)


class Layer(list): pass


def environment(hidden=False, excluded=False):
    collections = Collections()
    source_collection = collections.new('untouched source collection')
    source_collection.hidden = excluded
    arm, skin, unrelated = Object('arm', hidden), Object('skin', hidden), Object('unrelated', True)
    for ob in [arm, skin, unrelated]: source_collection.objects.link(ob)
    unrelated.selected = True
    layer = Layer([arm, skin, unrelated]); layer.active = unrelated
    context = NS(view_layer=NS(objects=layer, update=lambda: None), scene=NS(collection=NS(children=Links())))
    collections.parent_children = context.scene.collection.children
    events = []
    def mode_set(mode):
        ob = layer.active
        if mode == 'EDIT' and (not ob.visible_get() or ob.hide_select or not ob.selected):
            raise RuntimeError('Cannot edit hidden object')
        ob.mode = mode
        events.append(mode)
    def activate(ob):
        for item in layer: item.select_set(False)
        ob.select_set(True); layer.active = ob
    bpy = NS(context=context, data=NS(collections=collections), ops=NS(object=NS(mode_set=mode_set)))
    return NS(arm=arm, skin=skin, unrelated=unrelated, layer=layer, collections=collections,
              source_collection=source_collection, bpy=bpy, activate=activate, events=events)


def snapshot(env):
    return {'objects': [(o.name, o.hide_viewport, o.hide_render, o.hide_select, o.hide_get(), o.selected,
                          tuple(id(c) for c in o.users_collection), o.matrix_world, o.mode) for o in env.layer],
            'active': id(env.layer.active),
            'scene_children': tuple(id(c) for c in env.bpy.context.scene.collection.children),
            'collections': [(id(c), c.hidden, tuple(id(o) for o in c.objects)) for c in env.collections]}


def load(env, filename):
    tree = ast.parse((SOURCE / filename).read_text())
    funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    ns = {'bpy': env.bpy, 'contextmanager': contextmanager, 'C': NS(activate=env.activate, FeatureError=RuntimeError),
          'Matrix': NS(Identity=lambda n: ('identity', n))}
    selected = [n for n in funcs if n.name in ['_export_visibility', '_conform_visibility', '_copy']]
    exec(compile(ast.fix_missing_locations(ast.Module(body=selected, type_ignores=[])), filename, 'exec'), ns)
    return tree, ns


def writer(env, raises=False):
    tree, ns = load(env, 'rig_export.py')
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'export_ue')
    # Execute the unchanged production writer try/finally; isolate preceding geometric admission/readback.
    node = next(n for n in fn.body if isinstance(n, ast.Try) and any(
        isinstance(x, ast.Call) and ast.unparse(x.func) == 'bpy.ops.export_scene.fbx' for x in ast.walk(n)))
    seen = []
    def fbx(**kwargs):
        seen.extend(o.name for o in env.layer if o.selected and o.visible_get() and not o.hide_select)
        if raises: raise RuntimeError('synthetic writer exception')
    env.bpy.ops.export_scene = NS(fbx=fbx)
    ex = {'object_types': set()}
    # The metre path's carrier: the requested objects themselves (main's centimetre copies are their own native controls).
    ns.update(ob=env.arm, mesh_obs=[env.skin], layer=list(env.layer), keep_sel=[o for o in env.layer if o.selected],
              keep_active=env.layer.active, act=None, writing='synthetic-not-written.fbx', ex=ex,
              carrier=nullcontext({'armature': env.arm, 'meshes': [env.skin], 'action': None, 'exporter': ex, 'receipt': None}))
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), 'production-writer-portion', 'exec'), ns)
    return seen


@pytest.mark.parametrize('hidden', [False, True])
def test_writer_admits_exact_requested_objects_and_restores_all_source_state(hidden):
    env = environment(hidden=hidden); before = snapshot(env)
    assert writer(env) == ['arm', 'skin']
    assert snapshot(env) == before


def test_writer_exception_restores_visibility_selection_active_and_collections():
    env = environment(hidden=True); before = snapshot(env)
    with pytest.raises(RuntimeError, match='synthetic writer exception'):
        writer(env, raises=True)
    assert snapshot(env) == before


@pytest.mark.parametrize('hidden,excluded', [(False, False), (True, False), (True, True)])
def test_conform_copy_can_enter_edit_without_mutating_source_or_collections(hidden, excluded):
    env = environment(hidden, excluded); before = snapshot(env)
    tree, ns = load(env, 'rig_conform.py')
    new, copies = ns['_copy'](env.arm, 'conformed', [env.skin], '_conformed')
    env.layer.extend([new, *copies]); new_before = [(o.hide_viewport,o.hide_render,o.hide_select,o.hide_get()) for o in [new,*copies]]
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'conform')
    # Retain the actual owned wrapper and activation/Edit admission statements.
    tr = next(n for n in fn.body if isinstance(n, ast.Try) and any(isinstance(x, ast.Call) and
        ast.unparse(x.func) == 'C.activate' for x in ast.walk(n)))
    gate = next((n for n in tr.body if isinstance(n, ast.With) and '_conform_visibility' in ast.unparse(n.items[0].context_expr)), None)
    if gate:
        gate = copy.deepcopy(gate)
        def activates(n):
            return isinstance(n, ast.Expr) and isinstance(n.value, ast.Call) and ast.unparse(n.value.func) == 'C.activate'
        # The rewrite may sit under the source_copy branch (`if not preserving:`); take the statements around the activation.
        stmts = gate.body if any(activates(n) for n in gate.body) else next(
            n.body for n in gate.body if isinstance(n, ast.If) and any(activates(x) for x in n.body))
        index = next(i for i,n in enumerate(stmts) if activates(n))
        gate.body = stmts[index:index+2]
        gate.items[0].context_expr.args = [ast.List(elts=[ast.Name(id='new',ctx=ast.Load()),ast.Starred(value=ast.Name(id='copies',ctx=ast.Load()),ctx=ast.Load())],ctx=ast.Load())]
        # Leave Edit Mode through the production admission helper's finally.
        body = [gate]
    else:
        index = next(i for i,n in enumerate(tr.body) if isinstance(n, ast.Expr) and
                     isinstance(n.value, ast.Call) and ast.unparse(n.value.func) == 'C.activate')
        body = tr.body[index:index+2]
        body.append(next(n for n in tr.body[index+2:] if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call) and ast.unparse(n.value.func) == 'bpy.ops.object.mode_set'))
    ns.update(new=new, copies=copies, base=new, base_meshes=[])
    exec(compile(ast.fix_missing_locations(ast.Module(body=body, type_ignores=[])), 'production-conform-edit-admission', 'exec'), ns)
    assert 'EDIT' in env.events and new.mode == 'OBJECT'
    assert [(o.hide_viewport,o.hide_render,o.hide_select,o.hide_get()) for o in [new,*copies]] == new_before
    assert tuple(id(c) for c in new.users_collection) == (id(env.source_collection),)
    env.layer[:] = env.layer[:3]
    # Created output copies persist in their original source collection; source membership/state itself stays identical.
    env.source_collection.objects[:] = env.source_collection.objects[:3]
    assert snapshot(env) == before


def test_conform_edit_exception_restores_owned_copy_and_removes_only_temporary_collection():
    env = environment(hidden=True, excluded=True); before = snapshot(env)
    _tree, ns = load(env, 'rig_conform.py')
    new, _copies = ns['_copy'](env.arm, 'conformed', [], '_conformed')
    flags = (new.hide_viewport, new.hide_select, new.hide_get())
    # Missing helper is a behavioral RED: the original copied armature cannot enter Edit Mode.
    guard = ns.get('_conform_visibility')
    @contextmanager
    def original_no_admission(ob): yield
    with pytest.raises(RuntimeError, match='synthetic edit exception'):
        with (guard or original_no_admission)([new]):
            env.activate(new); env.bpy.ops.object.mode_set(mode='EDIT')
            raise RuntimeError('synthetic edit exception')
    assert new.mode == 'OBJECT' and (new.hide_viewport,new.hide_select,new.hide_get()) == flags
    assert len(env.collections) == 1 and new.users_collection == [env.source_collection]
    env.source_collection.objects.remove(new)
    assert snapshot(env) == before


def test_native_hidden_armature_and_skin_export_without_changing_source_visibility(tmp_path):
    from features_support import run
    from test_rig_export_ue import CHAIN
    result = run(tmp_path, CHAIN + '''
from mixar.modules.lampway_tools.features import rig_export as RE
arm = chain("hidden_source")
skin = bpy.data.objects["hidden_source_skin"]
call("rig_inspect", armature=arm.name)
for ob in (arm, skin):
    ob.select_set(False)
    ob.hide_viewport = True
    ob.hide_render = True
    ob.hide_select = True
    ob.hide_set(True)
def source_state():
    return {ob.name: {"viewport": ob.hide_viewport, "render": ob.hide_render,
                     "select": ob.hide_select, "layer": ob.hide_get(),
                     "selected": ob.select_get(), "matrix": [list(row) for row in ob.matrix_world]}
            for ob in (arm, skin)}
before = source_state()
ids = set(bpy.data.objects.keys())
good = call("rig_export_ue", armature=arm.name, out="export/hidden.fbx", recipe=str(RE.RECIPES / "cm_native_blender_convention.json"))
after_good = source_state()
bad = call("rig_export_ue", armature=arm.name, out="export/hidden_wrong.fbx", recipe=str(RE.RECIPES / "cm_native_ue_axes.json"))
print("RESULT", json.dumps({"good": good, "bad": bad, "before": before,
                           "after_good": after_good, "after_bad": source_state(),
                           "ids_restored": set(bpy.data.objects.keys()) == ids}))
''', timeout=600)
    assert result.rc == 0, result.out[-3000:]
    data = result.results[0]
    assert data["good"]["ok"], data["good"]
    assert data["good"]["readback"]["bones_compared"] == 5
    assert data["good"]["normals"]["unmatched_meshes"] == 0
    assert not data["bad"]["ok"] and "read-back" in data["bad"]["error"], data["bad"]
    assert data["before"] == data["after_good"] == data["after_bad"]
    assert data["ids_restored"]


def test_native_export_visibility_restores_source_flags_when_writer_raises(tmp_path):
    from features_support import run
    from test_rig_export_ue import CHAIN
    result = run(tmp_path, CHAIN + '''
from mixar.modules.lampway_tools.features.rig_export import _export_visibility
from mixar.modules.lampway_tools.features import rig_export as RE
arm = chain("hidden_source")
skin = bpy.data.objects["hidden_source_skin"]
for ob in (arm, skin):
    ob.select_set(False)
    ob.hide_viewport = ob.hide_render = ob.hide_select = True
    ob.hide_set(True)
def flags():
    return [[ob.hide_viewport, ob.hide_render, ob.hide_select, ob.hide_get()]
            for ob in (arm, skin)]
before = flags()
try:
    with _export_visibility([arm, skin]):
        admitted = flags() == [[False] * 4] * 2
        raise RuntimeError("planted writer failure")
except RuntimeError as exc:
    caught = str(exc) == "planted writer failure"
print("RESULT", json.dumps({"admitted": admitted, "caught": caught, "restored": flags() == before}))
''')
    assert result.rc == 0, result.out[-3000:]
    assert result.results[0] == {"admitted": True, "caught": True, "restored": True}


def test_native_hidden_collection_conform_preserves_source_and_collection_state(tmp_path):
    from features_support import run
    from test_rig_tools import MIXAMO
    from test_rig_conform import SKIN
    result = run(tmp_path, MIXAMO + SKIN + '''
ob = mixamo(); skin = skinned(ob)
call("rig_inspect", armature=ob.name)
call("rig_map", armature=ob.name, out="rig/hidden.map.json")
source_collection = bpy.data.collections.new("hidden source collection")
bpy.context.scene.collection.children.link(source_collection)
for item in (ob, skin):
    for collection in list(item.users_collection): collection.objects.unlink(item)
    source_collection.objects.link(item)
    item.hide_viewport = item.hide_render = item.hide_select = True
    item.hide_set(True)
bpy.context.view_layer.layer_collection.children[source_collection.name].exclude = True
bpy.context.view_layer.update()
def source_state():
    return {item.name: {"flags": [item.hide_viewport, item.hide_render, item.hide_select, item.hide_get()],
           "collections": [collection.name for collection in item.users_collection],
           "matrix": [list(row) for row in item.matrix_world], "selected": item.select_get()} for item in (ob, skin)}
before = source_state(); collections_before = sorted(bpy.data.collections.keys())
active_before = bpy.context.view_layer.objects.active.name if bpy.context.view_layer.objects.active else None
result = call("rig_conform", armature=ob.name, map="rig/hidden.map.json", dry_run=False)
repeat = call("rig_conform", armature=ob.name, map="rig/hidden.map.json", dry_run=False, out_name="hidden_second")
print("RESULT", json.dumps({"result": result, "repeat": repeat, "before": before, "after": source_state(),
       "collections_before": collections_before, "collections_after": sorted(bpy.data.collections.keys()),
       "excluded_after": bpy.context.view_layer.layer_collection.children[source_collection.name].exclude,
       "active_before": active_before, "active_after": bpy.context.view_layer.objects.active.name if bpy.context.view_layer.objects.active else None}))
''')
    assert result.rc == 0, result.out[-3000:]
    data = result.results[0]
    assert data["result"]["ok"], data["result"]
    assert data["repeat"]["ok"], data["repeat"]
    assert data["before"] == data["after"]
    assert data["collections_before"] == data["collections_after"] and data["excluded_after"]
    assert data["active_before"] == data["active_after"]


def test_conform_visibility_synchronizes_removed_baseline_before_snapshot():
    env = environment(hidden=True, excluded=True)
    _tree, ns = load(env, "rig_conform.py")
    new, _copies = ns["_copy"](env.arm, "conformed", [], "_conformed")
    # Real native repeated-conform falsifier: a removed baseline remains as a pending None Base entry.
    env.layer.append(None)
    updates = []
    def synchronize():
        updates.append(True)
        env.layer[:] = [ob for ob in env.layer if ob is not None]
    env.bpy.context.view_layer.update = synchronize
    with ns["_conform_visibility"]([new]):
        assert updates and None not in env.layer
        env.activate(new)
        env.bpy.ops.object.mode_set(mode="EDIT")
    assert new.mode == "OBJECT"
    assert env.layer.active is env.unrelated and env.unrelated.select_get()
    assert new.users_collection == [env.source_collection] and len(env.collections) == 1
