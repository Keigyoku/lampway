# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Adapt the existing asynchronous scene renderer to a project file and tool job."""
import threading
import uuid

import bpy

from .. import jobs, settings
from . import ViewError, reserve_output


def start(window, preset, out):
    from mixar.modules.scene_render.core import jobs as renders
    from mixar.modules.scene_render.constants import RESULTS_NS
    root = settings.load().project_root.resolve()
    path = reserve_output(root, out)
    scene = window.scene
    key = uuid.uuid4().hex
    options = {'engine': 'eevee', 'width': 256, 'height': 256, 'samples': 8} if preset == 'thumbnail' else {}
    try:
        with bpy.context.temp_override(window=window, scene=scene):
            receipt = renders.start(bpy.context, key, kind='image', expected_session=str(scene.mixie_session_id or ''), **options)
        if receipt['status'] != 'started':
            raise ViewError('render_in_progress' if receipt['status'] == 'busy' else receipt.get('error', 'render_unavailable'),
                            'Cannot start still render', ['lampway_job_status'])
    except Exception:
        path.unlink(missing_ok=True)
        raise
    done = threading.Event()
    terminal = {}

    def wait():
        # No Blender references or APIs on this worker: the timer owns delivery.
        done.wait()
        if 'error' in terminal:
            raise RuntimeError(terminal['error'])
        return dict(terminal)

    job = jobs.start('render-still', wait)
    jobs.ensure_timer()

    def finish():
        try:
            record = bpy.app.driver_namespace.get(RESULTS_NS, {}).get(key)
            if record is None or record.get('status') == 'started':
                if not any(s == scene for s in bpy.data.scenes):
                    raise RuntimeError('scene_unavailable')
                return 0.2
            if record.get('status') != 'done':
                raise RuntimeError(record.get('error', record.get('status', 'render_failed')))
            image = bpy.data.images.get(record.get('moodboard_image_name', ''))
            if image is None:
                raise RuntimeError('output_unavailable')
            # Packed scene-render result survives renderer cleanup; persist only our exclusive reservation.
            if image.packed_file is None:
                raise RuntimeError('packed_output_unavailable')
            path.write_bytes(bytes(image.packed_file.data))
            terminal.update(path=path.relative_to(root).as_posix(), image={'width': image.size[0], 'height': image.size[1], 'bytes': path.stat().st_size})
        except Exception as exc:
            path.unlink(missing_ok=True)
            terminal['error'] = str(exc)
        done.set()
        return None

    try:
        # Keep the delivery timer across a file load so it can fail the old job and wake its worker.
        bpy.app.timers.register(finish, first_interval=0.2, persistent=True)
    except Exception as exc:
        path.unlink(missing_ok=True)
        terminal['error'] = str(exc)
        done.set()
    return {'action': 'render_still', 'job': job.id, 'preset': preset,
            'help': [f'lampway_job_status job={job.id}']}
