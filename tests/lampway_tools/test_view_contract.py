# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The view wrapper's observable contract, without a desktop or paid jobs."""
import importlib
import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src/scripts'))


def test_view_engine_exists():
    assert (Path(__file__).resolve().parents[2] / 'src/scripts/mixar/modules/lampway_tools/api_view.py').exists(), 'T2 has no client entry'


def engine():
    return importlib.import_module('mixar.modules.lampway_tools.view')


def test_outside_path_is_refused(tmp_path):
    assert (Path(__file__).resolve().parents[2] / 'src/scripts/mixar/modules/lampway_tools/api_view.py').exists(), 'T2 has no path jail'
    from mixar.modules.lampway_tools.settings import PathOutsideProject
    import pytest
    with pytest.raises(PathOutsideProject):
        engine().reserve_output(tmp_path, '../escape.png')


def test_render_paths_never_overwrite(tmp_path):
    assert (Path(__file__).resolve().parents[2] / 'src/scripts/mixar/modules/lampway_tools/api_view.py').exists(), 'T2 has no unique output'
    first = engine().reserve_output(tmp_path, 'renders/still.png')
    first.write_bytes(b'original')
    second = engine().reserve_output(tmp_path, 'renders/still.png')
    assert first.name == 'still.png' and second.name == 'still-2.png'
    assert first.read_bytes() == b'original'


def test_png_budget_and_crop():
    assert (Path(__file__).resolve().parents[2] / 'src/scripts/mixar/modules/lampway_tools/api_view.py').exists(), 'T2 has no bounded PNG'
    from PIL import Image
    import io
    frame = Image.new('RGB', (400, 300), 'white')
    frame.paste('black', (40, 100, 140, 200))
    raw = io.BytesIO()
    frame.save(raw, format='PNG')
    png, meta = engine().crop_png(raw.getvalue(), {'width': 400, 'height': 300, 'window_width': 400, 'window_height': 300}, (40, 100, 100, 100), 50000)
    with Image.open(io.BytesIO(png)) as result:
        assert result.size == (100, 100)
        assert result.getpixel((50, 50)) == (0, 0, 0)
    assert meta['bytes'] <= 50000


def test_invalid_arguments_are_structured():
    assert (Path(__file__).resolve().parents[2] / 'src/scripts/mixar/modules/lampway_tools/api_view.py').exists(), 'T2 has no argument validation'
    view = importlib.import_module('mixar.modules.lampway_tools.api_view').view
    assert view(action='bogus')['code'] == 'bad_argument'
    assert view(max_bytes=49999)['code'] == 'bad_argument'
    assert view(unknown=True)['code'] == 'unknown_argument'


def test_capture_requires_optin(monkeypatch):
    from mixar.modules.lampway_tools.view import runtime, ViewError
    from mixar.modules.mcp_bridge.core import runtime as bridge
    import pytest
    monkeypatch.setattr(bridge, 'ui_control_enabled', lambda: False)
    with pytest.raises(ViewError) as exc:
        runtime.pixel_gate()
    assert exc.value.code == 'ui_control_off'


def test_busy_renderer_refuses_before_work(monkeypatch):
    from mixar.modules.lampway_tools.view import runtime
    from mixar.modules.common.render_coordinator import core as slot
    from types import SimpleNamespace
    monkeypatch.setattr(runtime, 'bound_window', lambda: SimpleNamespace())
    monkeypatch.setattr(slot, 'busy', lambda: True)
    view = importlib.import_module('mixar.modules.lampway_tools.api_view').view
    assert view(action='render_still')['code'] == 'render_in_progress'


def test_focus_preserves_selection_and_unhide_undo(monkeypatch):
    from mixar.modules.lampway_tools.view import runtime, ViewError
    from types import SimpleNamespace
    from contextlib import nullcontext
    from unittest.mock import Mock
    import pytest

    class Object:
        def __init__(self, name, selected, hidden=False):
            self.name, self.selected, self.hidden = name, selected, hidden
            self.hide_viewport = False
            self.bound_box = [(0, 0, 0), (2, 2, 2)]
            self.matrix_world = SimpleNamespace()
        def hide_get(self, **kw): return self.hidden
        def hide_set(self, value, **kw): self.hidden = value
        def visible_get(self, **kw): return not self.hidden and not self.hide_viewport
        def select_get(self, **kw): return self.selected
        def select_set(self, value, **kw): self.selected = value

    class Objects(list):
        def get(self, name): return next((o for o in self if o.name == name), None)

    class Matrix:
        def __matmul__(self, point): return point

    one, target = Object('selected', True), Object('target', False, True)
    target.matrix_world = Matrix()
    objects = Objects([one, target])
    objects.active = one
    area = SimpleNamespace(type='VIEW_3D', ui_type='VIEW_3D', width=400, height=300,
                           regions=[SimpleNamespace(type='WINDOW')])
    window = SimpleNamespace(scene=SimpleNamespace(objects=objects, unit_settings=SimpleNamespace(scale_length=0.01)), view_layer=SimpleNamespace(objects=objects),
                             screen=SimpleNamespace(areas=[area]))
    monkeypatch.setattr(runtime.bpy.context, 'temp_override', lambda **kw: nullcontext())
    monkeypatch.setattr(sys.modules['mathutils'], 'Vector', lambda value: value)
    operation = Mock(return_value={'FINISHED'})
    undo = Mock()
    monkeypatch.setattr(runtime.bpy.ops.view3d, 'view_selected', operation)
    monkeypatch.setattr(runtime.bpy.ops.ed, 'undo_push', undo)
    with pytest.raises(ViewError) as exc:
        runtime.focus(window, 'target', None, False)
    assert exc.value.code == 'hidden'
    assert operation.call_count == 0
    result = runtime.focus(window, 'target', None, True)
    assert one.selected and not target.selected and objects.active is one
    assert not target.hidden and result['unhidden']
    assert result['framed_bounds'] == {'min': [0.0, 0.0, 0.0], 'max': [0.02, 0.02, 0.02]}
    undo.assert_called_once_with(message='Lampway: unhide target')



def test_render_adapter_persists_packed_png_on_main_thread(monkeypatch, tmp_path):
    from mixar.modules.lampway_tools.view import rendering
    from mixar.modules.scene_render.core import jobs as renders
    from mixar.modules.scene_render.constants import RESULTS_NS
    from types import SimpleNamespace
    from contextlib import nullcontext
    from unittest.mock import Mock
    from PIL import Image
    import io
    raw = io.BytesIO()
    Image.new('RGB', (256, 256), 'white').save(raw, format='PNG')
    png = raw.getvalue()
    scene = SimpleNamespace(mixie_session_id='bound-session')
    window = SimpleNamespace(scene=scene)
    image = SimpleNamespace(packed_file=SimpleNamespace(data=png), size=[256, 256])
    callbacks = []
    job = SimpleNamespace(id='render-still-test')
    monkeypatch.setattr(rendering.settings, 'load', lambda: SimpleNamespace(project_root=tmp_path))
    monkeypatch.setattr(rendering.bpy.context, 'temp_override', lambda **kw: nullcontext())
    native = Mock(return_value={'status': 'started'})
    monkeypatch.setattr(renders, 'start', native)
    monkeypatch.setattr(rendering.jobs, 'start', lambda kind, fn: job)
    monkeypatch.setattr(rendering.jobs, 'ensure_timer', lambda: None)
    monkeypatch.setattr(rendering.bpy.app.timers, 'register', lambda fn, **kw: callbacks.append(fn))
    monkeypatch.setattr(rendering.bpy.app, 'driver_namespace', {})
    monkeypatch.setattr(rendering.bpy.data.images, 'get', lambda name: image)
    result = rendering.start(window, 'thumbnail', 'renders/still.png')
    assert result['job'] == job.id
    opts = native.call_args.kwargs
    assert opts['engine'] == 'eevee' and opts['width'] == 256 and opts['samples'] == 8
    assert opts['expected_session'] == 'bound-session'
    key = native.call_args.args[1]
    rendering.bpy.app.driver_namespace[RESULTS_NS] = {key: {'status': 'done', 'moodboard_image_name': 'packed'}}
    assert callbacks[0]() is None
    assert (tmp_path / 'renders/still.png').read_bytes() == png


def test_capture_passes_secret_widgets_to_masked_observer(monkeypatch, tmp_path):
    from mixar.modules.lampway_tools.view import runtime
    from mixar.modules.common.ui_control.core import observe
    from types import SimpleNamespace
    from unittest.mock import Mock
    from PIL import Image
    import io
    import base64
    raw = io.BytesIO()
    Image.new('RGB', (10, 10), 'black').save(raw, format='PNG')
    items = [{'secret': True, 'rect': [0, 0, 10, 10]}]
    observer = Mock(return_value=({'data': base64.b64encode(raw.getvalue()).decode()},
                                 {'window_width': 10, 'window_height': 10}))
    window = SimpleNamespace()
    monkeypatch.setattr(runtime, 'pixel_gate', lambda: None)
    monkeypatch.setattr(runtime.bpy.app, 'driver_namespace', {})
    monkeypatch.setattr(observe, 'widgets', lambda: items)
    monkeypatch.setattr(observe, 'image', observer)
    monkeypatch.setattr(runtime.settings, 'load', lambda: SimpleNamespace(project_root=tmp_path))
    result = runtime.capture(window, None, 50000)
    observer.assert_called_once_with(window, items)
    assert result['image']['bytes'] <= 50000
    assert (tmp_path / result['image_path']).read_bytes().startswith(b'\x89PNG')


def test_switched_tab_capture_refuses_cached_pixels(monkeypatch):
    from mixar.modules.lampway_tools.view import runtime, ViewError
    import pytest
    monkeypatch.setattr(runtime, 'pixel_gate', lambda: None)
    monkeypatch.setattr(runtime.bpy.app, 'driver_namespace', {'mixie_route_switched': True})
    with pytest.raises(ViewError) as exc:
        runtime.capture(None, None, 50000)
    assert exc.value.code == 'capture_busy'


def test_random_png_downscales_to_budget():
    from PIL import Image
    import numpy as np
    import io
    random = np.random.default_rng(42).integers(0, 256, (400, 400, 3), dtype=np.uint8)
    frame = Image.fromarray(random)
    stream = io.BytesIO()
    frame.save(stream, format='PNG')
    assert len(stream.getvalue()) > 50000
    png, meta = engine().crop_png(stream.getvalue(), {}, None, 50000)
    assert len(png) == meta['bytes'] <= 50000
    assert meta['width'] < 400 and meta['height'] < 400
